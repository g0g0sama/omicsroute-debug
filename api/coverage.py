"""The static catalogue snapshot used by ordinary coverage requests."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from engine.catalog import get_global_coverage


COVERAGE_PATH = Path(__file__).resolve().parents[1] / "build" / "coverage.json"


class _CoveragePayload(BaseModel):
    supported: int = Field(ge=0)
    total: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    families: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_startup_coverage() -> dict[str, Any]:
    """Load once per process; calculate once when developing without a build."""
    if not COVERAGE_PATH.exists():
        return get_global_coverage()

    try:
        payload = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
        _CoveragePayload.model_validate(payload, strict=True)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Invalid coverage artifact at {COVERAGE_PATH}. "
            "Regenerate it with: python -m scripts.precompute_coverage"
        ) from exc
    return payload
