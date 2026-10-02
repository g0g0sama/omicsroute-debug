from engine.compatibility import check_tool_compatibility
from engine.recommender import build_workflow, load_optional_yaml, load_tools


SAMPLE = "Eukaryotic genome"
GOAL = "Functional annotation"


def main():
    tools = load_tools()
    tool_io = load_optional_yaml("tool_io.yaml")

    assert "wengan" in tools, "Wengan missing from tools.yaml"
    assert "wengan" in tool_io, "Wengan missing from tool_io.yaml"

    wengan = tools["wengan"]

    for sequencing in [
        ["Illumina", "Oxford Nanopore"],
        ["Illumina", "PacBio"],
    ]:
        result = check_tool_compatibility(
            wengan,
            SAMPLE,
            sequencing,
            ["Paired-end", "Long reads"],
        )
        assert result["compatible"], (sequencing, result)

    for sequencing in [
        "Illumina + Oxford Nanopore",
        "Illumina + PacBio",
    ]:
        workflow = build_workflow(
            SAMPLE,
            sequencing,
            "Paired-end + Long reads",
            GOAL,
            workflow_id=(
                "planner2__eukaryotic_genome__"
                "functional_annotation__evidence_guided"
            ),
            data_state="raw_reads",
            compute_profile={"enabled": False},
        )

        hybrid_step = next(
            step
            for step in workflow["steps"]
            if step["operation"] == "hybrid_genome_assembly"
        )

        ids = [tool["id"] for tool in hybrid_step["tools"]]

        assert "masurca" in ids, (sequencing, ids)
        assert "wengan" in ids, (sequencing, ids)
        assert len(ids) >= 2, (sequencing, ids)

    print("=" * 78)
    print("RESULT: PASS")
    print("Hybrid eukaryotic assembly diversification: PASS")
    print("- Illumina + Oxford Nanopore: MaSuRCA + Wengan")
    print("- Illumina + PacBio: MaSuRCA + Wengan")
    print("=" * 78)


if __name__ == "__main__":
    main()
