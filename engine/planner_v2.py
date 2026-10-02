
from __future__ import annotations

import re

from engine.context_intake import (
    RAW_READS,
    GENOME_ASSEMBLY,
    PREDICTED_PROTEINS,
)


EUKARYOTIC = "Eukaryotic genome"
ILLUMINA = "Illumina"
ONT = "Oxford Nanopore"
PACBIO = "PacBio"

HYBRID_ONT = "Illumina + Oxford Nanopore"
HYBRID_PACBIO = "Illumina + PacBio"

FUNCTIONAL_ANNOTATION = "Functional annotation"

PLANNER_VERSION = "2.4-complete-hybrid-blueprint"

_SUPPORTED_RAW_CONTEXTS = {
    (ILLUMINA, "Paired-end"),
    (ONT, "Long reads"),
    (PACBIO, "Long reads"),
    (HYBRID_ONT, "Paired-end + Long reads"),
    (HYBRID_PACBIO, "Paired-end + Long reads"),
}

_EVIDENCE_BASIS = [
    {
        "kind": "official_documentation",
        "resource": "MaSuRCA",
        "url": "https://github.com/alekseyzimin/masurca",
        "supports": (
            "Illumina-only and Illumina + ONT/PacBio eukaryotic genome "
            "assembly routes."
        ),
    },
    {
        "kind": "official_documentation",
        "resource": "Wengan",
        "url": "https://github.com/adigenova/wengan",
        "supports": (
            "Hybrid Illumina + Oxford Nanopore/PacBio eukaryotic "
            "genome assembly."
        ),
    },
    {
        "kind": "official_documentation",
        "resource": "BRAKER4",
        "url": "https://github.com/Gaius-Augustus/BRAKER4",
        "supports": (
            "Repeat masking plus genome-only (ES) and evidence-guided "
            "eukaryotic structural gene annotation."
        ),
    },
    {
        "kind": "official_documentation",
        "resource": "eggNOG-mapper",
        "url": "https://github.com/eggnogdb/eggnog-mapper",
        "supports": (
            "Orthology-based functional annotation of predicted proteins."
        ),
    },
]


def _slug(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value).lower(),
    ).strip("_")


def get_planner_sequencing_options(sample_type: str) -> list[str]:
    if sample_type != EUKARYOTIC:
        return []

    return [
        ILLUMINA,
        ONT,
        PACBIO,
        HYBRID_ONT,
        HYBRID_PACBIO,
    ]


def get_planner_read_type_options(
    sample_type: str,
    sequencing: str,
) -> list[str]:
    if sample_type != EUKARYOTIC:
        return []

    if sequencing == ILLUMINA:
        return ["Paired-end"]

    if sequencing in {ONT, PACBIO}:
        return ["Long reads"]

    if sequencing in {HYBRID_ONT, HYBRID_PACBIO}:
        return ["Paired-end + Long reads"]

    return []


def planner_supports_context(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
    goal: str,
) -> bool:
    if sample_type != EUKARYOTIC:
        return False

    if goal != FUNCTIONAL_ANNOTATION:
        return False

    if data_state == GENOME_ASSEMBLY:
        return True

    if data_state == PREDICTED_PROTEINS:
        return False

    if data_state != RAW_READS:
        return False

    return (sequencing, read_type) in _SUPPORTED_RAW_CONTEXTS


def get_planner_goal_options(
    sample_type: str,
    sequencing: str,
    read_type: str,
    data_state: str,
) -> list[str]:
    if sample_type != EUKARYOTIC:
        return []

    if data_state == GENOME_ASSEMBLY:
        return [FUNCTIONAL_ANNOTATION]

    if data_state == RAW_READS and (
        sequencing,
        read_type,
    ) in _SUPPORTED_RAW_CONTEXTS:
        return [FUNCTIONAL_ANNOTATION]

    return []


def _strategy_id(mode: str) -> str:
    return (
        "planner2__eukaryotic_genome__"
        "functional_annotation__"
        f"{_slug(mode)}"
    )


def get_planner_workflow_strategies(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    data_state: str,
) -> list[dict]:
    if not planner_supports_context(
        sample_type,
        sequencing,
        read_type,
        data_state,
        goal,
    ):
        return []

    return [
        {
            "id": _strategy_id("evidence_guided"),
            "name": (
                "Complete eukaryotic functional annotation — "
                "evidence-guided structural annotation"
            ),
            "description": (
                "Build the required upstream route from the data you have: "
                "read QC/assembly when needed, assembly assessment, repeat "
                "handling, BRAKER4 protein-evidence gene prediction, then "
                "functional annotation. Requires homologous protein evidence "
                "for the structural-annotation stage."
            ),
            "dynamic": True,
            "route_class": "artifact_planned",
            "planner_version": PLANNER_VERSION,
        },
        {
            "id": _strategy_id("genome_only"),
            "name": (
                "Complete eukaryotic functional annotation — "
                "genome-only fallback"
            ),
            "description": (
                "Build the same complete upstream route, but use BRAKER4 "
                "genome-only/ES structural annotation when external gene "
                "evidence is unavailable. This is a fallback and should be "
                "interpreted more cautiously than evidence-guided annotation."
            ),
            "dynamic": True,
            "route_class": "artifact_planned",
            "planner_version": PLANNER_VERSION,
        },
    ]


def should_suppress_legacy_functional_route(
    sample_type: str,
    data_state: str,
    goal: str,
) -> bool:
    """
    Legacy eukaryotic functional-annotation entries start from predicted
    proteins even when their workflow context looks like raw sequencing data.
    They are valid only when the user's actual starting state is proteins.
    """
    return (
        sample_type == EUKARYOTIC
        and goal == FUNCTIONAL_ANNOTATION
        and data_state != PREDICTED_PROTEINS
    )


def _short_read_steps() -> list[dict]:
    return [
        {
            "operation": "raw_read_qc",
            "name": "Illumina read quality control",
            "description": (
                "Inspect raw Illumina read quality before genome reconstruction."
            ),
            "context": {
                "sequencing": ILLUMINA,
                "read_type": "Paired-end",
            },
            "candidates": ["fastqc"],
        },
        {
            "operation": "read_preprocessing",
            "name": "Illumina read preprocessing",
            "description": (
                "Remove adapters and low-quality sequence when indicated by QC."
            ),
            "context": {
                "sequencing": ILLUMINA,
                "read_type": "Paired-end",
            },
            "candidates": ["fastp"],
        },
    ]


def _long_read_steps(
    sequencing: str,
    include_filtering: bool,
) -> list[dict]:
    steps = [
        {
            "operation": "raw_read_qc",
            "name": f"{sequencing} read quality control",
            "description": (
                "Inspect long-read length and quality distributions before "
                "genome reconstruction."
            ),
            "context": {
                "sequencing": sequencing,
                "read_type": "Long reads",
            },
            "candidates": ["nanoplot"],
        },
    ]

    if include_filtering:
        steps.append(
            {
                "operation": "read_preprocessing",
                "name": f"{sequencing} read preprocessing",
                "description": (
                    "Apply quality/length filtering only when the QC profile "
                    "shows that filtering is warranted."
                ),
                "context": {
                    "sequencing": sequencing,
                    "read_type": "Long reads",
                },
                "candidates": ["chopper", "filtlong"],
            }
        )

    return steps


def _assembly_steps(
    sequencing: str,
    read_type: str,
) -> list[dict]:
    if sequencing == ILLUMINA:
        return [
            {
                "operation": "genome_assembly",
                "name": "Illumina eukaryotic genome assembly",
                "description": (
                    "Assemble paired-end Illumina genomic reads with MaSuRCA. "
                    "For large/repetitive genomes, short-read-only assemblies "
                    "may be fragmented; long-read or hybrid data can improve "
                    "continuity."
                ),
                "context": {
                    "sequencing": ILLUMINA,
                    "read_type": "Paired-end",
                },
                "candidates": ["masurca"],
            }
        ]

    if sequencing == ONT:
        return [
            {
                "operation": "genome_assembly",
                "name": "Oxford Nanopore eukaryotic genome assembly",
                "description": (
                    "Construct a long-read genome assembly. Flye is the "
                    "general ONT route in this planner foundation."
                ),
                "context": {
                    "sequencing": ONT,
                    "read_type": "Long reads",
                },
                "candidates": ["flye"],
            }
        ]

    if sequencing == PACBIO:
        return [
            {
                "operation": "genome_assembly",
                "name": "PacBio HiFi eukaryotic genome assembly",
                "description": (
                    "Construct a PacBio HiFi genome assembly with hifiasm."
                ),
                "context": {
                    "sequencing": PACBIO,
                    "read_type": "Long reads",
                },
                "candidates": ["hifiasm"],
            }
        ]

    if sequencing in {HYBRID_ONT, HYBRID_PACBIO}:
        long_platform = (
            ONT if sequencing == HYBRID_ONT else PACBIO
        )
        return [
            {
                "operation": "hybrid_genome_assembly",
                "name": (
                    f"Illumina + {long_platform} hybrid "
                    "eukaryotic genome assembly"
                ),
                "description": (
                    "Combine paired-end Illumina reads with matched long reads. "
                    "MaSuRCA and Wengan are curated alternatives for "
                    "Illumina + ONT/PacBio hybrid eukaryotic assembly; "
                    "ranking remains separate from compatibility."
                ),
                "context": {
                    "sequencing": [ILLUMINA, long_platform],
                    "read_type": ["Paired-end", "Long reads"],
                },
                "candidates": ["masurca", "wengan"],
            }
        ]

    return []


def _post_assembly_steps(
    evidence_guided: bool,
) -> list[dict]:
    gene_description = (
        "Predict gene structures with BRAKER4 in protein-evidence (EP) mode "
        "from the repeat-masked genome."
        if evidence_guided
        else
        "Predict gene structures with BRAKER4 genome-only/ES mode. This is "
        "a fallback when external transcript/protein evidence is unavailable "
        "and generally has lower confidence than evidence-guided annotation."
    )

    return [
        {
            "operation": "assembly_qc",
            "name": "Assembly structural quality assessment",
            "description": (
                "Review assembly statistics and fragmentation before annotation."
            ),
            "candidates": ["quast"],
        },
        {
            "operation": "genome_quality_assessment",
            "name": "Assembly completeness assessment",
            "description": (
                "Estimate biological completeness with an appropriate BUSCO "
                "lineage before downstream annotation."
            ),
            "candidates": ["busco"],
        },
        {
            "operation": "repeat_discovery",
            "name": "De novo repeat discovery",
            "description": (
                "Construct a species-specific repeat library from the assembled "
                "eukaryotic genome."
            ),
            "candidates": ["repeatmodeler"],
        },
        {
            "operation": "repeat_annotation",
            "name": "Repeat annotation and masking",
            "description": (
                "Mask repetitive regions before structural gene prediction."
            ),
            "candidates": ["repeatmasker"],
        },
        {
            "operation": "gene_prediction",
            "name": "Structural gene annotation",
            "description": gene_description,
            "candidates": ["braker4"],
        },
        {
            "operation": "functional_annotation",
            "name": "Protein functional annotation",
            "description": (
                "Annotate the predicted protein set with eggNOG-mapper and "
                "retain orthology, GO/KEGG and related functional assignments "
                "for downstream interpretation."
            ),
            "candidates": ["eggnog_mapper"],
        },
    ]


def _hybrid_post_assembly_steps(
    evidence_guided: bool,
) -> list[dict]:
    gene_description = (
        "Predict gene structures with BRAKER4 in protein-evidence (EP) mode "
        "from the repeat-masked genome."
        if evidence_guided
        else
        "Predict gene structures with BRAKER4 genome-only/ES mode. This is "
        "a fallback when external transcript/protein evidence is unavailable "
        "and should be interpreted more cautiously than evidence-guided "
        "annotation."
    )

    return [
        {
            "operation": "assembly_qc",
            "name": "Complementary assembly quality assessment",
            "description": (
                "Run structural assembly statistics and Illumina k-mer-based "
                "reference-free quality assessment. QUAST and Merqury answer "
                "different QC questions and are intentionally co-executed."
            ),
            "mode": "parallel",
            "min_successful_candidates": 2,
            "candidates": ["quast", "merqury"],
        },
        {
            "operation": "contamination_screening",
            "name": "Assembly contamination / cobiont screening",
            "description": (
                "Screen the assembly for contaminant or cobiont sequence before "
                "committing to downstream structural and functional annotation. "
                "Positive findings should trigger curation and re-QC."
            ),
            "candidates": ["blobtoolkit"],
        },
        {
            "operation": "genome_quality_assessment",
            "name": "Assembly completeness assessment",
            "description": (
                "Estimate biological completeness with an appropriate BUSCO "
                "lineage after initial assembly QC."
            ),
            "candidates": ["busco"],
        },
        {
            "operation": "repeat_discovery",
            "name": "De novo repeat / TE library discovery",
            "description": (
                "Construct a species-specific repeat library. RepeatModeler "
                "and EDTA are alternative curated strategies; EDTA provides a "
                "more TE-focused integrated route."
            ),
            "candidates": ["repeatmodeler", "edta"],
        },
        {
            "operation": "repeat_annotation",
            "name": "Repeat annotation and masking",
            "description": (
                "Mask repetitive regions before structural gene prediction."
            ),
            "candidates": ["repeatmasker"],
        },
        {
            "operation": "gene_prediction",
            "name": "Structural gene annotation",
            "description": gene_description,
            "candidates": ["braker4"],
        },
        {
            "operation": "functional_annotation",
            "name": "Complementary protein functional annotation",
            "description": (
                "Run orthology-based eggNOG-mapper together with domain/family "
                "annotation from InterProScan. They provide complementary "
                "functional evidence rather than interchangeable answers."
            ),
            "mode": "parallel",
            "min_successful_candidates": 2,
            "candidates": ["eggnog_mapper", "interproscan"],
        },
    ]


def _hybrid_decision_points(
    sequencing: str,
) -> list[dict]:
    long_platform = ONT if sequencing == HYBRID_ONT else PACBIO

    decisions = [
        {
            "id": "assembly_polishing",
            "title": "Do residual consensus errors justify extra polishing?",
            "status": "context_dependent",
            "when": (
                "Consider after assembly when k-mer/QV or read-alignment QC "
                "suggests residual base-level errors."
            ),
            "why": (
                "Polishing is not universally inserted because hybrid assemblers "
                "already use accurate short reads differently, and unnecessary "
                "polishing can waste compute or alter a high-quality consensus."
            ),
            "suggested_tools": ["NextPolish"],
            "evidence": [
                {
                    "label": "NextPolish official documentation",
                    "url": "https://github.com/Nextomics/NextPolish",
                }
            ],
        },
        {
            "id": "haplotig_reduction",
            "title": "Is the assembly carrying uncollapsed haplotigs?",
            "status": "context_dependent",
            "when": (
                "Consider for diploid/heterozygous genomes when duplicated BUSCO, "
                "coverage or k-mer spectra suggest allelic redundancy."
            ),
            "why": (
                "Haplotig purging is not a universal step; over-purging can remove "
                "real biological sequence."
            ),
            "suggested_tools": ["purge_dups"],
            "evidence": [
                {
                    "label": "purge_dups official documentation",
                    "url": "https://github.com/dfguan/purge_dups",
                }
            ],
        },
        {
            "id": "contamination_response",
            "title": "Did contamination screening flag suspect contigs?",
            "status": "decision_gate",
            "when": (
                "If BlobToolKit identifies contaminant/cobiont sequence, curate "
                "the assembly and repeat QC/BUSCO before annotation."
            ),
            "why": (
                "Downstream annotation should be performed on the curated target "
                "assembly rather than silently propagating suspect contigs."
            ),
            "suggested_tools": ["BlobToolKit"],
            "evidence": [
                {
                    "label": "BlobToolKit official documentation",
                    "url": "https://github.com/genomehubs/blobtoolkit",
                }
            ],
        },
    ]

    if long_platform == PACBIO:
        decisions.insert(
            0,
            {
                "id": "pacbio_read_chemistry",
                "title": "Which PacBio read chemistry is this?",
                "status": "needs_input",
                "when": (
                    "Resolve HiFi/CCS versus CLR before choosing any additional "
                    "polishing or long-read-specific refinement."
                ),
                "why": (
                    "PacBio HiFi and older noisy CLR data have different error "
                    "profiles and should not share one blind polishing recipe."
                ),
                "suggested_tools": [],
                "evidence": [
                    {
                        "label": "NextPolish documentation notes a separate HiFi path",
                        "url": "https://github.com/Nextomics/NextPolish",
                    }
                ],
            },
        )

    return decisions


def _raw_input_artifacts(
    sequencing: str,
) -> list[str]:
    if sequencing == ILLUMINA:
        return ["raw_paired_fastq"]

    if sequencing in {ONT, PACBIO}:
        return ["raw_long_fastq"]

    if sequencing in {HYBRID_ONT, HYBRID_PACBIO}:
        return [
            "raw_paired_fastq",
            "raw_long_fastq",
        ]

    return []


def _workflow_context(
    sequencing: str,
    read_type: str,
) -> dict:
    if sequencing == HYBRID_ONT:
        return {
            "sample_type": EUKARYOTIC,
            "sequencing": [ILLUMINA, ONT],
            "read_type": ["Paired-end", "Long reads"],
            "goal": FUNCTIONAL_ANNOTATION,
        }

    if sequencing == HYBRID_PACBIO:
        return {
            "sample_type": EUKARYOTIC,
            "sequencing": [ILLUMINA, PACBIO],
            "read_type": ["Paired-end", "Long reads"],
            "goal": FUNCTIONAL_ANNOTATION,
        }

    return {
        "sample_type": EUKARYOTIC,
        "sequencing": sequencing,
        "read_type": read_type,
        "goal": FUNCTIONAL_ANNOTATION,
    }


def materialize_planner_workflow(
    sample_type: str,
    sequencing: str,
    read_type: str,
    goal: str,
    workflow_id: str | None,
    data_state: str,
) -> dict | None:
    if workflow_id not in {
        _strategy_id("evidence_guided"),
        _strategy_id("genome_only"),
    }:
        return None

    if not planner_supports_context(
        sample_type,
        sequencing,
        read_type,
        data_state,
        goal,
    ):
        return None

    evidence_guided = (
        workflow_id == _strategy_id("evidence_guided")
    )

    steps: list[dict] = []
    external_inputs: list[str] = []

    if data_state == RAW_READS:
        external_inputs.extend(
            _raw_input_artifacts(sequencing)
        )

        if sequencing == ILLUMINA:
            steps.extend(_short_read_steps())

        elif sequencing == ONT:
            steps.extend(
                _long_read_steps(
                    ONT,
                    include_filtering=True,
                )
            )

        elif sequencing == PACBIO:
            steps.extend(
                _long_read_steps(
                    PACBIO,
                    include_filtering=False,
                )
            )

        elif sequencing == HYBRID_ONT:
            steps.extend(_short_read_steps())
            steps.extend(
                _long_read_steps(
                    ONT,
                    include_filtering=True,
                )
            )

        elif sequencing == HYBRID_PACBIO:
            steps.extend(_short_read_steps())
            steps.extend(
                _long_read_steps(
                    PACBIO,
                    include_filtering=False,
                )
            )

        steps.extend(
            _assembly_steps(
                sequencing,
                read_type,
            )
        )

    elif data_state == GENOME_ASSEMBLY:
        external_inputs.append(
            "eukaryotic_genome_fasta"
        )

    external_inputs.extend(
        [
            "busco_lineage_database",
            "orthology_database",
        ]
    )

    if evidence_guided:
        external_inputs.append(
            "protein_evidence_fasta"
        )

    if (
        data_state == RAW_READS
        and sequencing in {HYBRID_ONT, HYBRID_PACBIO}
    ):
        steps.extend(
            _hybrid_post_assembly_steps(
                evidence_guided=evidence_guided
            )
        )
    else:
        steps.extend(
            _post_assembly_steps(
                evidence_guided=evidence_guided
            )
        )

    decision_points = (
        _hybrid_decision_points(sequencing)
        if (
            data_state == RAW_READS
            and sequencing in {HYBRID_ONT, HYBRID_PACBIO}
        )
        else []
    )

    return {
        "id": workflow_id,
        "name": (
            "Eukaryotic functional annotation — complete "
            + (
                "evidence-guided route"
                if evidence_guided
                else
                "genome-only fallback route"
            )
        ),
        "description": (
            "Artifact-planned end-to-end route from the user's actual "
            "starting data to a functional annotation table. Upstream "
            "operations are not skipped merely because the terminal "
            "annotation tool is known."
        ),
        "context": _workflow_context(
            sequencing,
            read_type,
        ),
        "external_inputs": list(
            dict.fromkeys(external_inputs)
        ),
        "steps": steps,
        "dynamic_route": True,
        "route_class": "artifact_planned",
        "planning_basis": (
            "goal blueprint + artifact/dependency graph + "
            "platform-aware assembly route"
        ),
        "planner_version": PLANNER_VERSION,
        "goal_target_artifact": "functional_annotation_table",
        "evidence_basis": _EVIDENCE_BASIS,
        "decision_points": decision_points,
        "data_state": data_state,
    }
