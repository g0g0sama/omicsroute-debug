from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import yaml


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

def _file_signature(filename):
    filepath = (DATA_DIR / filename).resolve()
    stat = filepath.stat()
    return filepath, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=32)
def _load_yaml_cached(filepath, modified_ns, file_size):

    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as file:

        data = yaml.safe_load(
            file
        )

    if data is None:
        return {}

    return data


def load_yaml(filename):
    """Cache catalogue YAML until its file version changes."""
    return _load_yaml_cached(*_file_signature(filename))


def load_analysis_catalog():

    return load_yaml(
        "analysis_goals.yaml"
    )


def load_workflows():

    return load_yaml(
        "workflows.yaml"
    )


# ==================================================
# WORKFLOW CONTEXT INDEX
# ==================================================

@lru_cache(maxsize=8)
def _workflow_context_index_cached(filepath, modified_ns, file_size):
    """
    Create a simplified index of all implemented
    BioFlow workflow contexts.
    """

    workflows = (
        _load_yaml_cached(filepath, modified_ns, file_size)
    )

    index = []

    for workflow_id, workflow in (
        workflows.items()
    ):

        context = (
            workflow.get(
                "context",
                {}
            )
        )

        sample_type = (
            context.get(
                "sample_type"
            )
        )

        goal = (
            context.get(
                "goal"
            )
        )

        sequencing = (
            context.get(
                "sequencing"
            )
        )

        read_type = (
            context.get(
                "read_type"
            )
        )

        if not sample_type or not goal:
            continue

        index.append(
            {
                "workflow_id": (
                    workflow_id
                ),

                "sample_type": (
                    sample_type
                ),

                "goal": (
                    goal
                ),

                "sequencing": (
                    sequencing
                ),

                "read_type": (
                    read_type
                )
            }
        )

    return index


def build_workflow_context_index():
    # Callers can annotate returned contexts without changing the cached index.
    return deepcopy(
        _workflow_context_index_cached(*_file_signature("workflows.yaml"))
    )


# ==================================================
# GOAL SUPPORT
# ==================================================

def find_goal_contexts(
    sample_type,
    goal_label
):
    """
    Find all currently implemented workflows for
    one sample type + analysis goal.
    """

    index = (
        build_workflow_context_index()
    )

    matches = []

    for item in index:

        if (
            item[
                "sample_type"
            ]
            == sample_type

            and

            item[
                "goal"
            ]
            == goal_label
        ):

            matches.append(
                item
            )

    return matches


# ==================================================
# BUILD CATALOG STATUS
# ==================================================

def get_catalog_status():
    """
    Merge analysis_goals.yaml with workflows.yaml.

    A goal is considered supported when at least
    one matching workflow actually exists.
    """

    catalog = (
        load_analysis_catalog()
    )

    result = []
    index = build_workflow_context_index()

    for (
        family_id,
        family
    ) in catalog.items():

        sample_type = (
            family.get(
                "sample_type"
            )
        )

        goals = (
            family.get(
                "goals",
                []
            )
        )

        processed_goals = []

        supported_count = 0

        for goal in goals:

            goal_label = (
                goal.get(
                    "label"
                )
            )

            contexts = [
                item for item in index
                if item["sample_type"] == sample_type
                and item["goal"] == goal_label
            ]

            supported = (
                len(contexts)
                > 0
            )

            if supported:
                supported_count += 1

            processed_goals.append(
                {
                    "id": (
                        goal.get(
                            "id"
                        )
                    ),

                    "label": (
                        goal_label
                    ),

                    "priority": (
                        goal.get(
                            "priority",
                            "core"
                        )
                    ),

                    "supported": (
                        supported
                    ),

                    "contexts": (
                        contexts
                    )
                }
            )

        total_goals = len(
            processed_goals
        )

        result.append(
            {
                "id": (
                    family_id
                ),

                "sample_type": (
                    sample_type
                ),

                "label": (
                    family.get(
                        "label",
                        sample_type
                    )
                ),

                "description": (
                    family.get(
                        "description",
                        ""
                    )
                ),

                "goals": (
                    processed_goals
                ),

                "supported_count": (
                    supported_count
                ),

                "total_count": (
                    total_goals
                )
            }
        )

    return result


# ==================================================
# GLOBAL SUMMARY
# ==================================================

def get_global_coverage():
    """
    Return global BioFlow implementation progress.
    """

    families = (
        get_catalog_status()
    )

    supported = sum(
        family[
            "supported_count"
        ]
        for family in families
    )

    total = sum(
        family[
            "total_count"
        ]
        for family in families
    )

    percentage = 0

    if total > 0:

        percentage = round(
            (
                supported
                /
                total
            )
            * 100,
            1
        )

    return {
        "supported": supported,
        "total": total,
        "percentage": percentage,
        "families": families
    }
