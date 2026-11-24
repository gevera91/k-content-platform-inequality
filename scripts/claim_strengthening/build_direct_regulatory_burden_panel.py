#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

OBLIGATION_INPUTS = [
    ("kr", ROOT / "data/interim/claim_strengthening/kr_regulatory_obligations_core.csv"),
    ("us", ROOT / "data/interim/claim_strengthening/us_regulatory_obligations_core.csv"),
    ("mixed", ROOT / "data/interim/claim_strengthening/jp_uk_regulatory_obligations_core.csv"),
    ("mixed", ROOT / "data/interim/claim_strengthening/ca_tw_regulatory_obligations_core.csv"),
]
ENFORCEMENT_PATH = ROOT / "data/processed/claim_strengthening/regulatory_enforcement_evidence_panel.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/direct_regulatory_burden_panel.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/direct_regulatory_burden_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def normalize_obligation_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for mode, path in OBLIGATION_INPUTS:
        for row in read_csv(path):
            normalized = dict(row)
            if mode in {"kr", "us"}:
                normalized["country_std"] = mode
            rows.append(normalized)
    return rows


def load_enforcement_map() -> dict[tuple[str, str, str, str], dict[str, str]]:
    rows = read_csv(ENFORCEMENT_PATH)
    return {
        (r["country_std"], r["firm_std"], r["service_std"], r["obligation_id"]): r
        for r in rows
    }


def safe_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def dense_rank(rows: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["peer_group_id"]].append(row)

    for peer_group_id, peer_rows in grouped.items():
        ordered = sorted(
            peer_rows,
            key=lambda r: (
                -safe_int(r["obligation_intensity_score"]),
                -safe_int(r["obligation_count"]),
                -safe_int(r["enforced_obligation_score"]),
                r["country_std"],
                r["service_std"],
                r["firm_std"],
            ),
        )
        rank = 0
        prev_key: tuple[int, int, int] | None = None
        for row in ordered:
            current_key = (
                safe_int(row["obligation_intensity_score"]),
                safe_int(row["obligation_count"]),
                safe_int(row["enforced_obligation_score"]),
            )
            if current_key != prev_key:
                rank += 1
                prev_key = current_key
            row["burden_rank_within_peer"] = str(rank)


def build_rows() -> list[dict[str, str]]:
    obligation_rows = normalize_obligation_rows()
    enforcement_map = load_enforcement_map()

    buckets: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in obligation_rows:
        key = (
            row["peer_group_id"],
            row["firm_std"],
            row["service_std"],
            row["country_std"],
        )
        bucket = buckets.setdefault(
            key,
            {
                "peer_group_id": row["peer_group_id"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "country_std": row["country_std"],
                "obligation_count": 0,
                "obligation_intensity_score": 0,
                "enforced_obligation_score": 0,
                "unclear_obligation_count": 0,
                "scope_no_obligation_count": 0,
                "law_exists_yes_count": 0,
                "evidence_profile": set(),
            },
        )

        merged = enforcement_map[
            (row["country_std"], row["firm_std"], row["service_std"], row["obligation_id"])
        ]
        burden = safe_int(row.get("burden_score", ""))
        if merged["law_exists_flag"] == "yes":
            bucket["obligation_count"] = int(bucket["obligation_count"]) + 1
            bucket["obligation_intensity_score"] = int(bucket["obligation_intensity_score"]) + burden
            bucket["law_exists_yes_count"] = int(bucket["law_exists_yes_count"]) + 1
        elif merged["law_exists_flag"] == "unclear":
            bucket["unclear_obligation_count"] = int(bucket["unclear_obligation_count"]) + 1
        else:
            bucket["scope_no_obligation_count"] = int(bucket["scope_no_obligation_count"]) + 1

        if merged["enforced_flag"] == "yes":
            bucket["enforced_obligation_score"] = int(bucket["enforced_obligation_score"]) + burden

        bucket["evidence_profile"].add(merged["evidence_strength"])

    output_rows: list[dict[str, str]] = []
    for bucket in buckets.values():
        profile = sorted(str(x) for x in bucket["evidence_profile"])
        output_rows.append(
            {
                "peer_group_id": str(bucket["peer_group_id"]),
                "firm_std": str(bucket["firm_std"]),
                "service_std": str(bucket["service_std"]),
                "country_std": str(bucket["country_std"]),
                "obligation_count": str(bucket["obligation_count"]),
                "obligation_intensity_score": str(bucket["obligation_intensity_score"]),
                "enforced_obligation_score": str(bucket["enforced_obligation_score"]),
                "burden_rank_within_peer": "",
                "unclear_obligation_count": str(bucket["unclear_obligation_count"]),
                "scope_no_obligation_count": str(bucket["scope_no_obligation_count"]),
                "law_exists_yes_count": str(bucket["law_exists_yes_count"]),
                "evidence_profile": "|".join(profile),
            }
        )

    dense_rank(output_rows)
    output_rows.sort(key=lambda r: (r["peer_group_id"], int(r["burden_rank_within_peer"]), r["country_std"], r["service_std"], r["firm_std"]))
    return output_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "obligation_count",
        "obligation_intensity_score",
        "enforced_obligation_score",
        "burden_rank_within_peer",
        "unclear_obligation_count",
        "scope_no_obligation_count",
        "law_exists_yes_count",
        "evidence_profile",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["peer_group_id"]].append(row)

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 18. 규제부담 직접 점수표 작성\n\n")
        f.write("- `direct_regulatory_burden_panel.csv`는 국가별 obligation table의 `burden_score`와 enforcement evidence panel의 `law_exists/enforced` 판정을 결합해 peer 내부 직접 burden 점수표로 접은 결과다.\n")
        f.write("- `obligation_count`는 `law_exists_flag = yes`인 의무 수, `obligation_intensity_score`는 그 의무들의 burden score 합계, `enforced_obligation_score`는 `enforced_flag = yes`인 의무의 burden score 합계로 정의했다.\n")
        f.write("- 현재 strengthening chain에는 service-matched enforcement evidence가 없어 `enforced_obligation_score`는 전 행 `0`으로 남는다.\n")
        f.write("- 따라서 이번 표의 실질 정보력은 `obligation_intensity_score`와 peer 내부 상대순위에 있다.\n\n")
        f.write(f"- total rows: `{len(rows)}`\n")
        for peer_group_id, peer_rows in sorted(grouped.items()):
            best = max(peer_rows, key=lambda r: (safe_int(r['obligation_intensity_score']), safe_int(r['obligation_count'])))
            f.write(
                f"- {peer_group_id}: rows `{len(peer_rows)}`, top `{best['country_std']}:{best['service_std']}` intensity `{best['obligation_intensity_score']}`, rank `{best['burden_rank_within_peer']}`\n"
            )


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
