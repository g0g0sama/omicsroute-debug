from engine.workflow_research import analyze, build_queries


def paper(title, abstract, year=2025, providers=None):
    return {
        "title": title,
        "abstract": abstract,
        "year": year,
        "source": "Synthetic Journal",
        "source_providers": providers or ["Europe PMC"],
        "cited_by_count": 10,
    }


def main():
    queries = build_queries(
        "Eukaryotic genome",
        "Illumina + PacBio",
        "Paired-end + Long reads",
        "Functional annotation",
        "raw_reads",
    )

    joined = " | ".join(queries)
    assert "Illumina" in joined
    assert "PacBio" in joined
    assert "functional annotation" in joined.lower()

    papers = [
        paper(
            "Chromosome-scale genome assembly and annotation",
            "Genome assembly, QUAST and BUSCO were followed by RepeatModeler, RepeatMasker, BRAKER gene prediction and eggNOG functional annotation.",
            providers=["Europe PMC", "OpenAlex"],
        ),
        paper(
            "Genome annotation workflow for a non-model eukaryote",
            "BUSCO completeness, RepeatModeler and RepeatMasker preceded BRAKER structural annotation using protein evidence; proteins were processed with eggNOG-mapper.",
            2024,
        ),
        paper(
            "Long-read eukaryotic genome resource",
            "Genome assembly and consensus polishing with Racon preceded BRAKER gene models and functional annotation with InterProScan and eggNOG.",
            2023,
        ),
        paper(
            "Genome curation before annotation",
            "Assembly polishing and contamination screening preceded structural gene annotation.",
            2022,
        ),
    ]

    planned = [
        "raw_read_qc",
        "read_preprocessing",
        "hybrid_genome_assembly",
        "assembly_qc",
        "genome_quality_assessment",
        "repeat_discovery",
        "repeat_annotation",
        "gene_prediction",
        "functional_annotation",
    ]

    result = analyze(
        papers,
        planned,
        min_candidate_support=2,
    )

    by_operation = {
        row["operation"]: row
        for row in result["operation_support"]
    }

    assert by_operation["genome_reconstruction"]["planned"] is True
    assert by_operation["repeat_annotation"]["supporting_paper_count"] >= 2
    assert by_operation["gene_prediction"]["supporting_paper_count"] >= 3
    assert by_operation["functional_annotation"]["supporting_paper_count"] >= 3

    candidates = {
        row["operation"]
        for row in result["contextual_candidate_operations"]
    }

    assert "assembly_polishing" in candidates
    assert "contamination_screening" not in candidates

    print("=" * 78)
    print("RESULT: PASS")
    print("Workflow-level literature research v2.1 validation passed.")
    print("=" * 78)


if __name__ == "__main__":
    main()
