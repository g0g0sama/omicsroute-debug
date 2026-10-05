from __future__ import annotations

# OMICSROUTE PROJECT-ROOT IMPORT BOOTSTRAP
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from engine.context_intake import RAW_READS, get_data_state_options, get_goal_availability
from engine.dependencies import validate_workflow
from engine.recommender import (
    build_workflow,
    get_goal_options,
    get_read_type_options,
    get_sample_types,
    get_sequencing_options,
    get_workflow_strategies,
)

def contexts_for(sample_type, data_state):
    if data_state != RAW_READS:
        return [("Existing data", "Not applicable")]
    result = []
    for sequencing in get_sequencing_options(sample_type):
        for read_type in get_read_type_options(sample_type, sequencing):
            result.append((sequencing, read_type))
    return result

def main():
    sample_types = get_sample_types()
    selectable_goals = 0
    strategy_count = 0
    build_count = 0
    dependency_invalid = []
    dead_ends = []

    for sample_type in sample_types:
        for state in get_data_state_options(sample_type):
            data_state = state["id"]
            for sequencing, read_type in contexts_for(sample_type, data_state):
                goals = get_goal_options(
                    sample_type,
                    sequencing,
                    read_type,
                    data_state=data_state,
                )
                assert "Hybrid genome assembly" not in goals, (
                    sample_type, data_state, sequencing, read_type, goals
                )
                for goal in goals:
                    availability = get_goal_availability(
                        sample_type, data_state, goal
                    )
                    if not availability.get("selectable", True):
                        continue
                    selectable_goals += 1
                    strategies = get_workflow_strategies(
                        sample_type,
                        sequencing,
                        read_type,
                        goal,
                        data_state=data_state,
                    )
                    if not strategies:
                        dead_ends.append(
                            (sample_type, data_state, sequencing, read_type, goal, "no strategies")
                        )
                        continue
                    strategy_count += len(strategies)
                    for strategy in strategies:
                        workflow = build_workflow(
                            sample_type,
                            sequencing,
                            read_type,
                            goal,
                            workflow_id=strategy["id"],
                            data_state=data_state,
                            compute_profile={"enabled": False},
                        )
                        if workflow is None or not workflow.get("steps"):
                            dead_ends.append(
                                (sample_type, data_state, sequencing, read_type, goal, strategy.get("id"))
                            )
                            continue
                        build_count += 1
                        report = validate_workflow(
                            workflow["id"], workflow_override=workflow
                        )
                        if not report.get("valid", False):
                            dependency_invalid.append(
                                (sample_type, data_state, sequencing, read_type, goal, strategy.get("id"))
                            )

    assert not dead_ends, (
        "Selectable UI contexts with no buildable workflow:\n"
        + "\n".join(str(item) for item in dead_ends)
    )

    print("=" * 78)
    print("RESULT: PASS")
    print("Global selectable-context matrix: PASS")
    print(f"Sample types: {len(sample_types)}")
    print(f"Selectable goal contexts: {selectable_goals}")
    print(f"Strategies checked: {strategy_count}")
    print(f"Workflows built: {build_count}")
    print(f"Dependency-invalid catalogue cases: {len(dependency_invalid)}")
    if dependency_invalid:
        print("NOTE: these remain catalogue-hardening items, not UI dead-ends.")
        for item in dependency_invalid[:20]:
            print("  -", item)
        if len(dependency_invalid) > 20:
            print(f"  ... and {len(dependency_invalid) - 20} more")
    print("=" * 78)

if __name__ == "__main__":
    main()
