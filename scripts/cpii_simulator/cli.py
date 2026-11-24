#!/usr/bin/env python3
"""Command-line entry point for frozen-anchor CPII company scoring."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.engine import ScoringError, flatten_score, read_company_csv, score_rows
    from scripts.cpii_simulator.validate_input import validate_company_rows
else:
    from .engine import ScoringError, flatten_score, read_company_csv, score_rows
    from .validate_input import validate_company_rows


def _csv_safe_value(value: object) -> object:
    if isinstance(value, set):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=isinstance(value, dict))
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip()
    return "'" + value if value[0] in "\t\r\n" or (stripped and stripped[0] in "=+-@") else value


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("no scored rows")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {field: _csv_safe_value(value) for field, value in row.items()}
            for row in rows
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial", action="store_true", help="diagnostic only: permit missing features")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    strict = not args.partial
    try:
        _, issues = validate_company_rows(
            args.company_csv,
            strict=strict,
            require_complete_features=strict,
        )
        errors = [issue for issue in issues if issue.severity == "ERROR"]
        for issue in issues:
            print(issue.render(), file=sys.stderr if issue.severity == "ERROR" else sys.stdout)
        if errors:
            print(f"FAIL scoring input: {len(errors)} validation error(s)", file=sys.stderr)
            return 1
        scored = [flatten_score(row) for row in score_rows(read_company_csv(args.company_csv), strict=strict)]
        write_csv(args.output, scored)
    except (OSError, ValueError, ScoringError, csv.Error) as exc:
        print(f"FAIL scoring: {exc}", file=sys.stderr)
        return 1
    print(f"WROTE {len(scored)} scored companies: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
