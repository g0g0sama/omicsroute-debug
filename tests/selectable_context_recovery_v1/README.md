# Selectable-context recovery contract v1

This regression test walks the same planner endpoints used by the web UI:

1. sample type
2. data state
3. sequencing and read type when raw reads are selected
4. selectable goal
5. every returned workflow strategy
6. inspected workflow steps

For every sequential step it requires either a ready tool candidate, or a
recovery action that the current web `RecoveryPanel` actually displays
(alternative strategy or remediation). A recovery response containing only
`direct_tool_ids` is reported as a failure because it is not actionable in the
current UI. A parallel step must contain at least one ready candidate.

The test uses an empty dataset profile and compute checks disabled. It protects
the default user route from dead ends; scenario-specific constraint tests remain
separate regression coverage.

Run from the project root:

```powershell
& ".\.venv\Scripts\python.exe" tests\selectable_context_recovery_v1\validate_selectable_context_recovery_v1.py
```
