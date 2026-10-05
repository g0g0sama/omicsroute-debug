from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from engine.context_intake import RAW_READS, GENOME_ASSEMBLY, PREDICTED_PROTEINS
from engine.planner_v2 import (
    EUKARYOTIC, ILLUMINA, ONT, PACBIO, HYBRID_ONT, HYBRID_PACBIO,
    _assembly_steps, _hybrid_decision_points, _hybrid_post_assembly_steps,
    _long_read_steps, _short_read_steps,
)

PLANNER_VERSION = "3.1-all-eukaryotic-contexts"

GENOME_ASSEMBLY_GOAL = "Genome assembly"
GENOME_QUALITY = "Genome quality assessment"
CONTAMINATION_SCREENING = "Contamination screening"
REPEAT_ANNOTATION = "Repeat annotation"
GENE_PREDICTION = "Gene prediction"
FUNCTIONAL_ANNOTATION = "Functional annotation"

RAW_GOALS = [
    GENOME_ASSEMBLY_GOAL, GENOME_QUALITY, CONTAMINATION_SCREENING,
    REPEAT_ANNOTATION, GENE_PREDICTION, FUNCTIONAL_ANNOTATION,
]
ASSEMBLY_GOALS = [
    GENOME_QUALITY, CONTAMINATION_SCREENING, REPEAT_ANNOTATION,
    GENE_PREDICTION, FUNCTIONAL_ANNOTATION,
]
PROTEIN_GOALS = [FUNCTIONAL_ANNOTATION]

_SUPPORTED_RAW_CONTEXTS = {
    (ILLUMINA, "Paired-end"),
    (ONT, "Long reads"),
    (PACBIO, "Long reads"),
    (HYBRID_ONT, "Paired-end + Long reads"),
    (HYBRID_PACBIO, "Paired-end + Long reads"),
}

_GOAL_SPECS: dict[str, dict[str, Any]] = {
    GENOME_ASSEMBLY_GOAL: {
        "target_artifact": "eukaryotic_genome_fasta",
        "description": (
            "Build a de novo eukaryotic genome assembly from the selected "
            "sequencing strategy and stop once the genome FASTA is produced."
        ),
    },
    CONTAMINATION_SCREENING: {
        "target_operation": "contamination_screening",
        "target_artifact": "contamination_screening_report",
        "description": (
            "Reach an assembled genome, perform structural QC where possible, "
            "and screen for contaminant/cobiont sequence."
        ),
    },
    GENOME_QUALITY: {
        "target_operation": "genome_quality_assessment",
        "target_artifact": "genome_completeness_report",
        "description": (
            "Reach an assembled genome and continue through assembly QC, "
            "contamination screening and lineage-aware completeness assessment."
        ),
    },
    REPEAT_ANNOTATION: {
        "target_operation": "repeat_annotation",
        "target_artifact": "repeat_annotation_gff",
        "description": (
            "Reach a quality-checked genome, discover repeats/TEs, and produce "
            "a repeat-masked genome plus repeat annotation."
        ),
    },
    GENE_PREDICTION: {
        "target_operation": "gene_prediction",
        "target_artifact": "eukaryotic_gene_annotation_gff",
        "description": (
            "Reach a quality-checked, repeat-masked genome and produce "
            "structural gene models plus predicted proteins."
        ),
    },
    FUNCTIONAL_ANNOTATION: {
        "target_operation": "functional_annotation",
        "target_artifact": "functional_annotation_table",
        "description": (
            "Continue the artifact path through structural gene annotation "
            "when needed and produce protein functional annotation."
        ),
    },
}

def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

def _is_supported_raw_context(sequencing: str, read_type: str) -> bool:
    return (sequencing, read_type) in _SUPPORTED_RAW_CONTEXTS

def supports_target_artifact_context(
    sample_type: str, sequencing: str, read_type: str,
    data_state: str, goal: str | None = None,
) -> bool:
    if sample_type != EUKARYOTIC:
        return False
    if data_state == RAW_READS:
        if not _is_supported_raw_context(sequencing, read_type):
            return False
        allowed = RAW_GOALS
    elif data_state == GENOME_ASSEMBLY:
        allowed = ASSEMBLY_GOALS
    elif data_state == PREDICTED_PROTEINS:
        allowed = PROTEIN_GOALS
    else:
        return False
    return goal is None or goal in allowed

def get_target_artifact_goal_options(
    sample_type: str, sequencing: str, read_type: str, data_state: str,
) -> list[str]:
    if sample_type != EUKARYOTIC:
        return []
    if data_state == RAW_READS:
        return list(RAW_GOALS) if _is_supported_raw_context(sequencing, read_type) else []
    if data_state == GENOME_ASSEMBLY:
        return list(ASSEMBLY_GOALS)
    if data_state == PREDICTED_PROTEINS:
        return list(PROTEIN_GOALS)
    return []

def _strategy_id(goal: str, mode: str) -> str:
    return f"planner3__eukaryotic_genome__{_slug(goal)}__{_slug(mode)}"

def _strategy_modes(goal: str, data_state: str) -> list[str]:
    if data_state == PREDICTED_PROTEINS:
        return ["protein_input"]
    if goal in {GENE_PREDICTION, FUNCTIONAL_ANNOTATION}:
        return ["evidence_guided", "genome_only"]
    return ["target_artifact"]

def get_target_artifact_workflow_strategies(
    sample_type: str, sequencing: str, read_type: str,
    goal: str, data_state: str,
) -> list[dict]:
    if not supports_target_artifact_context(
        sample_type, sequencing, read_type, data_state, goal
    ):
        return []
    spec = _GOAL_SPECS[goal]
    results = []
    for mode in _strategy_modes(goal, data_state):
        if mode == "evidence_guided":
            name = f"{goal} — evidence-guided structural annotation"
            description = spec["description"] + " Uses homologous protein evidence for structural annotation."
        elif mode == "genome_only":
            name = f"{goal} — genome-only structural annotation fallback"
            description = spec["description"] + " Uses the genome-only BRAKER4 fallback when external protein evidence is unavailable."
        elif mode == "protein_input":
            name = f"{goal} — from predicted proteins"
            description = (
                "The starting artifact is already a predicted eukaryotic protein FASTA, "
                "so genome assembly, QC, repeat handling and gene prediction are not repeated."
            )
        else:
            name = f"{goal} — target-artifact route"
            description = spec["description"]
        results.append({
            "id": _strategy_id(goal, mode),
            "name": name,
            "description": description,
            "dynamic": True,
            "route_class": "artifact_target_planned",
            "planner_version": PLANNER_VERSION,
            "goal_target_artifact": spec["target_artifact"],
        })
    return results

def _raw_input_artifacts(sequencing: str) -> list[str]:
    if sequencing == ILLUMINA:
        return ["raw_paired_fastq"]
    if sequencing in {ONT, PACBIO}:
        return ["raw_long_fastq"]
    if sequencing in {HYBRID_ONT, HYBRID_PACBIO}:
        return ["raw_paired_fastq", "raw_long_fastq"]
    return []

def _build_raw_prefix(sequencing: str, read_type: str) -> list[dict]:
    steps: list[dict] = []
    if sequencing == ILLUMINA:
        steps.extend(_short_read_steps())
    elif sequencing == ONT:
        steps.extend(_long_read_steps(ONT, include_filtering=True))
    elif sequencing == PACBIO:
        steps.extend(_long_read_steps(PACBIO, include_filtering=False))
    elif sequencing == HYBRID_ONT:
        steps.extend(_short_read_steps())
        steps.extend(_long_read_steps(ONT, include_filtering=True))
    elif sequencing == HYBRID_PACBIO:
        steps.extend(_short_read_steps())
        steps.extend(_long_read_steps(PACBIO, include_filtering=False))
    steps.extend(_assembly_steps(sequencing, read_type))
    return steps

def _post_assembly_steps_for_context(
    sequencing: str, data_state: str, evidence_guided: bool,
) -> list[dict]:
    steps = deepcopy(_hybrid_post_assembly_steps(evidence_guided=evidence_guided))
    has_illumina_reads = (
        data_state == RAW_READS
        and sequencing in {ILLUMINA, HYBRID_ONT, HYBRID_PACBIO}
    )
    if not has_illumina_reads:
        qc_step = steps[0]
        qc_step["name"] = "Assembly structural quality assessment"
        qc_step["description"] = (
            "Review assembly statistics and fragmentation with QUAST. "
            "Merqury is not forced when an appropriate accurate-read k-mer "
            "input is not present in the selected starting context."
        )
        qc_step["mode"] = "sequential"
        qc_step["min_successful_candidates"] = 1
        qc_step["candidates"] = ["quast"]
    return steps

def _slice_to_operation(steps: list[dict], target_operation: str) -> list[dict]:
    output: list[dict] = []
    for step in steps:
        output.append(step)
        if step.get("operation") == target_operation:
            return output
    raise ValueError(
        f"Target operation '{target_operation}' is missing from "
        "the eukaryotic target-artifact graph."
    )

def _assembly_target_operation(sequencing: str) -> str:
    return (
        "hybrid_genome_assembly"
        if sequencing in {HYBRID_ONT, HYBRID_PACBIO}
        else "genome_assembly"
    )

def _protein_input_steps() -> list[dict]:
    return [{
        "operation": "functional_annotation",
        "name": "Complementary protein functional annotation",
        "description": (
            "Run orthology-based eggNOG-mapper together with domain/family "
            "annotation from InterProScan."
        ),
        "mode": "parallel",
        "min_successful_candidates": 2,
        "candidates": ["eggnog_mapper", "interproscan"],
    }]

def _decision_points_for(
    sequencing: str, data_state: str, included_operations: set[str],
) -> list[dict]:
    if data_state != RAW_READS or sequencing not in {HYBRID_ONT, HYBRID_PACBIO}:
        return []
    result = []
    for point in _hybrid_decision_points(sequencing):
        point_id = point.get("id")
        if point_id in {"assembly_polishing", "haplotig_reduction", "pacbio_read_chemistry"}:
            result.append(point)
        elif point_id == "contamination_response" and "contamination_screening" in included_operations:
            result.append(point)
    return result

def materialize_target_artifact_workflow(
    sample_type: str, sequencing: str, read_type: str,
    goal: str, workflow_id: str | None, data_state: str,
) -> dict | None:
    if not supports_target_artifact_context(
        sample_type, sequencing, read_type, data_state, goal
    ):
        return None

    mode_lookup = {
        _strategy_id(goal, mode): mode
        for mode in _strategy_modes(goal, data_state)
    }
    mode = mode_lookup.get(str(workflow_id or ""))
    if mode is None:
        return None

    spec = _GOAL_SPECS[goal]
    evidence_guided = mode == "evidence_guided"
    steps: list[dict] = []
    external_inputs: list[str] = []

    if data_state == PREDICTED_PROTEINS:
        external_inputs.extend(["eukaryotic_protein_fasta", "orthology_database"])
        steps.extend(_protein_input_steps())
    else:
        if data_state == RAW_READS:
            external_inputs.extend(_raw_input_artifacts(sequencing))
            steps.extend(_build_raw_prefix(sequencing, read_type))
        elif data_state == GENOME_ASSEMBLY:
            external_inputs.append("eukaryotic_genome_fasta")

        if goal != GENOME_ASSEMBLY_GOAL:
            post_steps = _post_assembly_steps_for_context(
                sequencing=sequencing,
                data_state=data_state,
                evidence_guided=evidence_guided,
            )
            steps.extend(_slice_to_operation(post_steps, spec["target_operation"]))

    operations = {
        step.get("operation")
        for step in steps
        if step.get("operation")
    }

    if "genome_quality_assessment" in operations:
        external_inputs.append("busco_lineage_database")
    if evidence_guided and "gene_prediction" in operations:
        external_inputs.append("protein_evidence_fasta")
    if "functional_annotation" in operations:
        external_inputs.append("orthology_database")

    target_operation = (
        _assembly_target_operation(sequencing)
        if goal == GENOME_ASSEMBLY_GOAL
        else spec.get("target_operation")
    )

    route_suffix = (
        "evidence-guided route" if mode == "evidence_guided"
        else "genome-only fallback route" if mode == "genome_only"
        else "protein-input route" if mode == "protein_input"
        else "target-artifact route"
    )

    return {
        "id": workflow_id,
        "name": f"Eukaryotic {goal.lower()} — {route_suffix}",
        "description": spec["description"],
        "context": {
            "sample_type": EUKARYOTIC,
            "sequencing": sequencing,
            "read_type": read_type,
            "goal": goal,
        },
        "external_inputs": list(dict.fromkeys(external_inputs)),
        "steps": steps,
        "dynamic_route": True,
        "route_class": "artifact_target_planned",
        "planning_basis": (
            "current artifact + requested target artifact + "
            "platform-aware operation graph + dependency validation"
        ),
        "planner_version": PLANNER_VERSION,
        "goal_target_artifact": spec["target_artifact"],
        "target_operation": target_operation,
        "decision_points": _decision_points_for(sequencing, data_state, operations),
        "data_state": data_state,
    }
# OMICSROUTE EUKARYOTIC ORGANISM IDENTIFICATION V1
# This goal intentionally means closest indexed reference / lineage evidence.
# It does not claim an exact species call when the reference collection is
# incomplete, nor does it apply prokaryote-specific ANI/GTDB logic to eukaryotes.
ORGANISM_IDENTIFICATION = "Organism identification / closest reference match"
_ORIGINAL_TARGET_GOALS_ORGANISM_ID_V1 = get_target_artifact_goal_options
_ORIGINAL_TARGET_STRATEGIES_ORGANISM_ID_V1 = get_target_artifact_workflow_strategies
_ORIGINAL_TARGET_MATERIALIZER_ORGANISM_ID_V1 = materialize_target_artifact_workflow


def _organism_identification_supported(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
) -> bool:
    if sample_type != EUKARYOTIC:
        return False
    if data_state == GENOME_ASSEMBLY:
        return True
    return data_state == RAW_READS and _is_supported_raw_context(
        sequencing,
        read_type,
    )


def _organism_identification_strategy_id() -> str:
    return "planner3__eukaryotic_genome__organism_identification__reference_sketch"


def get_target_artifact_goal_options(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
) -> list[str]:
    values = list(_ORIGINAL_TARGET_GOALS_ORGANISM_ID_V1(
        sample_type,
        sequencing,
        read_type,
        data_state,
    ) or [])

    if _organism_identification_supported(
        sample_type,
        sequencing,
        read_type,
        data_state,
    ) and ORGANISM_IDENTIFICATION not in values:
        values.append(ORGANISM_IDENTIFICATION)

    return values


def get_target_artifact_workflow_strategies(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    data_state: str,
) -> list[dict]:
    if goal != ORGANISM_IDENTIFICATION:
        return _ORIGINAL_TARGET_STRATEGIES_ORGANISM_ID_V1(
            sample_type,
            sequencing,
            read_type,
            goal,
            data_state,
        )

    if not _organism_identification_supported(
        sample_type,
        sequencing,
        read_type,
        data_state,
    ):
        return []

    return [{
        "id": _organism_identification_strategy_id(),
        "name": "Eukaryotic organism identification — closest reference sketch match",
        "description": (
            "For an unknown eukaryotic genome, assemble first when starting "
            "from reads, then compare a genome sketch against a curated broad "
            "reference-sketch collection. Interpret the result as the closest "
            "indexed reference and its lineage; exact species identification "
            "requires adequate reference coverage and confirmatory review."
        ),
        "dynamic": True,
        "route_class": "artifact_target_planned",
        "planner_version": PLANNER_VERSION,
        "goal_target_artifact": "organism_identification_report",
    }]


def materialize_target_artifact_workflow(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    workflow_id: str | None,
    data_state: str,
) -> dict | None:
    if goal != ORGANISM_IDENTIFICATION:
        return _ORIGINAL_TARGET_MATERIALIZER_ORGANISM_ID_V1(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflow_id,
            data_state,
        )

    if (
        workflow_id != _organism_identification_strategy_id()
        or not _organism_identification_supported(
            sample_type,
            sequencing,
            read_type,
            data_state,
        )
    ):
        return None

    external_inputs = ["reference_genome_sketch_database"]
    steps = []

    if data_state == RAW_READS:
        external_inputs.extend(_raw_input_artifacts(sequencing))
        steps.extend(_build_raw_prefix(sequencing, read_type))
    else:
        external_inputs.append("eukaryotic_genome_fasta")

    steps.append({
        "operation": "genome_identification",
        "name": "Closest reference genome and lineage search",
        "description": (
            "Sketch the assembled eukaryotic genome and search it against a "
            "curated broad reference-sketch collection with sourmash. Report "
            "the closest available references, containment/similarity evidence "
            "and their taxonomy; do not convert a weak or absent match into an "
            "exact species claim."
        ),
        "mode": "sequential",
        "min_successful_candidates": 1,
        "candidates": ["sourmash_eukaryotic"],
    })

    return {
        "id": workflow_id,
        "name": "Eukaryotic organism identification — closest reference match",
        "description": (
            "Determine the closest indexed reference and taxonomic lineage for "
            "an eukaryotic genome. This route is reference-database limited and "
            "is deliberately not presented as an unconditional exact species call."
        ),
        "context": {
            "sample_type": EUKARYOTIC,
            "sequencing": sequencing,
            "read_type": read_type,
            "goal": goal,
        },
        "external_inputs": list(dict.fromkeys(external_inputs)),
        "steps": steps,
        "dynamic_route": True,
        "route_class": "artifact_target_planned",
        "planning_basis": (
            "assembled genome + broad reference-sketch comparison + "
            "dependency validation"
        ),
        "planner_version": PLANNER_VERSION,
        "goal_target_artifact": "organism_identification_report",
        "target_operation": "genome_identification",
        "decision_points": [],
        "data_state": data_state,
    }
