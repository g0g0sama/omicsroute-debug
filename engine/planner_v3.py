from __future__ import annotations

import re
from typing import Any

from engine.context_intake import RAW_READS
from engine.planner_v2 import (
    EUKARYOTIC,
    HYBRID_ONT,
    HYBRID_PACBIO,
    ONT,
    PACBIO,
    _assembly_steps,
    _hybrid_decision_points,
    _hybrid_post_assembly_steps,
    _long_read_steps,
    _short_read_steps,
)

PLANNER_VERSION = "3.0-target-artifact-foundation"

GENOME_ASSEMBLY = "Genome assembly"
GENOME_QUALITY = "Genome quality assessment"
CONTAMINATION_SCREENING = "Contamination screening"
REPEAT_ANNOTATION = "Repeat annotation"
GENE_PREDICTION = "Gene prediction"
FUNCTIONAL_ANNOTATION = "Functional annotation"

SUPPORTED_GOALS = [
    GENOME_ASSEMBLY,
    GENOME_QUALITY,
    CONTAMINATION_SCREENING,
    REPEAT_ANNOTATION,
    GENE_PREDICTION,
    FUNCTIONAL_ANNOTATION,
]

_HYBRID_CONTEXTS = {
    (HYBRID_ONT, "Paired-end + Long reads"),
    (HYBRID_PACBIO, "Paired-end + Long reads"),
}

_GOAL_SPECS: dict[str, dict[str, Any]] = {
    GENOME_ASSEMBLY: {
        "target_operation": "hybrid_genome_assembly",
        "target_artifact": "eukaryotic_genome_fasta",
        "description": (
            "Build a de novo hybrid eukaryotic genome assembly and stop once "
            "the genome FASTA has been produced."
        ),
    },
    CONTAMINATION_SCREENING: {
        "target_operation": "contamination_screening",
        "target_artifact": "contamination_screening_report",
        "description": (
            "Build the hybrid assembly, perform initial assembly QC, and "
            "screen for contaminant/cobiont sequence."
        ),
    },
    GENOME_QUALITY: {
        "target_operation": "genome_quality_assessment",
        "target_artifact": "genome_completeness_report",
        "description": (
            "Build and evaluate the genome through assembly QC, contamination "
            "screening and lineage-aware completeness assessment."
        ),
    },
    REPEAT_ANNOTATION: {
        "target_operation": "repeat_annotation",
        "target_artifact": "repeat_annotation_gff",
        "description": (
            "Build and quality-check the genome, discover repeats/TEs, and "
            "produce a repeat-masked genome plus repeat annotation."
        ),
    },
    GENE_PREDICTION: {
        "target_operation": "gene_prediction",
        "target_artifact": "eukaryotic_gene_annotation_gff",
        "description": (
            "Build and quality-check the genome, handle repeats, and produce "
            "structural gene models plus predicted proteins."
        ),
    },
    FUNCTIONAL_ANNOTATION: {
        "target_operation": "functional_annotation",
        "target_artifact": "functional_annotation_table",
        "description": (
            "Continue the artifact path through structural gene annotation to "
            "protein functional annotation."
        ),
    },
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def supports_target_artifact_context(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
    goal: str | None = None,
) -> bool:
    if sample_type != EUKARYOTIC:
        return False
    if data_state != RAW_READS:
        return False
    if (sequencing, read_type) not in _HYBRID_CONTEXTS:
        return False
    if goal is not None and goal not in _GOAL_SPECS:
        return False
    return True


def get_target_artifact_goal_options(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
) -> list[str]:
    if not supports_target_artifact_context(
        sample_type, sequencing, read_type, data_state
    ):
        return []
    return list(SUPPORTED_GOALS)


def _strategy_id(goal: str, mode: str) -> str:
    return f"planner3__eukaryotic_genome__{_slug(goal)}__{_slug(mode)}"


def _strategy_modes(goal: str) -> list[str]:
    if goal in {GENE_PREDICTION, FUNCTIONAL_ANNOTATION}:
        return ["evidence_guided", "genome_only"]
    return ["target_artifact"]


def get_target_artifact_workflow_strategies(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    data_state: str,
) -> list[dict]:
    if not supports_target_artifact_context(
        sample_type, sequencing, read_type, data_state, goal
    ):
        return []

    spec = _GOAL_SPECS[goal]
    results = []

    for mode in _strategy_modes(goal):
        if mode == "evidence_guided":
            name = f"{goal} — evidence-guided structural annotation"
            description = (
                spec["description"]
                + " Uses homologous protein evidence for structural annotation."
            )
        elif mode == "genome_only":
            name = f"{goal} — genome-only structural annotation fallback"
            description = (
                spec["description"]
                + " Uses the genome-only BRAKER4 fallback when external "
                "protein evidence is unavailable."
            )
        else:
            name = f"{goal} — target-artifact route"
            description = spec["description"]

        results.append(
            {
                "id": _strategy_id(goal, mode),
                "name": name,
                "description": description,
                "dynamic": True,
                "route_class": "artifact_target_planned",
                "planner_version": PLANNER_VERSION,
                "goal_target_artifact": spec["target_artifact"],
            }
        )

    return results


def _build_hybrid_prefix(sequencing: str, read_type: str) -> list[dict]:
    steps: list[dict] = []
    steps.extend(_short_read_steps())

    if sequencing == HYBRID_ONT:
        steps.extend(_long_read_steps(ONT, include_filtering=True))
    else:
        steps.extend(_long_read_steps(PACBIO, include_filtering=False))

    steps.extend(_assembly_steps(sequencing, read_type))
    return steps


def _slice_to_operation(steps: list[dict], target_operation: str) -> list[dict]:
    result = []
    for step in steps:
        result.append(step)
        if step.get("operation") == target_operation:
            return result
    raise ValueError(
        f"Target operation '{target_operation}' is missing from hybrid graph."
    )


def _decision_points_for(
    sequencing: str,
    included_operations: set[str],
) -> list[dict]:
    result = []
    for point in _hybrid_decision_points(sequencing):
        point_id = point.get("id")
        if point_id in {
            "assembly_polishing",
            "haplotig_reduction",
            "pacbio_read_chemistry",
        }:
            result.append(point)
        elif (
            point_id == "contamination_response"
            and "contamination_screening" in included_operations
        ):
            result.append(point)
    return result


def materialize_target_artifact_workflow(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    workflow_id: str | None,
    data_state: str,
) -> dict | None:
    if not supports_target_artifact_context(
        sample_type, sequencing, read_type, data_state, goal
    ):
        return None

    mode_lookup = {
        _strategy_id(goal, mode): mode
        for mode in _strategy_modes(goal)
    }
    mode = mode_lookup.get(str(workflow_id or ""))
    if mode is None:
        return None

    spec = _GOAL_SPECS[goal]
    evidence_guided = mode == "evidence_guided"

    steps = _build_hybrid_prefix(sequencing, read_type)

    if goal != GENOME_ASSEMBLY:
        steps.extend(
            _slice_to_operation(
                _hybrid_post_assembly_steps(
                    evidence_guided=evidence_guided
                ),
                spec["target_operation"],
            )
        )

    operations = {
        step.get("operation")
        for step in steps
        if step.get("operation")
    }

    external_inputs = ["raw_paired_fastq", "raw_long_fastq"]

    if "genome_quality_assessment" in operations:
        external_inputs.append("busco_lineage_database")

    if evidence_guided and "gene_prediction" in operations:
        external_inputs.append("protein_evidence_fasta")

    if "functional_annotation" in operations:
        external_inputs.append("orthology_database")

    long_platform = ONT if sequencing == HYBRID_ONT else PACBIO

    route_suffix = (
        "evidence-guided route"
        if mode == "evidence_guided"
        else "genome-only fallback route"
        if mode == "genome_only"
        else "target-artifact route"
    )

    return {
        "id": workflow_id,
        "name": f"Eukaryotic hybrid {goal.lower()} — {route_suffix}",
        "description": spec["description"],
        "context": {
            "sample_type": EUKARYOTIC,
            "sequencing": ["Illumina", long_platform],
            "read_type": ["Paired-end", "Long reads"],
            "goal": goal,
        },
        "external_inputs": list(dict.fromkeys(external_inputs)),
        "steps": steps,
        "dynamic_route": True,
        "route_class": "artifact_target_planned",
        "planning_basis": (
            "current artifacts + requested target artifact + "
            "platform-aware operation graph + dependency validation"
        ),
        "planner_version": PLANNER_VERSION,
        "goal_target_artifact": spec["target_artifact"],
        "target_operation": spec["target_operation"],
        "decision_points": _decision_points_for(
            sequencing,
            operations,
        ),
        "data_state": data_state,
    }
