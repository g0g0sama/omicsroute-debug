from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.dependencies import validate_workflow
from engine.recommender import (
    build_workflow,
    get_goal_options,
    get_workflow_strategies,
)


SAMPLE = "Eukaryotic genome"
GOAL = "Organism identification / closest reference match"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_context(sequencing: str, read_type: str, data_state: str) -> None:
    goals = get_goal_options(
        SAMPLE,
        sequencing,
        read_type,
        data_state=data_state,
    )
    require(GOAL in goals, f"Goal missing for {sequencing}/{read_type}/{data_state}: {goals}")

    strategies = get_workflow_strategies(
        SAMPLE,
        sequencing,
        read_type,
        GOAL,
        data_state=data_state,
    )
    require(len(strategies) == 1, f"Expected one identification strategy: {strategies}")

    workflow = build_workflow(
        SAMPLE,
        sequencing,
        read_type,
        GOAL,
        workflow_id=strategies[0]["id"],
        data_state=data_state,
        compute_profile={"enabled": False},
    )
    require(workflow is not None, "Workflow did not materialize")

    operations = [step.get("operation") for step in workflow.get("steps", [])]
    require(operations[-1] == "genome_identification", operations)
    require(
        workflow["steps"][-1].get("candidate_ids") == ["sourmash_eukaryotic"],
        workflow["steps"][-1],
    )
    require(
        "reference_genome_sketch_database" in workflow.get("external_inputs", []),
        workflow.get("external_inputs"),
    )

    if data_state == "raw_reads":
        require(
            "genome_assembly" in operations or "hybrid_genome_assembly" in operations,
            operations,
        )
    else:
        require("genome_assembly" not in operations, operations)
        require("hybrid_genome_assembly" not in operations, operations)

    report = validate_workflow(workflow["id"], workflow_override=workflow)
    require(report.get("valid", False), f"Dependency-invalid route: {report}")


def main() -> None:
    verify_context("Illumina", "Paired-end", "raw_reads")
    verify_context("Existing data", "Not applicable", "genome_assembly")
    print("=" * 78)
    print("RESULT: PASS")
    print("Eukaryotic organism identification / closest-reference route: PASS")
    print("- raw reads: assembly then reference-sketch comparison")
    print("- assembly: direct reference-sketch comparison")
    print("- output is closest indexed reference/lineage, not an automatic species claim")
    print("=" * 78)


if __name__ == "__main__":
    main()
