from __future__ import annotations

# OMICSROUTE PROJECT-ROOT IMPORT BOOTSTRAP
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from engine.context_intake import RAW_READS, GENOME_ASSEMBLY, PREDICTED_PROTEINS
from engine.dependencies import validate_workflow
from engine.recommender import build_workflow, get_goal_options, get_workflow_strategies

SAMPLE = "Eukaryotic genome"

RAW_CONTEXTS = [
    ("Illumina", "Paired-end", "genome_assembly"),
    ("Oxford Nanopore", "Long reads", "genome_assembly"),
    ("PacBio", "Long reads", "genome_assembly"),
    ("Illumina + Oxford Nanopore", "Paired-end + Long reads", "hybrid_genome_assembly"),
    ("Illumina + PacBio", "Paired-end + Long reads", "hybrid_genome_assembly"),
]

RAW_GOALS = {
    "Genome assembly": "eukaryotic_genome_fasta",
    "Genome quality assessment": "genome_completeness_report",
    "Contamination screening": "contamination_screening_report",
    "Repeat annotation": "repeat_annotation_gff",
    "Gene prediction": "eukaryotic_gene_annotation_gff",
    "Functional annotation": "functional_annotation_table",
}

LAST_OPERATION = {
    "Genome quality assessment": "genome_quality_assessment",
    "Contamination screening": "contamination_screening",
    "Repeat annotation": "repeat_annotation",
    "Gene prediction": "gene_prediction",
    "Functional annotation": "functional_annotation",
}

def assert_valid(workflow):
    report = validate_workflow(workflow["id"], workflow_override=workflow)
    assert report["valid"], report

def assert_no_downstream_leak(goal, operations):
    if goal == "Genome assembly":
        assert "assembly_qc" not in operations
        assert "gene_prediction" not in operations
        assert "functional_annotation" not in operations
    elif goal == "Contamination screening":
        assert "genome_quality_assessment" not in operations
        assert "repeat_discovery" not in operations
    elif goal == "Genome quality assessment":
        assert "repeat_discovery" not in operations
    elif goal == "Repeat annotation":
        assert "gene_prediction" not in operations
    elif goal == "Gene prediction":
        assert "functional_annotation" not in operations

def main():
    built = 0

    for sequencing, read_type, assembly_operation in RAW_CONTEXTS:
        goals = get_goal_options(
            SAMPLE, sequencing, read_type, data_state=RAW_READS
        )
        assert "Hybrid genome assembly" not in goals, goals

        for goal, target_artifact in RAW_GOALS.items():
            assert goal in goals, (sequencing, goal, goals)
            strategies = get_workflow_strategies(
                SAMPLE, sequencing, read_type, goal, data_state=RAW_READS
            )
            expected_count = 2 if goal in {"Gene prediction", "Functional annotation"} else 1
            assert len(strategies) == expected_count, (sequencing, goal, strategies)

            for strategy in strategies:
                assert strategy["id"].startswith("planner3__")
                workflow = build_workflow(
                    SAMPLE,
                    sequencing,
                    read_type,
                    goal,
                    workflow_id=strategy["id"],
                    data_state=RAW_READS,
                    compute_profile={"enabled": False},
                )
                assert workflow is not None
                assert workflow["planner_version"] == "3.1-all-eukaryotic-contexts"
                assert workflow["goal_target_artifact"] == target_artifact
                operations = [step["operation"] for step in workflow["steps"]]
                if goal == "Genome assembly":
                    assert operations[-1] == assembly_operation
                else:
                    assert operations[-1] == LAST_OPERATION[goal]
                assert_no_downstream_leak(goal, operations)
                assert_valid(workflow)
                built += 1

    assembly_goals = get_goal_options(
        SAMPLE, "Existing data", "Not applicable", data_state=GENOME_ASSEMBLY
    )
    assert "Genome assembly" not in assembly_goals

    for goal in [
        "Genome quality assessment",
        "Contamination screening",
        "Repeat annotation",
        "Gene prediction",
        "Functional annotation",
    ]:
        assert goal in assembly_goals, (goal, assembly_goals)
        strategies = get_workflow_strategies(
            SAMPLE, "Existing data", "Not applicable", goal,
            data_state=GENOME_ASSEMBLY,
        )
        assert strategies
        for strategy in strategies:
            workflow = build_workflow(
                SAMPLE,
                "Existing data",
                "Not applicable",
                goal,
                workflow_id=strategy["id"],
                data_state=GENOME_ASSEMBLY,
                compute_profile={"enabled": False},
            )
            assert workflow is not None
            operations = [step["operation"] for step in workflow["steps"]]
            assert "raw_read_qc" not in operations
            assert "genome_assembly" not in operations
            assert "hybrid_genome_assembly" not in operations
            assert_no_downstream_leak(goal, operations)
            assert_valid(workflow)
            built += 1

    protein_goals = get_goal_options(
        SAMPLE, "Existing data", "Not applicable", data_state=PREDICTED_PROTEINS
    )
    assert "Functional annotation" in protein_goals

    protein_strategies = get_workflow_strategies(
        SAMPLE,
        "Existing data",
        "Not applicable",
        "Functional annotation",
        data_state=PREDICTED_PROTEINS,
    )
    assert len(protein_strategies) == 1, protein_strategies

    workflow = build_workflow(
        SAMPLE,
        "Existing data",
        "Not applicable",
        "Functional annotation",
        workflow_id=protein_strategies[0]["id"],
        data_state=PREDICTED_PROTEINS,
        compute_profile={"enabled": False},
    )
    operations = [step["operation"] for step in workflow["steps"]]
    assert operations == ["functional_annotation"], operations
    assert_valid(workflow)
    built += 1

    print("=" * 78)
    print("RESULT: PASS")
    print("Planner v3.1 all-eukaryotic-context matrix: PASS")
    print(f"Built and dependency-validated routes: {built}")
    print("=" * 78)

if __name__ == "__main__":
    main()
