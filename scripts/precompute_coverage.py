"""Generate the static coverage artifact from this checkout's catalogues."""

import argparse
import json
from pathlib import Path

from engine.catalog import get_global_coverage


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "build" / "coverage.json"


def generate(output: Path = DEFAULT_OUTPUT) -> dict:
    payload = get_global_coverage()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = generate(args.output)
    print(f"Wrote {args.output}: {payload['supported']}/{payload['total']} goals")


if __name__ == "__main__":
    main()
