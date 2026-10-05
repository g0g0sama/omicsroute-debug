from pathlib import Path

import yaml

from engine.compatibility import (
    check_tool_compatibility
)

from engine.scoring import (
    calculate_tool_score,
    scientific_fit_priority,
    operational_hard_gate_priority
)

from engine.feasibility import (
    evaluate_operational_feasibility,
    operational_status_priority
)


from engine.dynamic_routes import (
    get_dynamic_read_types,
    get_dynamic_goal_options,
    get_dynamic_workflow_strategies,
    materialize_dynamic_workflow,
)


from engine.context_intake import (
    RAW_READS,
    compact_reference_context,
    filter_goal_options,
    get_context_goal_options,
    get_context_workflow_strategies,
    get_goal_availability,
    materialize_context_workflow,
)


from engine.planner_v2 import (
    get_planner_goal_options,
    get_planner_read_type_options,
    get_planner_sequencing_options,
    get_planner_workflow_strategies,
    materialize_planner_workflow,
    should_suppress_legacy_functional_route,
)

from engine.planner_v3 import (
    get_target_artifact_goal_options,
    get_target_artifact_workflow_strategies,
    materialize_target_artifact_workflow,
)



# ==================================================
# PATHS
# ==================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    BASE_DIR
    / "data"
)


# ==================================================
# YAML LOADING
# ==================================================

# Streamlit reruns app.py after most UI interactions, but imported
# modules remain loaded. Keeping parsed YAML data here avoids reparsing
# the same files on every dropdown change. The cache is automatically
# invalidated when a YAML file changes on disk.
_YAML_CACHE = {}


def _yaml_file_signature(filepath):
    """Return a lightweight signature that changes when the file changes."""

    stat = filepath.stat()

    return (
        stat.st_mtime_ns,
        stat.st_size
    )


def clear_yaml_cache():
    """Clear BioFlow's in-process YAML cache manually if ever needed."""

    _YAML_CACHE.clear()


def load_yaml(filename):
    """
    Load a YAML file from the BioFlow data directory.

    Parsed data is cached by filename + file modification signature,
    so editing the YAML automatically refreshes the cached value.
    """

    filepath = (
        DATA_DIR
        / filename
    )

    signature = (
        _yaml_file_signature(
            filepath
        )
    )

    cached = (
        _YAML_CACHE.get(
            filename
        )
    )

    if (
        cached
        and
        cached.get(
            "signature"
        )
        ==
        signature
    ):

        return cached[
            "data"
        ]

    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as file:

        data = yaml.safe_load(
            file
        )

    if data is None:
        data = {}

    _YAML_CACHE[
        filename
    ] = {
        "signature": signature,
        "data": data
    }

    return data


def load_tools():
    """
    Load tools.yaml.
    """

    return load_yaml(
        "tools.yaml"
    )


def load_workflows():
    """
    Load workflows.yaml.
    """

    return load_yaml(
        "workflows.yaml"
    )


def load_optional_yaml(filename):
    """
    Load an optional YAML file from the BioFlow data
    directory.

    Missing optional metadata must not break the core
    recommender.
    """

    filepath = (
        DATA_DIR
        / filename
    )

    if not filepath.exists():

        return {}

    return load_yaml(
        filename
    )


def load_strategy_fit():
    """
    Load optional strategy-specific tool-fit metadata.
    """

    return load_optional_yaml(
        "strategy_fit.yaml"
    )


# ==================================================
# UTILITIES
# ==================================================

def unique_preserve_order(values):
    """
    Remove duplicate values while preserving order.
    """

    result = []
    seen = set()

    for value in values:

        if value is None:
            continue

        key = str(value)

        if key not in seen:

            seen.add(
                key
            )

            result.append(
                value
            )

    return result


def format_context_value(value):
    """
    Convert a workflow context value into a
    human-readable string.

    Examples:

    "Illumina"
        -> "Illumina"

    ["Illumina", "Oxford Nanopore"]
        -> "Illumina + Oxford Nanopore"

    ["Paired-end", "Long reads"]
        -> "Paired-end + Long reads"
    """

    if isinstance(
        value,
        (
            list,
            tuple,
            set
        )
    ):

        return " + ".join(
            str(item)
            for item in value
        )

    if value is None:
        return ""

    return str(value)


def format_context(context):
    """
    Convert workflow context values into UI-safe strings while
    preserving BioFlow's scientific strategy metadata.

    Earlier versions returned only sample_type/sequencing/read_type/goal.
    That silently discarded keys such as feature_strategy and marker,
    which is why the Research panel showed "NOT SPECIFIED" even though
    those values were present in workflows.yaml.
    """

    if not isinstance(
        context,
        dict
    ):

        return {}

    formatted = {}

    for key, value in context.items():

        if isinstance(
            value,
            (
                list,
                tuple,
                set
            )
        ):

            formatted[
                key
            ] = [
                format_context_value(
                    item
                )
                for item
                in value
            ]

        elif isinstance(
            value,
            dict
        ):

            formatted[
                key
            ] = value.copy()

        else:

            formatted[
                key
            ] = (
                format_context_value(
                    value
                )
            )

    for required_key in [
        "sample_type",
        "sequencing",
        "read_type",
        "goal"
    ]:

        formatted.setdefault(
            required_key,
            ""
        )

    return formatted


# ==================================================
# DYNAMIC UI OPTIONS
# ==================================================

def get_sample_types():
    """
    Return all sample types currently represented
    in workflows.yaml.
    """

    workflows = (
        load_workflows()
    )

    values = []

    for workflow in workflows.values():

        context = (
            workflow.get(
                "context",
                {}
            )
        )

        value = (
            format_context_value(
                context.get(
                    "sample_type"
                )
            )
        )

        if value:

            values.append(
                value
            )

    return unique_preserve_order(
        values
    )


def get_sequencing_options(
    sample_type
):
    """
    Return sequencing options available for the
    selected sample type.

    Hybrid workflow lists are displayed as:

    Illumina + Oxford Nanopore
    """

    workflows = (
        load_workflows()
    )

    values = []

    for workflow in workflows.values():

        context = (
            workflow.get(
                "context",
                {}
            )
        )

        workflow_sample = (
            format_context_value(
                context.get(
                    "sample_type"
                )
            )
        )

        if workflow_sample == sample_type:

            value = (
                format_context_value(
                    context.get(
                        "sequencing"
                    )
                )
            )

            if value:

                values.append(
                    value
                )

    return unique_preserve_order(
        values
    )


def get_read_type_options(
    sample_type,
    sequencing
):
    """
    Return read types available for the selected
    sample type and sequencing combination.
    """

    workflows = (
        load_workflows()
    )

    values = []

    for workflow in workflows.values():

        context = (
            workflow.get(
                "context",
                {}
            )
        )

        workflow_sample = (
            format_context_value(
                context.get(
                    "sample_type"
                )
            )
        )

        workflow_sequencing = (
            format_context_value(
                context.get(
                    "sequencing"
                )
            )
        )

        if (
            workflow_sample
            == sample_type

            and

            workflow_sequencing
            == sequencing
        ):

            value = (
                format_context_value(
                    context.get(
                        "read_type"
                    )
                )
            )

            if value:

                values.append(
                    value
                )

    values.extend(
        get_dynamic_read_types(
            sample_type,
            sequencing
        )
    )

    values.extend(
        get_planner_read_type_options(
            sample_type,
            sequencing,
        )
    )

    return unique_preserve_order(
        values
    )


def get_goal_options(
    sample_type,
    sequencing,
    read_type,
    data_state=None,
    reference_context=None
):
    """
    Return analysis goals available for the exact
    selected data context.
    """

    workflows = (
        load_workflows()
    )

    values = []

    for workflow in workflows.values():

        context = (
            workflow.get(
                "context",
                {}
            )
        )

        workflow_sample = (
            format_context_value(
                context.get(
                    "sample_type"
                )
            )
        )

        workflow_sequencing = (
            format_context_value(
                context.get(
                    "sequencing"
                )
            )
        )

        workflow_read_type = (
            format_context_value(
                context.get(
                    "read_type"
                )
            )
        )

        if (
            workflow_sample
            == sample_type

            and

            workflow_sequencing
            == sequencing

            and

            workflow_read_type
            == read_type
        ):

            value = (
                format_context_value(
                    context.get(
                        "goal"
                    )
                )
            )

            if value:

                values.append(
                    value
                )

    values.extend(
        get_dynamic_goal_options(
            sample_type,
            sequencing,
            read_type
        )
    )

    values.extend(
        get_context_goal_options(
            sample_type,
            data_state
            or
            RAW_READS
        )
    )

    values.extend(
        get_target_artifact_goal_options(
            sample_type,
            sequencing,
            read_type,
            data_state
            or
            RAW_READS,
        )
    )

    values.extend(
        get_planner_goal_options(
            sample_type,
            sequencing,
            read_type,
            data_state
            or
            RAW_READS,
        )
    )

    values = unique_preserve_order(
        values
    )

    target_artifact_goals = get_target_artifact_goal_options(
        sample_type,
        sequencing,
        read_type,
        data_state or RAW_READS,
    )

    if target_artifact_goals:
        values = [
            value
            for value in values
            if value != "Hybrid genome assembly"
        ]

    values = filter_goal_options(
        values,
        sample_type,
        data_state
        or
        RAW_READS,
        reference_context
    )

    # Global selection contract:
    # disabled/needs-input goals may remain visible, but a selectable goal
    # must have at least one strategy for this exact context.
    routed_values = []

    for candidate_goal in values:
        availability = get_goal_availability(
            sample_type,
            data_state or RAW_READS,
            candidate_goal,
        )

        if not availability.get("selectable", True):
            routed_values.append(candidate_goal)
            continue

        strategies = get_workflow_strategies(
            sample_type,
            sequencing,
            read_type,
            candidate_goal,
            data_state=data_state or RAW_READS,
            reference_context=reference_context,
        )

        if strategies:
            routed_values.append(candidate_goal)

    return unique_preserve_order(routed_values)


# ==================================================
# FIND WORKFLOW / STRATEGIES
# ==================================================

def workflow_matches_selection(
    workflow,
    sample_type,
    sequencing,
    read_type,
    goal
):
    '''
    Match one workflow to the human-readable UI selection.

    Hybrid YAML contexts can be lists. The UI represents those lists as
    strings such as 'Illumina + Oxford Nanopore', so use
    format_context_value for exact matching.
    '''

    context = workflow.get("context", {}) or {}

    return (
        format_context_value(context.get("sample_type")) == sample_type
        and
        format_context_value(context.get("sequencing")) == sequencing
        and
        format_context_value(context.get("read_type")) == read_type
        and
        format_context_value(context.get("goal")) == goal
    )


def find_workflows(
    sample_type,
    sequencing,
    read_type,
    goal
):
    """
    Return every workflow matching one biological goal
    and dataset context.

    Multiple matches are intentional: BioFlow can model
    distinct technical strategies that reach the same
    biological goal, for example alignment-based and
    lightweight RNA-seq differential expression.
    """

    workflows = (
        load_workflows()
    )

    matches = []

    for (
        workflow_id,
        workflow
    ) in workflows.items():

        if workflow_matches_selection(
            workflow,
            sample_type,
            sequencing,
            read_type,
            goal
        ):

            matches.append(
                (
                    workflow_id,
                    workflow
                )
            )

    return matches


def get_workflow_strategies(
    sample_type,
    sequencing,
    read_type,
    goal,
    data_state=None,
    reference_context=None
):
    """
    Return workflow strategy records for the selected
    dataset context and biological goal.

    The UI uses this to let the user choose between
    genuinely different end-to-end strategies instead
    of treating them as tool-level alternatives.
    """

    target_artifact_strategies = (
        get_target_artifact_workflow_strategies(
            sample_type,
            sequencing,
            read_type,
            goal,
            data_state or RAW_READS,
        )
    )

    if target_artifact_strategies:
        return target_artifact_strategies

    target_artifact_goals = get_target_artifact_goal_options(
        sample_type,
        sequencing,
        read_type,
        data_state or RAW_READS,
    )

    if (
        target_artifact_goals
        and goal == "Hybrid genome assembly"
    ):
        return []

    matches = (
        find_workflows(
            sample_type,
            sequencing,
            read_type,
            goal
        )
    )

    if should_suppress_legacy_functional_route(
        sample_type,
        data_state or RAW_READS,
        goal,
    ):
        matches = []

    strategies = []

    for workflow_id, workflow in matches:

        strategies.append(
            {
                "id": workflow_id,
                "name": workflow.get(
                    "name",
                    workflow_id
                ),
                "description": workflow.get(
                    "description",
                    ""
                )
            }
        )

    dynamic_strategies = (
        []
        if should_suppress_legacy_functional_route(
            sample_type,
            data_state or RAW_READS,
            goal,
        )
        else get_dynamic_workflow_strategies(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflows=load_workflows()
        )
    )

    existing_strategy_ids = {
        item.get("id")
        for item in strategies
    }

    strategies.extend(
        item
        for item in dynamic_strategies
        if item.get("id") not in existing_strategy_ids
    )

    context_strategies = (
        get_context_workflow_strategies(
            sample_type,
            data_state
            or
            RAW_READS,
            goal,
            workflows=load_workflows()
        )
    )

    existing_strategy_ids = {
        item.get(
            "id"
        )
        for item
        in strategies
    }

    strategies.extend(
        item
        for item
        in context_strategies
        if item.get(
            "id"
        )
        not in
        existing_strategy_ids
    )

    planner_strategies = (
        get_planner_workflow_strategies(
            sample_type,
            sequencing,
            read_type,
            goal,
            data_state or RAW_READS,
        )
    )

    existing_strategy_ids = {
        item.get("id")
        for item in strategies
    }

    strategies.extend(
        item
        for item in planner_strategies
        if item.get("id") not in existing_strategy_ids
    )

    return strategies


def find_workflow(
    sample_type,
    sequencing,
    read_type,
    goal
):
    """
    Backward-compatible helper returning the first
    workflow matching the selected UI context.

    New UI code should use get_workflow_strategies()
    when multiple strategies may exist.
    """

    matches = (
        find_workflows(
            sample_type,
            sequencing,
            read_type,
            goal
        )
    )

    if not matches:

        return (
            None,
            None
        )

    return matches[0]


# ==================================================
# TOOL ACCESS
# ==================================================

def get_tool(tool_id):
    """
    Retrieve one tool from tools.yaml.
    """

    tools = (
        load_tools()
    )

    return tools.get(
        tool_id
    )


# ==================================================
# STRATEGY-SPECIFIC TOOL FIT
# ==================================================

def get_strategy_fit(
    workflow_id,
    operation,
    tool_id
):
    """
    Return curated strategy-specific metadata for one
    workflow + operation + tool combination.

    Missing metadata returns None so all existing
    workflows keep their original BioFlow scores.
    """

    data = (
        load_strategy_fit()
    )

    workflows = (
        data.get(
            "workflows",
            {}
        )
    )

    if not isinstance(
        workflows,
        dict
    ):

        return None

    workflow_definition = (
        workflows.get(
            workflow_id,
            {}
        )
    )

    if not isinstance(
        workflow_definition,
        dict
    ):

        return None

    operations = (
        workflow_definition.get(
            "operations",
            {}
        )
    )

    if not isinstance(
        operations,
        dict
    ):

        return None

    operation_definition = (
        operations.get(
            operation,
            {}
        )
    )

    if not isinstance(
        operation_definition,
        dict
    ):

        return None

    tool_definition = (
        operation_definition.get(
            tool_id
        )
    )

    if not isinstance(
        tool_definition,
        dict
    ):

        return None

    return (
        tool_definition.copy()
    )


# ==================================================
# STEP CANDIDATES
# ==================================================

def get_step_candidates(step):
    """
    Return candidate tool IDs for a workflow step.

    Current format:

    candidates:
      - tool1
      - tool2

    The old preferred/alternatives format is still
    supported as a fallback so older entries do not
    crash BioFlow.
    """

    candidates = (
        step.get(
            "candidates"
        )
    )

    if candidates:

        return (
            unique_preserve_order(
                candidates
            )
        )

    legacy_candidates = []

    preferred = (
        step.get(
            "preferred"
        )
    )

    if preferred:

        legacy_candidates.append(
            preferred
        )

    legacy_candidates.extend(
        step.get(
            "alternatives",
            []
        )
    )

    return (
        unique_preserve_order(
            legacy_candidates
        )
    )


# ==================================================
# STEP-SPECIFIC CONTEXT
# ==================================================

def get_effective_step_context(
    workflow_context,
    step
):
    """
    Determine the biological/sequencing context
    used for a specific workflow step.

    A step may override workflow-level sequencing
    and read type.

    Example:

    Workflow:
        sequencing:
          - Illumina
          - Oxford Nanopore

        read_type:
          - Paired-end
          - Long reads

    FastQC step:
        context:
          sequencing: Illumina
          read_type: Paired-end

    NanoPlot step:
        context:
          sequencing: Oxford Nanopore
          read_type: Long reads
    """

    step_context = (
        step.get(
            "context",
            {}
        )
    )

    return {
        "sample_type": (
            step_context.get(
                "sample_type",
                workflow_context.get(
                    "sample_type"
                )
            )
        ),

        "sequencing": (
            step_context.get(
                "sequencing",
                workflow_context.get(
                    "sequencing"
                )
            )
        ),

        "read_type": (
            step_context.get(
                "read_type",
                workflow_context.get(
                    "read_type"
                )
            )
        )
    }


# ==================================================
# PREPARE TOOL
# ==================================================

def prepare_tool(
    tool_id,
    sample_type,
    sequencing,
    read_type,
    operation,
    strategy_fit=None,
    compute_profile=None
):
    """
    Load a tool and calculate compatibility,
    BioFlow base score and optional strategy-specific
    suitability score.
    """

    tool = (
        get_tool(
            tool_id
        )
    )

    if tool is None:

        return None

    compatibility = (
        check_tool_compatibility(
            tool,
            sample_type,
            sequencing,
            read_type
        )
    )

    tool = (
        tool.copy()
    )

    tool[
        "id"
    ] = tool_id

    tool[
        "compatible"
    ] = (
        compatibility[
            "compatible"
        ]
    )

    tool[
        "compatibility_problems"
    ] = (
        compatibility[
            "problems"
        ]
    )

    tool[
        "strategy_fit"
    ] = (
        strategy_fit.copy()
        if isinstance(
            strategy_fit,
            dict
        )
        else
        None
    )

    tool[
        "score"
    ] = (
        calculate_tool_score(
            tool,
            operation,
            strategy_fit=(
                strategy_fit
            )
        )
    )

    tool[
        "operational_fit"
    ] = (
        evaluate_operational_feasibility(
            tool,
            compute_profile,
            operation=operation
        )
    )

    return tool


# ==================================================
# BUILD WORKFLOW
# ==================================================

def build_workflow(
    sample_type,
    sequencing,
    read_type,
    goal,
    workflow_id=None,
    compute_profile=None,
    data_state=None,
    reference_context=None
):
    """
    Build one complete BioFlow workflow.

    workflow_id is optional for backward compatibility.
    When supplied, it selects a specific end-to-end
    strategy among multiple workflows that implement the
    same biological goal.

    Step execution semantics are preserved:
      sequential -> candidate tools are alternatives
      parallel   -> candidate tools are independent
                    co-executed branches
    """

    workflows = (
        load_workflows()
    )

    target_artifact_workflow = (
        materialize_target_artifact_workflow(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflow_id,
            data_state or RAW_READS,
        )
        if workflow_id is not None
        else None
    )

    planner_workflow = (
        materialize_planner_workflow(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflow_id,
            data_state or RAW_READS,
        )
        if (
            workflow_id is not None
            and target_artifact_workflow is None
        )
        else None
    )

    context_workflow = (
        materialize_context_workflow(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflow_id,
            data_state
            or
            RAW_READS,
            workflows
        )
        if (
            workflow_id is not None
            and target_artifact_workflow is None
            and planner_workflow is None
        )
        else None
    )

    dynamic_workflow = (
        materialize_dynamic_workflow(
            sample_type,
            sequencing,
            read_type,
            goal,
            workflow_id,
            workflows
        )
        if (
            workflow_id is not None
            and target_artifact_workflow is None
            and
            context_workflow is None
        )
        else None
    )

    if target_artifact_workflow is not None:

        workflow = target_artifact_workflow
        workflow_id = target_artifact_workflow["id"]

    elif planner_workflow is not None:

        workflow = planner_workflow
        workflow_id = planner_workflow["id"]

    elif context_workflow is not None:

        workflow = context_workflow
        workflow_id = context_workflow["id"]

    elif dynamic_workflow is not None:

        workflow = dynamic_workflow
        workflow_id = dynamic_workflow["id"]

    elif workflow_id is not None:

        if should_suppress_legacy_functional_route(
            sample_type,
            data_state or RAW_READS,
            goal,
        ):
            return None

        workflow = (
            workflows.get(
                workflow_id
            )
        )

        if workflow is None:

            return None

        if not workflow_matches_selection(
            workflow,
            sample_type,
            sequencing,
            read_type,
            goal
        ):

            return None

    else:

        (
            workflow_id,
            workflow
        ) = find_workflow(
            sample_type,
            sequencing,
            read_type,
            goal
        )

        if workflow is None:

            return None

    workflow_context = (
        workflow.get(
            "context",
            {}
        )
    )

    external_inputs = (
        workflow.get(
            "external_inputs",
            []
        )
        or
        []
    )

    if isinstance(
        external_inputs,
        str
    ):

        external_inputs = [
            external_inputs
        ]

    result = {
        "id": (
            workflow_id
        ),

        "name": (
            workflow.get(
                "name",
                workflow_id
            )
        ),

        "description": (
            workflow.get(
                "description",
                ""
            )
        ),

        # Streamlit currently works with
        # human-readable strings.
        "context": (
            format_context(
                workflow_context
            )
        ),

        # Preserve machine-readable user prerequisites
        # for explicit display in the UI.
        "external_inputs": (
            unique_preserve_order(
                external_inputs
            )
        ),

        "steps": []
    }

    for metadata_key in (
        "dynamic_route",
        "route_class",
        "route_origin",
        "infer_read_inputs",
        "data_state",
        "planning_basis",
        "planner_version",
        "goal_target_artifact",
        "evidence_basis",
        "decision_points"
    ):

        if metadata_key in workflow:

            result[
                metadata_key
            ] = workflow[
                metadata_key
            ]

    result[
        "context"
    ][
        "data_state"
    ] = (
        data_state
        or
        RAW_READS
    )

    compact_reference = (
        compact_reference_context(
            reference_context
        )
    )

    if compact_reference:

        result[
            "context"
        ][
            "reference"
        ] = compact_reference

        for field_name in (
            "reference_accession",
            "organism_name",
            "tax_id"
        ):

            field_value = (
                compact_reference.get(
                    field_name
                )
            )

            if field_value:

                result[
                    "context"
                ][
                    field_name
                ] = field_value

    for step in workflow.get(
        "steps",
        []
    ):

        operation = (
            step.get(
                "operation"
            )
        )

        mode = (
            step.get(
                "mode",
                "sequential"
            )
            or
            "sequential"
        )

        mode = (
            str(mode)
            .strip()
            .lower()
        )

        candidate_ids = (
            get_step_candidates(
                step
            )
        )

        effective_context = (
            get_effective_step_context(
                workflow_context,
                step
            )
        )

        candidate_tools = []

        for tool_id in candidate_ids:

            strategy_fit = (
                get_strategy_fit(
                    workflow_id,
                    operation,
                    tool_id
                )
            )

            tool = (
                prepare_tool(
                    tool_id,
                    effective_context[
                        "sample_type"
                    ],
                    effective_context[
                        "sequencing"
                    ],
                    effective_context[
                        "read_type"
                    ],
                    operation,
                    strategy_fit=(
                        strategy_fit
                    ),
                    compute_profile=(
                        compute_profile
                    )
                )
            )

            if tool is not None:

                candidate_tools.append(
                    tool
                )

        # Sequential candidates are alternatives, so a
        # score-based order is useful. Parallel branches
        # are co-executed and keep their curated YAML order.
        if mode != "parallel":

            if (
                isinstance(
                    compute_profile,
                    dict
                )
                and
                compute_profile.get(
                    "enabled",
                    False
                )
            ):

                candidate_tools.sort(
                    key=lambda item: (
                        operational_hard_gate_priority(
                            item.get(
                                "operational_fit",
                                {}
                            ).get(
                                "status",
                                "unknown"
                            ),
                            enabled=True
                        ),

                        scientific_fit_priority(
                            item.get(
                                "score",
                                {}
                            ).get(
                                "scientific_fit_label",
                                "curated"
                            )
                        ),

                        operational_status_priority(
                            item.get(
                                "operational_fit",
                                {}
                            ).get(
                                "status",
                                "unknown"
                            )
                        ),

                        item.get(
                            "score",
                            {}
                        ).get(
                            "total",
                            0
                        )
                    ),
                    reverse=True
                )

            else:

                candidate_tools.sort(
                    key=lambda item: (
                        scientific_fit_priority(
                            item.get(
                                "score",
                                {}
                            ).get(
                                "scientific_fit_label",
                                "curated"
                            )
                        ),

                        item.get(
                            "score",
                            {}
                        ).get(
                            "total",
                            0
                        )
                    ),
                    reverse=True
                )

        aggregate_produces = (
            step.get(
                "aggregate_produces",
                []
            )
            or
            []
        )

        if isinstance(
            aggregate_produces,
            str
        ):

            aggregate_produces = [
                aggregate_produces
            ]

        min_successful_candidates = (
            step.get(
                "min_successful_candidates",
                1
            )
            or
            1
        )

        try:

            min_successful_candidates = int(
                min_successful_candidates
            )

        except (
            TypeError,
            ValueError
        ):

            min_successful_candidates = 1

        result[
            "steps"
        ].append(
            {
                "operation": (
                    operation
                ),

                "name": (
                    step.get(
                        "name",
                        operation
                        or
                        "Unnamed step"
                    )
                ),

                "description": (
                    step.get(
                        "description",
                        ""
                    )
                ),

                "context": (
                    {
                        **(
                            format_context(
                                workflow_context
                            )
                        ),

                        **(
                            format_context(
                                step.get(
                                    "context",
                                    {}
                                )
                            )
                        ),

                        "sample_type": (
                            format_context_value(
                                effective_context[
                                    "sample_type"
                                ]
                            )
                        ),

                        "sequencing": (
                            format_context_value(
                                effective_context[
                                    "sequencing"
                                ]
                            )
                        ),

                        "read_type": (
                            format_context_value(
                                effective_context[
                                    "read_type"
                                ]
                            )
                        )
                    }
                ),

                "mode": mode,

                "min_successful_candidates": (
                    min_successful_candidates
                ),

                "aggregate_produces": (
                    unique_preserve_order(
                        aggregate_produces
                    )
                ),

                "candidates": (
                    candidate_ids
                ),

                "candidate_ids": (
                    candidate_ids
                ),

                "tools": (
                    candidate_tools
                )
            }
        )

    return result

# ==================================================
# METAGENOME PLATFORM COVERAGE V1
# ==================================================

from engine.dynamic_routes import (
    get_dynamic_sequencing_options as _get_dynamic_sequencing_options_metagenome_v1
)

_get_sequencing_options_before_metagenome_v1 = get_sequencing_options


def get_sequencing_options(sample_type):
    values = list(
        _get_sequencing_options_before_metagenome_v1(sample_type)
        or []
    )

    for value in _get_dynamic_sequencing_options_metagenome_v1(sample_type) or []:
        if value not in values:
            values.append(value)

    for value in get_planner_sequencing_options(sample_type) or []:
        if value not in values:
            values.append(value)

    return values
