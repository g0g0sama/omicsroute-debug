from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import (
    PlanningContext,
    StrategyRequest,
    WorkflowInspectRequest,
    data_states,
    goals,
    read_types,
    sample_types,
    sequencing_options,
    strategies,
    workflow_inspect,
)
from engine.context_intake import RAW_READS


@dataclass(frozen=True)
class Context:
    sample_type: str
    data_state: str
    sequencing: str | None
    read_type: str | None

    def label(self, goal: str | None = None, strategy_id: str | None = None) -> str:
        values = [
            self.sample_type,
            self.data_state,
            self.sequencing or "Existing data",
            self.read_type or "Not applicable",
        ]
        if goal:
            values.append(goal)
        if strategy_id:
            values.append(strategy_id)
        return " | ".join(values)


def fail(violations: list[str]) -> None:
    print("=" * 78)
    print("RESULT: FAIL")
    print("Selectable-context recovery contract was violated.")
    print(f"Violations: {len(violations)}")
    for item in violations[:80]:
        print("  -", item)
    if len(violations) > 80:
        print(f"  ... and {len(violations) - 80} more")
    print("=" * 78)
    raise SystemExit(1)


def _as_strings(values: Iterable[Any]) -> list[str]:
    return [str(value) for value in values or [] if str(value).strip()]


def ui_contexts() -> Iterable[Context]:
    """Enumerate only combinations the web planner itself can select."""
    for sample_type in _as_strings(sample_types().get("sample_types")):
        states = data_states(sample_type).get("data_states", []) or []
        for state in states:
            data_state = str((state or {}).get("id") or "").strip()
            if not data_state:
                continue

            if data_state != RAW_READS:
                yield Context(sample_type, data_state, None, None)
                continue

            for sequencing in _as_strings(
                sequencing_options(sample_type).get("sequencing_options")
            ):
                for read_type in _as_strings(
                    read_types(sample_type, sequencing).get("read_types")
                ):
                    yield Context(sample_type, data_state, sequencing, read_type)


def is_ready(tool: dict[str, Any]) -> bool:
    """Match the API's no-compute recovery semantics for one candidate."""
    assessment = tool.get("_assessment", {}) or {}
    dependency = assessment.get("dependency", {}) or {}
    constraint = assessment.get("constraint", {}) or {}

    return (
        dependency.get("status", "not_evaluated")
        in {"runnable", "unknown", "not_evaluated"}
        and constraint.get("status", "not_defined") != "block"
    )


def visible_recovery(recovery: Any) -> bool:
    """Return whether the current web RecoveryPanel gives the user an action."""
    if not isinstance(recovery, dict):
        return False

    if recovery.get("status") == "continue":
        return bool(recovery.get("ready_tools"))

    # RecoveryPanel currently renders these two collections. A bare
    # direct_tool_ids response is deliberately not accepted: an id that is not
    # shown in the UI does not help a user escape a blocked step.
    return bool(recovery.get("strategies") or recovery.get("remediations"))


def inspect_strategy(
    context: Context,
    goal: str,
    strategy: dict[str, Any],
    violations: list[str],
    counters: dict[str, int],
) -> None:
    strategy_id = str(strategy.get("id") or "").strip()
    label = context.label(goal, strategy_id or "<missing strategy id>")

    if not strategy_id:
        violations.append(f"{label}: strategy payload has no id")
        return

    try:
        result = workflow_inspect(
            WorkflowInspectRequest(
                sample_type=context.sample_type,
                data_state=context.data_state,
                sequencing=context.sequencing,
                read_type=context.read_type,
                goal=goal,
                workflow_id=strategy_id,
                dataset_profile={},
                compute_profile={"enabled": False},
            )
        )
    except Exception as exc:  # the exact FastAPI error varies by version
        violations.append(f"{label}: workflow inspection failed: {exc}")
        return

    counters["workflows_inspected"] += 1
    workflow = result.get("workflow", {}) or {}
    steps = workflow.get("steps", []) or []
    if not steps:
        violations.append(f"{label}: inspected workflow has no steps")
        return

    for step_number, step in enumerate(steps, start=1):
        counters["steps_checked"] += 1
        tools = step.get("tools", []) or []
        ready = [tool for tool in tools if is_ready(tool)]
        recovery = step.get("recovery")
        mode = step.get("mode", "sequential")
        step_name = str(step.get("name") or step.get("operation") or "unnamed")
        step_label = f"{label} | step {step_number} ({step_name})"

        if ready:
            counters["steps_with_ready_candidate"] += 1
            if isinstance(recovery, dict) and recovery.get("status") == "continue":
                counters["continue_recoveries"] += 1
            continue

        # Parallel steps intentionally do not receive an API recovery payload.
        # With no ready branch at all, the workflow offers no executable route.
        if mode == "parallel":
            violations.append(
                f"{step_label}: parallel step has no ready candidate and no recovery model"
            )
            continue

        if visible_recovery(recovery):
            counters["steps_with_visible_recovery"] += 1
            continue

        if isinstance(recovery, dict) and recovery.get("direct_tool_ids"):
            violations.append(
                f"{step_label}: recovery only exposes direct_tool_ids, which the web UI does not render"
            )
        elif not tools:
            violations.append(f"{step_label}: has no tool candidates and no recovery")
        else:
            violations.append(f"{step_label}: has no ready candidate and no visible recovery")


def main() -> None:
    counters = {
        "ui_contexts": 0,
        "selectable_goal_contexts": 0,
        "strategies_checked": 0,
        "workflows_inspected": 0,
        "steps_checked": 0,
        "steps_with_ready_candidate": 0,
        "steps_with_visible_recovery": 0,
        "continue_recoveries": 0,
    }
    violations: list[str] = []

    for context in ui_contexts():
        counters["ui_contexts"] += 1
        try:
            goal_payload = goals(
                PlanningContext(
                    sample_type=context.sample_type,
                    data_state=context.data_state,
                    sequencing=context.sequencing,
                    read_type=context.read_type,
                )
            )
        except Exception as exc:
            violations.append(f"{context.label()}: goals request failed: {exc}")
            continue

        for goal_record in goal_payload.get("goals", []) or []:
            if not isinstance(goal_record, dict) or not goal_record.get("selectable", True):
                continue

            goal = str(goal_record.get("id") or "").strip()
            if not goal:
                violations.append(f"{context.label()}: selectable goal has no id")
                continue

            counters["selectable_goal_contexts"] += 1
            goal_label = context.label(goal)
            try:
                rows = strategies(
                    StrategyRequest(
                        sample_type=context.sample_type,
                        data_state=context.data_state,
                        sequencing=context.sequencing,
                        read_type=context.read_type,
                        goal=goal,
                    )
                ).get("strategies", []) or []
            except Exception as exc:
                violations.append(f"{goal_label}: strategies request failed: {exc}")
                continue

            if not rows:
                violations.append(f"{goal_label}: selectable goal returns no strategy")
                continue

            counters["strategies_checked"] += len(rows)
            for strategy in rows:
                if not isinstance(strategy, dict):
                    violations.append(f"{goal_label}: strategy row is not an object")
                    continue
                inspect_strategy(context, goal, strategy, violations, counters)

    if counters["ui_contexts"] == 0:
        violations.append("No UI-selectable planning contexts were enumerated")
    if counters["selectable_goal_contexts"] == 0:
        violations.append("No selectable goal contexts were enumerated")

    if violations:
        fail(violations)

    print("=" * 78)
    print("RESULT: PASS")
    print("Selectable-context recovery contract: PASS")
    print(f"UI contexts checked: {counters['ui_contexts']}")
    print(f"Selectable goal contexts: {counters['selectable_goal_contexts']}")
    print(f"Strategies checked: {counters['strategies_checked']}")
    print(f"Workflows inspected through the API: {counters['workflows_inspected']}")
    print(f"Steps checked: {counters['steps_checked']}")
    print(f"Steps with a ready candidate: {counters['steps_with_ready_candidate']}")
    print(f"Steps with visible recovery: {counters['steps_with_visible_recovery']}")
    print(f"Continue recoveries: {counters['continue_recoveries']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
