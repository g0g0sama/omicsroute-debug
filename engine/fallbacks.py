from __future__ import annotations

from engine.compatibility import check_tool_compatibility
from engine.constraints import evaluate_tool_constraints
from engine.dependencies import validate_workflow
from engine.recommender import load_tools, load_workflows


USABLE_CONSTRAINT_STATUSES = {
    "pass",
    "not_defined",
    "warning",
    "needs_input",
}


def _format_context_value(value):
    if isinstance(value, (list, tuple, set)):
        return " + ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _same_context(left, right):
    fields = ("sample_type", "sequencing", "read_type", "goal")
    return all(
        _format_context_value(left.get(field))
        == _format_context_value(right.get(field))
        for field in fields
    )


def _step_context(workflow, step):
    workflow_context = workflow.get("context", {}) or {}
    local = step.get("context", {}) or {}
    return {
        "sample_type": local.get("sample_type", workflow_context.get("sample_type")),
        "sequencing": local.get("sequencing", workflow_context.get("sequencing")),
        "read_type": local.get("read_type", workflow_context.get("read_type")),
        "goal": workflow_context.get("goal"),
    }


def _candidate_ids(step):
    values = step.get("candidates")
    if values:
        return list(dict.fromkeys(values))

    legacy = []
    if step.get("preferred"):
        legacy.append(step["preferred"])
    legacy.extend(step.get("alternatives", []) or [])
    return list(dict.fromkeys(legacy))


def _get_step_report(validation_report, step_number):
    for report in validation_report.get("steps", []) or []:
        if report.get("step_number") == step_number:
            return report
    return None


def _tool_dependency_status(step_report, tool_id):
    if step_report is None:
        return "not_evaluated"

    if tool_id in (step_report.get("runnable_tools", []) or []):
        return "runnable"

    if tool_id in (step_report.get("unknown_tools", []) or []):
        return "unknown"

    for blocked in step_report.get("blocked_tools", []) or []:
        if blocked.get("tool") == tool_id:
            return "blocked"

    return "not_evaluated"


def _constraint_profile(base_profile, workflow, step):
    profile = dict(base_profile or {})
    context = _step_context(workflow, step)

    for field in ("sample_type", "sequencing", "read_type", "goal"):
        if profile.get(field) is None:
            profile[field] = context.get(field)

    return profile


def _compatibility_summary(tool, workflow, step):
    context = _step_context(workflow, step)
    result = check_tool_compatibility(
        tool,
        context.get("sample_type"),
        context.get("sequencing"),
        context.get("read_type"),
    )
    return {
        "compatible": bool(result.get("compatible", False)),
        "problems": result.get("problems", []) or [],
    }


def _find_matching_operation_step(workflow, operation):
    matches = []
    for index, step in enumerate(workflow.get("steps", []) or [], start=1):
        if step.get("operation") == operation:
            matches.append((index, step))
    return matches


def _candidate_record(
    *,
    source,
    workflow_id,
    workflow,
    step_number,
    step,
    tool_id,
    blocked_tool_id,
    base_profile,
):
    if tool_id == blocked_tool_id:
        return None

    tools = load_tools()
    tool = tools.get(tool_id)
    if not isinstance(tool, dict):
        return None

    compatibility = _compatibility_summary(tool, workflow, step)
    if not compatibility["compatible"]:
        return None

    validation = validate_workflow(workflow_id)
    if not validation or validation.get("error"):
        return None

    step_report = _get_step_report(validation, step_number)
    dependency_status = _tool_dependency_status(step_report, tool_id)
    if dependency_status != "runnable":
        return None

    profile = _constraint_profile(base_profile, workflow, step)
    report = evaluate_tool_constraints(tool_id, profile)
    constraint_status = report.get("status", "not_defined")

    if constraint_status not in USABLE_CONSTRAINT_STATUSES:
        return None

    return {
        "source": source,
        "workflow_id": workflow_id,
        "workflow_name": workflow.get("name", workflow_id),
        "step_number": step_number,
        "step_name": step.get("name", step.get("operation", "Workflow step")),
        "operation": step.get("operation"),
        "tool_id": tool_id,
        "tool_name": tool.get("name", tool_id),
        "dependency_status": dependency_status,
        "constraint_status": constraint_status,
        "constraint_report": report,
        "compatibility_problems": compatibility["problems"],
    }


def _priority(record):
    source_priority = {"same_step": 3, "alternate_strategy": 2}.get(
        record.get("source"), 1
    )
    constraint_priority = {
        "pass": 4,
        "not_defined": 4,
        "warning": 3,
        "needs_input": 2,
    }.get(record.get("constraint_status"), 0)
    return (source_priority, constraint_priority)


def _recovery_notes(blocked_report):
    notes = []
    for check in blocked_report.get("checks", []) or []:
        if check.get("status") != "block":
            continue
        message = check.get("message")
        if message:
            notes.append(message)
        missing = check.get("missing_fields", []) or []
        if missing:
            notes.append(
                "Additional dataset fields needed: "
                + ", ".join(str(field).replace("_", " ") for field in missing)
            )
    return list(dict.fromkeys(notes))


def find_constraint_fallbacks(
    workflow,
    step,
    step_number,
    blocked_tool_id,
    profile,
):
    workflow_id = workflow.get("id")
    operation = step.get("operation")

    if not workflow_id or not operation:
        return {"alternatives": [], "recovery_notes": []}

    blocked_profile = _constraint_profile(profile, workflow, step)
    blocked_report = evaluate_tool_constraints(blocked_tool_id, blocked_profile)

    alternatives = []

    for tool_id in _candidate_ids(step):
        record = _candidate_record(
            source="same_step",
            workflow_id=workflow_id,
            workflow=workflow,
            step_number=step_number,
            step=step,
            tool_id=tool_id,
            blocked_tool_id=blocked_tool_id,
            base_profile=profile,
        )
        if record:
            alternatives.append(record)

    workflows = load_workflows()
    current_context = workflow.get("context", {}) or {}

    for alternate_id, alternate in workflows.items():
        if alternate_id == workflow_id:
            continue

        alternate_context = alternate.get("context", {}) or {}
        if not _same_context(current_context, alternate_context):
            continue

        for alternate_step_number, alternate_step in _find_matching_operation_step(
            alternate, operation
        ):
            for tool_id in _candidate_ids(alternate_step):
                record = _candidate_record(
                    source="alternate_strategy",
                    workflow_id=alternate_id,
                    workflow=alternate,
                    step_number=alternate_step_number,
                    step=alternate_step,
                    tool_id=tool_id,
                    blocked_tool_id=blocked_tool_id,
                    base_profile=profile,
                )
                if record:
                    alternatives.append(record)

    deduplicated = []
    seen = set()
    for record in alternatives:
        key = (record.get("workflow_id"), record.get("tool_id"))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(record)

    deduplicated.sort(key=_priority, reverse=True)

    return {
        "alternatives": deduplicated,
        "recovery_notes": _recovery_notes(blocked_report),
        "blocked_report": blocked_report,
    }
# OmicsRoute web fallback contract v1
def _omicsroute_step_number(workflow, step):
    """Find the 1-based step position expected by find_constraint_fallbacks."""
    for number, candidate in enumerate(workflow.get("steps", []) or [], start=1):
        if candidate is step or candidate == step:
            return number
    return None


def _omicsroute_unique_records(records, key):
    result = []
    seen = set()
    for record in records:
        marker = key(record)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(record)
    return result


def resolve_step_recovery(workflow, step, constraint_blocked_ids):
    """Adapt the established fallback engine to the FastAPI web contract.

    The web API calls this only after every displayed tool candidate has been
    blocked by a dataset constraint.  It retains the existing scientific
    matching in find_constraint_fallbacks and converts its records into the
    explicit strategies/remediations that RecoveryPanel renders.
    """
    step_number = _omicsroute_step_number(workflow, step)
    blocked_ids = list(dict.fromkeys(constraint_blocked_ids or []))

    if not step_number or not blocked_ids:
        return {"strategies": [], "remediations": [], "direct_tool_ids": []}

    alternatives = []
    notes = []
    lookup_errors = []

    for blocked_tool_id in blocked_ids:
        try:
            found = find_constraint_fallbacks(
                workflow=workflow,
                step=step,
                step_number=step_number,
                blocked_tool_id=blocked_tool_id,
                profile={},
            ) or {}
        except Exception as exc:
            # The recovery message must remain actionable even if one legacy
            # metadata record is malformed. The detailed exception remains in
            # the server log through the calling environment when applicable.
            lookup_errors.append(str(exc))
            continue

        alternatives.extend(found.get("alternatives", []) or [])
        notes.extend(found.get("recovery_notes", []) or [])

    direct = []
    strategies = []
    remediations = []

    for item in alternatives:
        if not isinstance(item, dict):
            continue

        tool_id = str(item.get("tool_id") or "").strip()
        tool_name = str(item.get("tool_name") or tool_id or "alternative tool")
        source = item.get("source")

        if source == "same_step" and tool_id:
            direct.append(tool_id)
            remediations.append(
                {
                    "title": "Use the compatible tool in this step",
                    "message": (
                        f"Use {tool_name} instead of the constraint-blocked "
                        "candidate for this workflow step."
                    ),
                    "fallback_note": "Scientific operation and technical prerequisites were checked.",
                }
            )
            continue

        if source == "alternate_strategy":
            workflow_id = str(item.get("workflow_id") or "").strip()
            if workflow_id:
                strategies.append(
                    {
                        "id": workflow_id,
                        "name": item.get("workflow_name") or workflow_id,
                        "description": (
                            f"Uses {tool_name} for the same "
                            f"{item.get('operation') or 'workflow'} operation."
                        ),
                    }
                )

    for note in notes:
        message = str(note or "").strip()
        if message:
            remediations.append(
                {
                    "title": "Resolve the dataset constraint",
                    "message": message,
                    "fallback_note": "Then rerun this workflow strategy.",
                }
            )

    if lookup_errors:
        remediations.append(
            {
                "title": "Review the blocked dataset requirement",
                "message": (
                    "A curated recovery lookup could not be completed for one "
                    "candidate. Review the displayed constraint requirements "
                    "before proceeding."
                ),
                "fallback_note": "No unrelated method is selected automatically.",
            }
        )

    if not strategies and not remediations:
        remediations.append(
            {
                "title": "Revise the blocking dataset requirement",
                "message": (
                    "No equivalent curated route is currently available for "
                    "this blocked condition. Resolve the reported dataset "
                    "requirement or choose another compatible strategy."
                ),
                "fallback_note": "OmicsRoute does not silently substitute a different scientific method.",
            }
        )

    return {
        "strategies": _omicsroute_unique_records(
            strategies, lambda item: item.get("id")
        ),
        "remediations": _omicsroute_unique_records(
            remediations,
            lambda item: (item.get("title"), item.get("message")),
        ),
        "direct_tool_ids": list(dict.fromkeys(direct)),
    }
