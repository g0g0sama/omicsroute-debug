
from __future__ import annotations

from engine.recommender import (
    build_workflow,
    get_goal_options,
    get_read_type_options,
    get_sequencing_options,
    get_workflow_strategies,
)
from engine.dependencies import validate_workflow


GOAL = "Functional annotation"
SAMPLE = "Eukaryotic genome"


CASES = [
    (
        "Illumina",
        "Paired-end",
        [
            "raw_read_qc",
            "read_preprocessing",
            "genome_assembly",
            "assembly_qc",
            "genome_quality_assessment",
            "repeat_discovery",
            "repeat_annotation",
            "gene_prediction",
            "functional_annotation",
        ],
    ),
    (
        "Oxford Nanopore",
        "Long reads",
        [
            "raw_read_qc",
            "read_preprocessing",
            "genome_assembly",
            "assembly_qc",
            "genome_quality_assessment",
            "repeat_discovery",
            "repeat_annotation",
            "gene_prediction",
            "functional_annotation",
        ],
    ),
    (
        "PacBio",
        "Long reads",
        [
            "raw_read_qc",
            "genome_assembly",
            "assembly_qc",
            "genome_quality_assessment",
            "repeat_discovery",
            "repeat_annotation",
            "gene_prediction",
            "functional_annotation",
        ],
    ),
    (
        "Illumina + Oxford Nanopore",
        "Paired-end + Long reads",
        [
            "hybrid_genome_assembly",
            "assembly_qc",
            "genome_quality_assessment",
            "repeat_discovery",
            "repeat_annotation",
            "gene_prediction",
            "functional_annotation",
        ],
    ),
    (
        "Illumina + PacBio",
        "Paired-end + Long reads",
        [
            "hybrid_genome_assembly",
            "assembly_qc",
            "genome_quality_assessment",
            "repeat_discovery",
            "repeat_annotation",
            "gene_prediction",
            "functional_annotation",
        ],
    ),
]


def assert_subsequence(values, expected):
    pos = 0
    for value in values:
        if pos < len(expected) and value == expected[pos]:
            pos += 1
    assert pos == len(expected), (
        f"Missing expected ordered subsequence.\n"
        f"Expected: {expected}\nActual: {values}"
    )


def main():
    seq_options = get_sequencing_options(SAMPLE)
    assert "Illumina + PacBio" in seq_options, seq_options

    for sequencing, read_type, required_ops in CASES:
        reads = get_read_type_options(SAMPLE, sequencing)
        assert read_type in reads, (sequencing, reads)

        goals = get_goal_options(
            SAMPLE,
            sequencing,
            read_type,
            data_state="raw_reads",
        )
        assert GOAL in goals, (sequencing, goals)

        strategies = get_workflow_strategies(
            SAMPLE,
            sequencing,
            read_type,
            GOAL,
            data_state="raw_reads",
        )

        planner_ids = [
            item["id"]
            for item in strategies
            if str(item.get("id", "")).startswith(
                ("planner2__", "planner3__")
            )
        ]

        assert len(planner_ids) == 2, (
            sequencing,
            strategies,
        )

        # The old direct-protein route must not be exposed from raw reads.
        assert not any(
            item.get("id") == "eukaryotic_genome_functional_annotation"
            for item in strategies
        ), strategies

        for workflow_id in planner_ids:
            workflow = build_workflow(
                SAMPLE,
                sequencing,
                read_type,
                GOAL,
                workflow_id=workflow_id,
                data_state="raw_reads",
                compute_profile={"enabled": False},
            )
            assert workflow is not None, workflow_id

            operations = [
                step["operation"]
                for step in workflow["steps"]
            ]
            assert_subsequence(
                operations,
                required_ops,
            )

            assert operations[-1] == "functional_annotation"
            assert operations.count("gene_prediction") == 1
            assert "repeat_annotation" in operations

            report = validate_workflow(
                workflow["id"],
                workflow_override={
                    "id": workflow["id"],
                    "name": workflow["name"],
                    "context": workflow["context"],
                    "external_inputs": workflow["external_inputs"],
                    "steps": [
                        {
                            "operation": step["operation"],
                            "name": step["name"],
                            "candidates": step["candidate_ids"],
                            "context": step.get("context", {}),
                        }
                        for step in workflow["steps"]
                    ],
                },
            )
            assert report["valid"], (
                sequencing,
                workflow_id,
                report,
            )

    # Starting from an assembly should skip read QC and assembly.
    strategies = get_workflow_strategies(
        SAMPLE,
        "Existing data",
        "Not applicable",
        GOAL,
        data_state="genome_assembly",
    )
    planner_id = next(
        item["id"]
        for item in strategies
        if item["id"].endswith("evidence_guided")
    )
    workflow = build_workflow(
        SAMPLE,
        "Existing data",
        "Not applicable",
        GOAL,
        workflow_id=planner_id,
        data_state="genome_assembly",
        compute_profile={"enabled": False},
    )
    operations = [step["operation"] for step in workflow["steps"]]
    assert "genome_assembly" not in operations
    assert "raw_read_qc" not in operations
    assert operations[-1] == "functional_annotation"

    print("=" * 78)
    print("RESULT: PASS")
    print("Eukaryotic functional-annotation foundation remains valid across Planner v2 and Planner v3 routes.")
    print("Validated:")
    print("- Illumina paired-end raw reads")
    print("- Oxford Nanopore raw long reads")
    print("- PacBio raw long reads")
    print("- Illumina + Oxford Nanopore hybrid")
    print("- Illumina + PacBio hybrid")
    print("- existing genome assembly")
    print("- no direct eggNOG/protein-only shortcut from raw reads")
    print("=" * 78)


if __name__ == "__main__":
    main()
