from engine.dependencies import validate_workflow
from engine.recommender import build_workflow

SAMPLE = "Eukaryotic genome"
GOAL = "Functional annotation"
WORKFLOW_ID = (
    "planner2__eukaryotic_genome__"
    "functional_annotation__evidence_guided"
)


def assert_order(operations, expected):
    pos = 0
    for operation in operations:
        if pos < len(expected) and operation == expected[pos]:
            pos += 1
    assert pos == len(expected), (expected, operations)


def main():
    for sequencing in [
        "Illumina + Oxford Nanopore",
        "Illumina + PacBio",
    ]:
        workflow = build_workflow(
            SAMPLE,
            sequencing,
            "Paired-end + Long reads",
            GOAL,
            workflow_id=WORKFLOW_ID,
            data_state="raw_reads",
            compute_profile={"enabled": False},
        )

        assert workflow is not None, sequencing

        operations = [step["operation"] for step in workflow["steps"]]

        assert_order(
            operations,
            [
                "raw_read_qc",
                "read_preprocessing",
                "raw_read_qc",
                "hybrid_genome_assembly",
                "assembly_qc",
                "contamination_screening",
                "genome_quality_assessment",
                "repeat_discovery",
                "repeat_annotation",
                "gene_prediction",
                "functional_annotation",
            ],
        )

        hybrid = next(
            step for step in workflow["steps"]
            if step["operation"] == "hybrid_genome_assembly"
        )
        assert {"masurca", "wengan"} <= set(hybrid["candidate_ids"])

        qc = next(
            step for step in workflow["steps"]
            if step["operation"] == "assembly_qc"
        )
        assert qc["mode"] == "parallel"
        assert qc["min_successful_candidates"] == 2
        assert {"quast", "merqury"} <= set(qc["candidate_ids"])

        contamination = next(
            step for step in workflow["steps"]
            if step["operation"] == "contamination_screening"
        )
        assert "blobtoolkit" in contamination["candidate_ids"]

        repeats = next(
            step for step in workflow["steps"]
            if step["operation"] == "repeat_discovery"
        )
        assert {"repeatmodeler", "edta"} <= set(repeats["candidate_ids"])

        functional = next(
            step for step in workflow["steps"]
            if step["operation"] == "functional_annotation"
        )
        assert functional["mode"] == "parallel"
        assert functional["min_successful_candidates"] == 2
        assert {"eggnog_mapper", "interproscan"} <= set(
            functional["candidate_ids"]
        )

        points = {
            item["id"]
            for item in workflow.get("decision_points", [])
        }
        assert "assembly_polishing" in points
        assert "haplotig_reduction" in points
        assert "contamination_response" in points

        if sequencing == "Illumina + PacBio":
            assert "pacbio_read_chemistry" in points

        report = validate_workflow(
            workflow["id"],
            workflow_override=workflow,
        )
        assert report["valid"], (sequencing, report)

    print("=" * 78)
    print("RESULT: PASS")
    print("Complete hybrid eukaryotic genome blueprint: PASS")
    print("- separate short/long read QC")
    print("- hybrid assembly alternatives")
    print("- QUAST + Merqury complementary QC")
    print("- contamination screening")
    print("- BUSCO completeness")
    print("- RepeatModeler / EDTA repeat discovery")
    print("- repeat masking")
    print("- structural gene annotation")
    print("- eggNOG + InterProScan complementary functional annotation")
    print("- polishing/haplotig/chemistry decisions kept context-dependent")
    print("=" * 78)


if __name__ == "__main__":
    main()
