from engine.workflow_research import build_targeted_operation_queries


def main():
    rows = [
        {
            "operation": "raw_read_qc",
            "label": "Read quality control",
            "role": "core_or_platform_dependent",
            "planned": True,
            "supporting_paper_count": 0,
        },
        {
            "operation": "repeat_discovery",
            "label": "De novo repeat discovery",
            "role": "core",
            "planned": True,
            "supporting_paper_count": 0,
        },
        {
            "operation": "repeat_annotation",
            "label": "Repeat annotation / masking",
            "role": "core",
            "planned": True,
            "supporting_paper_count": 1,
        },
        {
            "operation": "gene_prediction",
            "label": "Gene prediction",
            "role": "core",
            "planned": True,
            "supporting_paper_count": 5,
        },
        {
            "operation": "assembly_polishing",
            "label": "Assembly polishing",
            "role": "contextual_candidate",
            "planned": False,
            "supporting_paper_count": 0,
        },
    ]

    queries = build_targeted_operation_queries(
        sample_type="Eukaryotic genome",
        sequencing="Illumina + PacBio",
        goal="Functional annotation",
        operation_support=rows,
    )

    joined = " | ".join(queries)

    assert len(queries) == 3, queries
    assert "read quality control" in joined
    assert "RepeatModeler" in joined
    assert "RepeatMasker" in joined
    assert "Illumina" in joined
    assert "PacBio" in joined
    assert "Assembly polishing" not in joined

    print("=" * 78)
    print("RESULT: PASS")
    print("Targeted second-pass workflow literature queries: PASS")
    print("=" * 78)


if __name__ == "__main__":
    main()
