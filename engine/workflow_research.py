from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from typing import Any

from services.europepmc import search_topic_literature as europepmc_topic
from services.openalex import search_topic_literature as openalex_topic
from services.literature import merge_papers

VERSION = "2.1-workflow-literature"

SIGNALS = {
    "raw_read_qc": ("Read quality control", "core_or_platform_dependent",
        ["read quality control", "sequence quality control", "fastqc", "nanoplot", "read quality assessment"]),
    "read_preprocessing": ("Read preprocessing / filtering", "core_or_platform_dependent",
        ["adapter trimming", "quality trimming", "read filtering", "read preprocessing", "fastp", "cutadapt", "filtlong", "chopper"]),
    "genome_reconstruction": ("Genome reconstruction / assembly", "core",
        ["genome assembly", "de novo assembly", "genome reconstruction", "masurca", "hifiasm", "flye", "assembled genome"]),
    "assembly_qc": ("Assembly structural quality assessment", "core",
        ["assembly quality", "assembly quality assessment", "assembly statistics", "quast", "n50", "assembly evaluation"]),
    "genome_quality_assessment": ("Genome completeness assessment", "core",
        ["busco", "genome completeness", "assembly completeness", "completeness assessment", "single-copy ortholog"]),
    "contamination_screening": ("Contamination screening", "contextual_candidate",
        ["contamination screening", "contaminant removal", "blobtoolkit", "blobtools", "fcs-gx", "foreign contamination"]),
    "assembly_polishing": ("Assembly polishing / consensus correction", "contextual_candidate",
        ["assembly polishing", "genome polishing", "consensus polishing", "pilon", "racon", "medaka", "nextpolish", "hypo"]),
    "haplotig_reduction": ("Haplotig / redundancy reduction", "contextual_candidate",
        ["purge_dups", "purge haplotigs", "haplotig purging", "haplotig removal", "redundant haplotigs", "allelic redundancy"]),
    "repeat_discovery": ("De novo repeat discovery", "core",
        ["repeatmodeler", "repeat discovery", "repeat library", "transposable element discovery", "de novo repeat"]),
    "repeat_annotation": ("Repeat annotation / masking", "core",
        ["repeatmasker", "repeat masking", "repeat annotation", "masked genome", "soft-masked", "softmasked"]),
    "gene_prediction": ("Structural gene annotation / gene prediction", "core",
        ["gene prediction", "structural annotation", "structural gene annotation", "braker", "augustus", "gene models", "gene model prediction"]),
    "transcript_or_protein_evidence": ("Transcript/protein evidence for gene models", "contextual_candidate",
        ["rna-seq evidence", "rnaseq evidence", "transcript evidence", "protein evidence", "homologous proteins", "protein homology evidence", "evidence-guided annotation"]),
    "functional_annotation": ("Functional annotation", "core",
        ["functional annotation", "eggnog", "interproscan", "interpro", "orthology assignment", "go annotation", "kegg annotation", "protein function"]),
}


TARGETED_OPERATION_TERMS = {
    "raw_read_qc": "read quality control",
    "read_preprocessing": "adapter trimming quality filtering",
    "genome_reconstruction": "genome assembly",
    "assembly_qc": "assembly quality assessment",
    "genome_quality_assessment": "BUSCO genome completeness",
    "repeat_discovery": "RepeatModeler de novo repeat discovery",
    "repeat_annotation": "RepeatMasker repeat masking",
    "gene_prediction": "structural gene annotation gene prediction",
    "functional_annotation": "protein functional annotation eggNOG InterPro",
}


def build_targeted_operation_queries(
    sample_type,
    sequencing,
    goal,
    operation_support,
    max_operations=4,
):
    platform = " ".join(_platform_terms(sequencing))
    queries = []

    weak_rows = [
        row
        for row in (operation_support or [])
        if row.get("planned")
        and row.get("role") in {"core", "core_or_platform_dependent"}
        and int(row.get("supporting_paper_count", 0) or 0) < 2
    ]

    for row in weak_rows[:max(1, int(max_operations))]:
        operation = row.get("operation")
        terms = TARGETED_OPERATION_TERMS.get(
            operation,
            row.get("label") or operation,
        )

        query = " ".join(
            str(item).strip()
            for item in [sample_type, platform, terms, goal]
            if item
        )

        if query and query not in queries:
            queries.append(query)

    return queries


def _norm(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").lower().replace("–", "-").replace("—", "-"),
    ).strip()


def _paper_text(paper: dict[str, Any]) -> str:
    return _norm(f"{paper.get('title', '')} {paper.get('abstract', '')}")


def _compact_paper(paper: dict[str, Any], matched=None) -> dict[str, Any]:
    return {
        "title": paper.get("title"),
        "year": paper.get("year"),
        "journal": paper.get("source"),
        "doi": paper.get("doi"),
        "pmid": paper.get("pmid"),
        "url": (
            paper.get("doi_url")
            or paper.get("pubmed_url")
            or paper.get("europepmc_url")
            or paper.get("openalex_url")
        ),
        "cited_by_count": paper.get("cited_by_count", 0) or 0,
        "source_providers": paper.get("source_providers", []) or [],
        "matched_signals": matched or [],
    }


def _platform_terms(sequencing: str | None) -> list[str]:
    return {
        "Illumina": ["Illumina", "short-read"],
        "Oxford Nanopore": ["Oxford Nanopore", "Nanopore", "long-read"],
        "PacBio": ["PacBio", "HiFi", "long-read"],
        "Illumina + Oxford Nanopore": ["Illumina", "Oxford Nanopore", "hybrid assembly"],
        "Illumina + PacBio": ["Illumina", "PacBio", "HiFi", "hybrid assembly"],
    }.get(str(sequencing or ""), [str(sequencing)] if sequencing else [])


def build_queries(sample_type, sequencing, read_type, goal, data_state):
    if sample_type == "Eukaryotic genome" and goal == "Functional annotation":
        platform = " ".join(_platform_terms(sequencing))
        queries = [
            "eukaryotic genome functional annotation workflow",
            "eukaryotic genome assembly repeat masking gene prediction functional annotation",
        ]
        if platform:
            queries.append(f"{platform} eukaryotic genome annotation workflow")
        if data_state == "genome_assembly":
            queries.append(
                "eukaryotic genome assembly repeat annotation structural annotation functional annotation"
            )
        return list(dict.fromkeys(queries))

    return [
        " ".join(
            str(item).strip()
            for item in [sample_type, sequencing, read_type, goal, "workflow"]
            if item
        )
    ]


def _search_one(provider, query, years, limit):
    fn = openalex_topic if provider == "OpenAlex" else europepmc_topic
    return provider, query, fn(query=query, years=years, limit=limit)


def search_workflow_literature(queries, years=10, per_source_limit=8, max_queries=3):
    clean_queries = [
        str(item).strip()
        for item in (queries or [])
        if str(item).strip()
    ][:max_queries]

    providers = ["OpenAlex", "Europe PMC"]
    papers, searches, errors = [], [], []

    with ThreadPoolExecutor(max_workers=max(1, len(clean_queries) * 2)) as pool:
        futures = [
            pool.submit(_search_one, provider, query, years, per_source_limit)
            for query in clean_queries
            for provider in providers
        ]

        for future in as_completed(futures):
            try:
                provider, query, result = future.result()
            except Exception as exc:
                errors.append(str(exc))
                continue

            result = result or {}
            searches.append(
                {
                    "provider": provider,
                    "query": query,
                    "error": result.get("error"),
                }
            )

            if result.get("error"):
                errors.append(f"{provider}: {result.get('error')}")

            papers.extend(result.get("results", []) or [])

    merged = merge_papers(papers)
    merged.sort(
        key=lambda paper: (
            len(paper.get("source_providers", []) or []),
            paper.get("year", 0) or 0,
            paper.get("cited_by_count", 0) or 0,
        ),
        reverse=True,
    )

    return {
        "queries": clean_queries,
        "providers_searched": providers,
        "searches": searches,
        "partial_errors": errors,
        "results": merged,
        "total_results": len(merged),
        "error": (
            "Workflow-literature search returned no publications."
            if not merged
            else None
        ),
    }


def _canonicalize(planned_operations):
    values = set(planned_operations or [])
    if {"genome_assembly", "hybrid_genome_assembly"} & values:
        values.add("genome_reconstruction")
    return values


def analyze(papers, planned_operations, min_candidate_support=2):
    planned = _canonicalize(planned_operations)
    rows = []
    contextual = []

    for operation, (label, role, signals) in SIGNALS.items():
        hits = []

        for paper in papers or []:
            text = _paper_text(paper)
            matched = [signal for signal in signals if _norm(signal) in text]
            if matched:
                hits.append((paper, list(dict.fromkeys(matched))))

        hits.sort(
            key=lambda item: (
                len(item[0].get("source_providers", []) or []),
                item[0].get("year", 0) or 0,
                item[0].get("cited_by_count", 0) or 0,
            ),
            reverse=True,
        )

        count = len(hits)
        confidence = (
            "strong"
            if count >= 3
            else "moderate"
            if count == 2
            else "limited"
            if count == 1
            else "none"
        )

        row = {
            "operation": operation,
            "label": label,
            "role": role,
            "planned": operation in planned,
            "supporting_paper_count": count,
            "confidence": confidence,
            "papers": [
                _compact_paper(paper, matched)
                for paper, matched in hits[:5]
            ],
        }
        rows.append(row)

        if (
            role == "contextual_candidate"
            and operation not in planned
            and count >= min_candidate_support
        ):
            contextual.append(
                {
                    "operation": operation,
                    "label": label,
                    "supporting_paper_count": count,
                    "confidence": confidence,
                    "status": "literature_signal_only",
                    "note": (
                        "Repeated literature signal only; do not auto-insert "
                        "until artifact/I-O, capability and context validation pass."
                    ),
                }
            )

    planned_rows = [row for row in rows if row["planned"]]
    supported = [
        row for row in planned_rows if row["supporting_paper_count"] > 0
    ]

    return {
        "operation_support": rows,
        "planned_operation_count": len(planned_rows),
        "planned_operations_with_literature_signal": len(supported),
        "planner_alignment_fraction": (
            round(len(supported) / len(planned_rows), 3)
            if planned_rows
            else None
        ),
        "contextual_candidate_operations": contextual,
        "interpretation": (
            "Literature signals support or challenge the operation blueprint; "
            "artifact/dependency rules determine executable order. Abstract "
            "co-occurrence is not treated as proof of step order."
        ),
    }


def research_workflow(
    sample_type,
    sequencing,
    read_type,
    goal,
    data_state,
    planned_operations,
    years=10,
):
    queries = build_queries(
        sample_type,
        sequencing,
        read_type,
        goal,
        data_state,
    )

    broad_search = search_workflow_literature(
        queries,
        years=years,
    )

    broad_papers = broad_search.get("results", []) or []

    initial_analysis = analyze(
        broad_papers,
        planned_operations,
    )

    targeted_queries = build_targeted_operation_queries(
        sample_type=sample_type,
        sequencing=sequencing,
        goal=goal,
        operation_support=initial_analysis.get("operation_support", []),
        max_operations=4,
    )

    targeted_search = {
        "queries": [],
        "providers_searched": [],
        "searches": [],
        "partial_errors": [],
        "results": [],
        "total_results": 0,
        "error": None,
    }

    if targeted_queries:
        targeted_search = search_workflow_literature(
            targeted_queries,
            years=years,
            per_source_limit=6,
            max_queries=4,
        )

    combined_papers = merge_papers(
        broad_papers + (targeted_search.get("results", []) or [])
    )

    combined_papers.sort(
        key=lambda paper: (
            len(paper.get("source_providers", []) or []),
            paper.get("year", 0) or 0,
            paper.get("cited_by_count", 0) or 0,
        ),
        reverse=True,
    )

    final_analysis = analyze(
        combined_papers,
        planned_operations,
    )

    all_queries = list(
        dict.fromkeys(
            (broad_search.get("queries", []) or [])
            + (targeted_search.get("queries", []) or [])
        )
    )

    partial_errors = list(
        dict.fromkeys(
            (broad_search.get("partial_errors", []) or [])
            + (targeted_search.get("partial_errors", []) or [])
        )
    )

    providers = list(
        dict.fromkeys(
            (broad_search.get("providers_searched", []) or [])
            + (targeted_search.get("providers_searched", []) or [])
        )
    )

    return {
        "version": "2.3-workflow-literature",
        "context": {
            "sample_type": sample_type,
            "sequencing": sequencing,
            "read_type": read_type,
            "goal": goal,
            "data_state": data_state,
        },
        "queries": all_queries,
        "broad_queries": broad_search.get("queries", []),
        "targeted_followup_queries": targeted_search.get("queries", []),
        "targeted_followup_triggered": bool(targeted_queries),
        "providers_searched": providers,
        "searches": (
            (broad_search.get("searches", []) or [])
            + (targeted_search.get("searches", []) or [])
        ),
        "partial_errors": partial_errors,
        "error": (
            None
            if combined_papers
            else (targeted_search.get("error") or broad_search.get("error"))
        ),
        "paper_count": len(combined_papers),
        "papers": [
            _compact_paper(paper)
            for paper in combined_papers[:20]
        ],
        **final_analysis,
    }
