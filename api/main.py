from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.coverage import get_startup_coverage
from engine.catalog import get_global_coverage
from engine.constraints import (
    evaluate_tool_constraints,
    evaluate_workflow_constraints,
    get_profile_field_definitions,
    get_workflow_profile_field_definitions,
)
from engine.context_intake import (
    RAW_READS,
    get_data_state_options,
    get_goal_availability,
    supports_reference_finder,
)
from engine.dependencies import (
    get_artifact_label,
    load_workflows,
    validate_workflow,
)
from engine.evidence import (
    classify_papers,
    rank_evidence,
    score_literature_evidence,
)
from engine.exporter import (
    export_filename,
    workflow_to_json,
    workflow_to_markdown,
)
from engine.fallbacks import resolve_step_recovery
from engine.feasibility import (
    evaluate_operational_feasibility,
    operational_status_priority,
)
from engine.recommender import (
    build_workflow,
    get_goal_options,
    get_read_type_options,
    get_sample_types,
    get_sequencing_options,
    get_workflow_strategies,
)
from engine.references import (
    get_default_scope,
    get_reference_guidance,
    get_scope_label,
    get_scope_options,
)
from engine.research import run_systematic_discovery
from engine.scoring import (
    constraint_hard_gate_priority,
    constraint_soft_priority,
    operational_hard_gate_priority,
    scientific_fit_priority,
)
from services.biotools import get_biotools_info
from services.literature import search_tool_evidence
from engine.workflow_research import research_workflow
from services.ncbi_reference import (
    lookup_assembly_accession,
    reference_context_from_assembly,
    search_genome_assemblies,
    search_taxa,
)


API_VERSION = "0.2.0"


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "OMICSROUTE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the snapshot before accepting requests, including after idle wake-up.
    get_startup_coverage()
    yield


app = FastAPI(
    title="OmicsRoute API",
    version=API_VERSION,
    lifespan=lifespan,
    description=(
        "API layer for the OmicsRoute evidence-aware "
        "bioinformatics workflow recommendation engine."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanningContext(BaseModel):
    sample_type: str = Field(min_length=1)
    data_state: str = RAW_READS
    sequencing: str | None = None
    read_type: str | None = None
    reference_context: dict[str, Any] | None = None


class StrategyRequest(PlanningContext):
    goal: str = Field(min_length=1)


class WorkflowRequest(StrategyRequest):
    workflow_id: str | None = None
    compute_profile: dict[str, Any] | None = None


class WorkflowInspectRequest(WorkflowRequest):
    dataset_profile: dict[str, Any] = Field(default_factory=dict)
    scope_id: str | None = None


class ToolEvidenceRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    operation: str | None = None


class WorkflowResearchRequest(WorkflowRequest):
    years: int = Field(default=10, ge=1, le=30)


class DiscoveryRequest(BaseModel):
    operation: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    curated_tools: list[str] = Field(default_factory=list)
    depth: str = "Standard"


def _execution_values(request: PlanningContext) -> tuple[str, str]:
    if request.data_state == RAW_READS:
        if not request.sequencing:
            raise HTTPException(
                status_code=422,
                detail="sequencing is required when data_state is raw_reads",
            )
        if not request.read_type:
            raise HTTPException(
                status_code=422,
                detail="read_type is required when data_state is raw_reads",
            )
        return request.sequencing, request.read_type

    return (
        request.sequencing or "Existing data",
        request.read_type or "Not applicable",
    )


def _build_workflow_from_request(request: WorkflowRequest) -> dict[str, Any]:
    sequencing, read_type = _execution_values(request)

    result = build_workflow(
        request.sample_type,
        sequencing,
        read_type,
        request.goal,
        workflow_id=request.workflow_id,
        compute_profile=request.compute_profile,
        data_state=request.data_state,
        reference_context=request.reference_context,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No compatible OmicsRoute workflow could be built "
                "for this context."
            ),
        )

    return result


def _is_collection_artifact(artifact_id: str) -> bool:
    artifact_id = str(artifact_id or "")
    label = str(get_artifact_label(artifact_id) or "")
    return (
        artifact_id.endswith("_collection")
        or "collection" in label.lower()
    )


def _artifact_record(artifact_id: str) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "label": get_artifact_label(artifact_id),
        "is_collection": _is_collection_artifact(artifact_id),
    }


def _tool_dependency_status(
    step_report: dict[str, Any] | None,
    tool_id: str,
) -> dict[str, Any]:
    if step_report is None:
        return {"status": "not_evaluated", "missing": []}

    if tool_id in (step_report.get("runnable_tools") or []):
        return {"status": "runnable", "missing": []}

    if tool_id in (step_report.get("unknown_tools") or []):
        return {"status": "unknown", "missing": []}

    for item in step_report.get("blocked_tools", []) or []:
        if item.get("tool") == tool_id:
            missing = item.get("missing", []) or []
            return {
                "status": "blocked",
                "missing": [_artifact_record(x) for x in missing],
            }

    return {"status": "not_evaluated", "missing": []}


def _dependency_priority(status: str) -> int:
    return {
        "runnable": 3,
        "unknown": 2,
        "not_evaluated": 1,
        "blocked": 0,
    }.get(status, 1)


def _constraint_fields(workflow: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}
    conflicts: list[dict[str, Any]] = []

    workflow_id = workflow.get("id")
    workflow_fields = (
        get_workflow_profile_field_definitions(workflow_id)
        if workflow_id
        else {}
    )

    for field_id, definition in (workflow_fields or {}).items():
        if not isinstance(definition, dict):
            continue
        fields[field_id] = definition.copy()
        sources[field_id] = ["Workflow strategy"]

    for step in workflow.get("steps", []) or []:
        for tool in step.get("tools", []) or []:
            tool_id = tool.get("id")
            if not tool_id:
                continue

            tool_name = tool.get("name", tool_id)
            definitions = get_profile_field_definitions(tool_id) or {}

            for field_id, definition in definitions.items():
                if not isinstance(definition, dict):
                    continue

                sources.setdefault(field_id, [])
                if tool_name not in sources[field_id]:
                    sources[field_id].append(tool_name)

                if field_id not in fields:
                    fields[field_id] = definition.copy()
                    continue

                existing = fields[field_id]
                for property_name in ("type", "unit"):
                    first = existing.get(property_name)
                    other = definition.get(property_name)
                    if first and other and first != other:
                        conflicts.append(
                            {
                                "field_id": field_id,
                                "property": property_name,
                                "first": first,
                                "other": other,
                                "tool": tool_name,
                            }
                        )

    return {
        "fields": fields,
        "sources": sources,
        "conflicts": conflicts,
    }


def _profile_for_subject(
    workflow: dict[str, Any],
    dataset_profile: dict[str, Any],
    step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = dict(dataset_profile or {})
    context = dict(workflow.get("context", {}) or {})

    if step is not None:
        step_context = dict(step.get("context", {}) or {})
        context.update(
            {
                key: value
                for key, value in step_context.items()
                if value not in (None, "")
            }
        )

    for key in ("sample_type", "sequencing", "read_type", "goal"):
        value = context.get(key)
        if value not in (None, ""):
            profile[key] = value

    return profile


def _workflow_required_inputs(
    workflow: dict[str, Any],
    dependency: dict[str, Any],
) -> list[dict[str, Any]]:
    source = workflow.get("external_inputs", []) or []
    if not source:
        source = dependency.get("initial_artifacts", []) or []

    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    for artifact_id in source:
        artifact_id = str(artifact_id)
        if not artifact_id or artifact_id in seen:
            continue
        seen.add(artifact_id)
        result.append(_artifact_record(artifact_id))

    return result


def _reference_payload(
    workflow: dict[str, Any],
    scope_id: str | None,
) -> dict[str, Any]:
    context = workflow.get("context", {}) or {}
    goal = context.get("goal")
    workflow_id = workflow.get("id")

    if not goal or not workflow_id:
        return {
            "scope_label": "Taxonomic scope",
            "scope_options": [],
            "selected_scope": None,
            "guidance": None,
        }

    options = get_scope_options(goal) or []
    selected = scope_id or get_default_scope(goal)

    return {
        "scope_label": get_scope_label(goal),
        "scope_options": options,
        "selected_scope": selected,
        "guidance": (
            get_reference_guidance(goal, workflow_id, selected)
            if options
            else None
        ),
    }


def _ranking_signature(
    tool: dict[str, Any],
    compute_enabled: bool,
) -> tuple:
    assessment = tool.get("_assessment", {}) or {}
    dependency = assessment.get("dependency", {}) or {}
    constraint = assessment.get("constraint", {}) or {}
    operational = assessment.get("operational", {}) or {}
    score = tool.get("score", {}) or {}

    return (
        _dependency_priority(dependency.get("status", "not_evaluated")),
        operational_hard_gate_priority(
            operational.get("status", "not_evaluated"),
            enabled=compute_enabled,
        ),
        constraint_hard_gate_priority(
            constraint.get("status", "not_defined")
        ),
        scientific_fit_priority(
            score.get("scientific_fit_label", "curated")
        ),
        constraint_soft_priority(
            constraint.get("status", "not_defined")
        ),
        (
            operational_status_priority(
                operational.get("status", "not_evaluated")
            )
            if compute_enabled
            else 0
        ),
        score.get("total", 0),
    )


def _step_recovery(
    workflow: dict[str, Any],
    step: dict[str, Any],
) -> dict[str, Any] | None:
    if step.get("mode", "sequential") == "parallel":
        return None

    tools = step.get("tools", []) or []
    blocked: list[dict[str, Any]] = []
    ready: list[dict[str, Any]] = []
    constraint_blocked: list[str] = []
    technical_blocked = False
    operational_blocked = False

    for tool in tools:
        assessment = tool.get("_assessment", {}) or {}
        dependency = assessment.get("dependency", {}) or {}
        constraint = assessment.get("constraint", {}) or {}
        operational = assessment.get("operational", {}) or {}
        compute_enabled = bool(
            assessment.get("compute_profile_enabled", False)
        )

        dep_status = dependency.get("status", "not_evaluated")
        con_status = constraint.get("status", "not_defined")
        op_status = operational.get("status", "not_evaluated")

        is_technical = dep_status == "blocked"
        is_constraint = con_status == "block"
        is_operational = compute_enabled and op_status == "blocked"

        if is_technical or is_constraint or is_operational:
            blocked.append(tool)
            technical_blocked = technical_blocked or is_technical
            operational_blocked = operational_blocked or is_operational
            if is_constraint and tool.get("id"):
                constraint_blocked.append(tool["id"])
        elif dep_status in ("runnable", "not_evaluated", "unknown"):
            ready.append(tool)

    if not blocked:
        return None

    if ready:
        names = [
            tool.get("name", tool.get("id", "tool"))
            for tool in ready
        ]
        return {
            "status": "continue",
            "message": (
                "Continue with the ready candidate(s). Blocked candidates "
                "remain visible for transparency."
            ),
            "ready_tools": names,
            "strategies": [],
            "remediations": [],
        }

    recovery = (
        resolve_step_recovery(
            workflow,
            step,
            constraint_blocked,
        )
        if constraint_blocked
        else {
            "strategies": [],
            "remediations": [],
            "direct_tool_ids": [],
        }
    )

    remediations = list(recovery.get("remediations", []) or [])

    if technical_blocked:
        remediations.append(
            {
                "title": "Restore technical prerequisites",
                "message": (
                    "Restore the missing upstream artifact required "
                    "by this step."
                ),
                "fallback_note": "",
            }
        )

    if operational_blocked:
        remediations.append(
            {
                "title": "Change execution environment",
                "message": (
                    "Use a compute environment that satisfies the "
                    "declared resource requirements, or choose a "
                    "compatible route."
                ),
                "fallback_note": "",
            }
        )

    strategies = recovery.get("strategies", []) or []

    return {
        "status": "blocked",
        "message": (
            "No ready candidate remains for this step. OmicsRoute "
            "will not silently substitute an unrelated method."
        ),
        "ready_tools": [],
        "direct_tool_ids": recovery.get("direct_tool_ids", []) or [],
        "strategies": strategies,
        "remediations": remediations,
    }


def _inspect_workflow(
    workflow: dict[str, Any],
    dataset_profile: dict[str, Any],
    compute_profile: dict[str, Any],
    scope_id: str | None,
) -> dict[str, Any]:
    dependency = validate_workflow(
        workflow.get("id"),
        workflow_override=workflow,
    )

    constraint_meta = _constraint_fields(workflow)
    workflow_profile = _profile_for_subject(
        workflow,
        dataset_profile,
    )

    workflow_constraint = evaluate_workflow_constraints(
        workflow.get("id"),
        workflow_profile,
    )

    step_report_lookup = {
        item.get("step_number"): item
        for item in dependency.get("steps", []) or []
    }

    compute_enabled = bool(
        (compute_profile or {}).get("enabled", False)
    )

    for step_number, step in enumerate(
        workflow.get("steps", []) or [],
        start=1,
    ):
        step_report = step_report_lookup.get(step_number)

        for tool in step.get("tools", []) or []:
            tool_id = tool.get("id")
            if not tool_id:
                continue

            subject_profile = _profile_for_subject(
                workflow,
                dataset_profile,
                step=step,
            )

            constraint = evaluate_tool_constraints(
                tool_id,
                subject_profile,
            )

            operational = evaluate_operational_feasibility(
                tool,
                compute_profile,
                operation=step.get("operation"),
            )

            dependency_status = _tool_dependency_status(
                step_report,
                tool_id,
            )

            tool["_assessment"] = {
                "dependency": dependency_status,
                "constraint": constraint,
                "operational": operational,
                "compute_profile_enabled": compute_enabled,
            }

        if step.get("mode", "sequential") != "parallel":
            tools = step.get("tools", []) or []
            tools.sort(
                key=lambda item: _ranking_signature(
                    item,
                    compute_enabled,
                ),
                reverse=True,
            )

            previous_signature = None
            current_rank = 0

            for position, tool in enumerate(tools, start=1):
                signature = _ranking_signature(
                    tool,
                    compute_enabled,
                )
                if previous_signature is None or signature != previous_signature:
                    current_rank = position
                    previous_signature = signature

                tool.setdefault("_assessment", {})["rank"] = current_rank

        else:
            for tool in step.get("tools", []) or []:
                tool.setdefault("_assessment", {})["rank"] = None

        step["recovery"] = _step_recovery(
            workflow,
            step,
        )

    required_inputs = _workflow_required_inputs(
        workflow,
        dependency,
    )

    tool_ids = {
        tool.get("id")
        for step in workflow.get("steps", []) or []
        for tool in step.get("tools", []) or []
        if tool.get("id")
    }

    reference = _reference_payload(
        workflow,
        scope_id,
    )

    exports = {
        "markdown": {
            "filename": export_filename(workflow, "md"),
            "mime": "text/markdown",
            "content": workflow_to_markdown(workflow),
        },
        "json": {
            "filename": export_filename(workflow, "json"),
            "mime": "application/json",
            "content": workflow_to_json(workflow),
        },
    }

    return {
        "workflow": workflow,
        "overview": {
            "steps": len(workflow.get("steps", []) or []),
            "tool_options": len(tool_ids),
            "required_inputs": len(required_inputs),
        },
        "required_inputs": required_inputs,
        "dependency": {
            **dependency,
            "initial_artifacts_labeled": [
                _artifact_record(x)
                for x in dependency.get("initial_artifacts", []) or []
            ],
            "final_artifacts_labeled": [
                _artifact_record(x)
                for x in dependency.get("final_artifacts", []) or []
            ],
        },
        "constraint_fields": constraint_meta,
        "workflow_constraint": workflow_constraint,
        "reference_guidance": reference,
        "exports": exports,
    }


def _compact_paper(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": paper.get("title"),
        "year": paper.get("year"),
        "doi": paper.get("doi"),
        "pmid": paper.get("pmid"),
        "url": paper.get("url")
        or paper.get("landing_page_url")
        or paper.get("openalex_url"),
        "journal": paper.get("journal")
        or paper.get("venue"),
        "cited_by_count": paper.get("cited_by_count", 0),
        "source_providers": paper.get("source_providers", []) or [],
        "search_scopes": paper.get("search_scopes", []) or [],
        "evidence_category": paper.get("evidence_category"),
        "evidence_label": paper.get("evidence_label"),
        "evidence_score": paper.get("evidence_score"),
    }


@lru_cache(maxsize=256)
def _cached_taxa(query: str):
    return search_taxa(query)


@lru_cache(maxsize=256)
def _cached_genomes(tax_id: str):
    return search_genome_assemblies(tax_id)


@lru_cache(maxsize=256)
def _cached_accession(accession: str):
    return lookup_assembly_accession(accession)


@app.get("/")
def root():
    return {
        "service": "OmicsRoute API",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "omicsroute-api",
        "version": API_VERSION,
    }


@app.get("/v1/sample-types")
def sample_types():
    return {"sample_types": get_sample_types()}


@app.get("/v1/data-states")
def data_states(sample_type: str = Query(..., min_length=1)):
    states = get_data_state_options(sample_type)

    return {
        "sample_type": sample_type,
        "data_states": [
            {
                **item,
                "supports_reference_finder": supports_reference_finder(
                    sample_type,
                    item.get("id"),
                ),
            }
            for item in states
        ],
    }


@app.get("/v1/sequencing-options")
def sequencing_options(sample_type: str = Query(..., min_length=1)):
    return {
        "sample_type": sample_type,
        "sequencing_options": get_sequencing_options(sample_type),
    }


@app.get("/v1/read-types")
def read_types(
    sample_type: str = Query(..., min_length=1),
    sequencing: str = Query(..., min_length=1),
):
    return {
        "sample_type": sample_type,
        "sequencing": sequencing,
        "read_types": get_read_type_options(
            sample_type,
            sequencing,
        ),
    }


@app.post("/v1/goals")
def goals(request: PlanningContext):
    sequencing, read_type = _execution_values(request)

    values = get_goal_options(
        request.sample_type,
        sequencing,
        read_type,
        data_state=request.data_state,
        reference_context=request.reference_context,
    )

    return {
        "context": {
            "sample_type": request.sample_type,
            "data_state": request.data_state,
            "sequencing": sequencing,
            "read_type": read_type,
        },
        "goals": [
            {
                "id": goal,
                "label": goal,
                **get_goal_availability(
                    request.sample_type,
                    request.data_state,
                    goal,
                ),
            }
            for goal in values
        ],
    }


@app.post("/v1/strategies")
def strategies(request: StrategyRequest):
    sequencing, read_type = _execution_values(request)

    return {
        "context": {
            "sample_type": request.sample_type,
            "data_state": request.data_state,
            "sequencing": sequencing,
            "read_type": read_type,
            "goal": request.goal,
        },
        "strategies": get_workflow_strategies(
            request.sample_type,
            sequencing,
            read_type,
            request.goal,
            data_state=request.data_state,
            reference_context=request.reference_context,
        ),
    }


@app.post("/v1/workflow")
def workflow(request: WorkflowRequest):
    return {
        "workflow": _build_workflow_from_request(request)
    }


@app.post("/v1/workflow/inspect")
def workflow_inspect(request: WorkflowInspectRequest):
    workflow_result = _build_workflow_from_request(request)

    return _inspect_workflow(
        workflow_result,
        dataset_profile=request.dataset_profile,
        compute_profile=request.compute_profile or {"enabled": False},
        scope_id=request.scope_id,
    )


@app.get("/v1/reference/taxa")
def reference_taxa(q: str = Query(..., min_length=1)):
    return _cached_taxa(q.strip())


@app.get("/v1/reference/assemblies")
def reference_assemblies(
    tax_id: str = Query(..., min_length=1)
):
    return _cached_genomes(tax_id.strip())


@app.get("/v1/reference/assembly/{accession}")
def reference_assembly(accession: str):
    return _cached_accession(
        accession.strip().upper()
    )


@app.get("/v1/reference/context/{accession}")
def reference_context(accession: str):
    accession = accession.strip().upper()
    result = _cached_accession(accession)

    if not isinstance(result, dict) or not result.get("ok"):
        return result

    assembly = result.get("assembly") or {}
    return {
        **result,
        "reference_context": reference_context_from_assembly(
            assembly,
            source_mode="api_reference_finder",
        ),
    }


@app.get("/v1/reference-guidance")
def reference_guidance(
    goal: str = Query(..., min_length=1),
    workflow_id: str = Query(..., min_length=1),
    scope_id: str | None = None,
):
    options = get_scope_options(goal) or []
    selected = scope_id or get_default_scope(goal)

    return {
        "scope_label": get_scope_label(goal),
        "scope_options": options,
        "selected_scope": selected,
        "guidance": (
            get_reference_guidance(
                goal,
                workflow_id,
                selected,
            )
            if options
            else None
        ),
    }


@app.post("/v1/tool-evidence")
def tool_evidence(request: ToolEvidenceRequest):
    result = search_tool_evidence(
        request.tool_name,
        operation=request.operation,
    )

    classified = classify_papers(
        result.get("results", []) or [],
        request.tool_name,
        operation=request.operation,
    )

    ranked = rank_evidence(classified)
    summary = score_literature_evidence(ranked)

    return {
        "tool_name": request.tool_name,
        "operation": request.operation,
        "available": not bool(result.get("error")),
        "summary": summary,
        "providers_searched": result.get(
            "providers_searched",
            [],
        ),
        "searches": result.get("searches", []),
        "partial_errors": result.get(
            "partial_errors",
            [],
        ),
        "error": result.get("error"),
        "papers": [
            _compact_paper(paper)
            for paper in ranked[:15]
        ],
    }


@app.post("/v1/workflow-research")
def workflow_research(request: WorkflowResearchRequest):
    workflow_result = _build_workflow_from_request(request)
    planned_operations = [
        step.get("operation")
        for step in workflow_result.get("steps", []) or []
        if step.get("operation")
    ]
    sequencing, read_type = _execution_values(request)
    return research_workflow(
        sample_type=request.sample_type,
        sequencing=sequencing,
        read_type=read_type,
        goal=request.goal,
        data_state=request.data_state,
        planned_operations=planned_operations,
        years=request.years,
    )


@app.get("/v1/biotools")
def biotools(
    tool_name: str = Query(..., min_length=1)
):
    return {
        "tool_name": tool_name,
        "record": get_biotools_info(tool_name),
    }


@app.post("/v1/discovery")
def discovery(request: DiscoveryRequest):
    deep = request.depth.strip().lower() == "deep"

    result = run_systematic_discovery(
        request.operation,
        context=request.context,
        curated_tools=request.curated_tools,
        registry_per_query=(30 if deep else 15),
        registry_max_total=(180 if deep else 100),
    )

    return result


@app.get("/v1/catalog/coverage")
def catalog_coverage(
    validate_dependencies: bool = False,
):
    if not validate_dependencies:
        return {
            **get_startup_coverage(),
            "dependency_audit": False,
        }

    # Audits use current catalogue files and never annotate the startup snapshot.
    coverage = get_global_coverage()
    workflows = load_workflows()
    reports = {
        workflow_id: validate_workflow(workflow_id)
        for workflow_id in workflows
    }

    families = []
    validated_total = 0
    broken_total = 0
    planned_total = 0

    for family in coverage.get("families", []) or []:
        family_copy = dict(family)
        goals_out = []
        family_validated = 0
        family_broken = 0
        family_planned = 0

        for goal in family.get("goals", []) or []:
            goal_copy = dict(goal)

            if not goal.get("supported", False):
                goal_copy["dependency_status"] = "planned"
                goal_copy["workflow_reports"] = []
                family_planned += 1
                planned_total += 1
            else:
                ids = [
                    item.get("workflow_id")
                    for item in (goal.get("contexts", []) or [])
                    if item.get("workflow_id")
                ]

                matching = [
                    reports[workflow_id]
                    for workflow_id in ids
                    if workflow_id in reports
                ]

                goal_copy["workflow_reports"] = matching

                if any(report.get("valid", False) for report in matching):
                    goal_copy["dependency_status"] = "valid"
                    family_validated += 1
                    validated_total += 1
                else:
                    goal_copy["dependency_status"] = "broken"
                    family_broken += 1
                    broken_total += 1

            goals_out.append(goal_copy)

        family_copy["goals"] = goals_out
        family_copy["validated_count"] = family_validated
        family_copy["broken_count"] = family_broken
        family_copy["planned_count"] = family_planned
        families.append(family_copy)

    total = coverage.get("total", 0)

    return {
        "total": total,
        "implemented": coverage.get("supported", 0),
        "validated": validated_total,
        "broken": broken_total,
        "planned": planned_total,
        "percentage": (
            round(validated_total / total * 100, 1)
            if total
            else 0
        ),
        "families": families,
        "dependency_audit": True,
    }
