from engine.dependencies import validate_workflow
from engine.recommender import (
    build_workflow,
    get_goal_options,
    get_workflow_strategies,
)

SAMPLE = "Eukaryotic genome"
READ_TYPE = "Paired-end + Long reads"
DATA_STATE = "raw_reads"

EXPECTED = {
    "Genome assembly": ("hybrid_genome_assembly", "eukaryotic_genome_fasta"),
    "Contamination screening": (
        "contamination_screening",
        "contamination_screening_report",
    ),
    "Genome quality assessment": (
        "genome_quality_assessment",
        "genome_completeness_report",
    ),
    "Repeat annotation": ("repeat_annotation", "repeat_annotation_gff"),
    "Gene prediction": ("gene_prediction", "eukaryotic_gene_annotation_gff"),
    "Functional annotation": (
        "functional_annotation",
        "functional_annotation_table",
    ),
}


def main():
    for sequencing in [
        "Illumina + Oxford Nanopore",
        "Illumina + PacBio",
    ]:
        goals = get_goal_options(
            SAMPLE,
            sequencing,
            READ_TYPE,
            data_state=DATA_STATE,
        )

        assert "Hybrid genome assembly" not in goals, (
            sequencing,
            goals,
        )

        for goal, (last_operation, target_artifact) in EXPECTED.items():
            assert goal in goals, (sequencing, goal, goals)

            strategies = get_workflow_strategies(
                SAMPLE,
                sequencing,
                READ_TYPE,
                goal,
                data_state=DATA_STATE,
            )

            expected_count = (
                2
                if goal in {"Gene prediction", "Functional annotation"}
                else 1
            )
            assert len(strategies) == expected_count, (
                sequencing,
                goal,
                strategies,
            )
            assert all(
                item["id"].startswith("planner3__")
                for item in strategies
            )

            for strategy in strategies:
                workflow = build_workflow(
                    SAMPLE,
                    sequencing,
                    READ_TYPE,
                    goal,
                    workflow_id=strategy["id"],
                    data_state=DATA_STATE,
                    compute_profile={"enabled": False},
                )

                assert workflow is not None
                assert workflow["planner_version"] == (
                    "3.1-all-eukaryotic-contexts"
                )
                assert workflow["goal_target_artifact"] == target_artifact

                operations = [
                    step["operation"]
                    for step in workflow["steps"]
                ]
                assert operations[-1] == last_operation, (
                    sequencing,
                    goal,
                    operations,
                )

                if goal == "Genome assembly":
                    assert "assembly_qc" not in operations
                    assert "functional_annotation" not in operations

                if goal == "Contamination screening":
                    assert "genome_quality_assessment" not in operations

                if goal == "Genome quality assessment":
                    assert "repeat_discovery" not in operations

                if goal == "Repeat annotation":
                    assert "gene_prediction" not in operations

                if goal == "Gene prediction":
                    assert "functional_annotation" not in operations

                report = validate_workflow(
                    workflow["id"],
                    workflow_override=workflow,
                )
                assert report["valid"], (
                    sequencing,
                    goal,
                    strategy["id"],
                    report,
                )

    print("=" * 78)
    print("RESULT: PASS")
    print("Planner v3 target-artifact foundation: PASS")
    print("- hybrid sequencing is an input strategy, not a goal")
    print("- six independent genome goals are exposed")
    print("- one shared upstream graph is reused")
    print("- each route stops at its requested target artifact")
    print("- Illumina+ONT and Illumina+PacBio both validate")
    print("=" * 78)


if __name__ == "__main__":
    main()
