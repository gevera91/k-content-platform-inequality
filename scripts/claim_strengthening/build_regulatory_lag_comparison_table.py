#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ENFORCEMENT_PANEL_PATH = ROOT / "data/processed/claim_strengthening/regulatory_enforcement_evidence_panel.csv"
MATCHED_PEER_PATH = ROOT / "data/processed/claim_strengthening/matched_peer_registry.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/regulatory_lag_comparison_table.csv"
SUMMARY_PATH = ROOT / "outputs/tables/claim_strengthening/T_claim_reg_lag_summary.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/regulatory_lag_comparison_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def parse_date_label(value: str) -> tuple[date | None, str]:
    if not value:
        return None, "missing"
    if value.startswith("pre-"):
        inner = value[4:]
        parsed, _ = parse_date_label(inner)
        return parsed, "left_censored"
    if value.startswith("stayed_"):
        inner = value.split("_", 1)[1]
        parsed, _ = parse_date_label(inner)
        return parsed, "modified"
    try:
        parts = value.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2])), "exact_day"
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1), "exact_month"
        if len(parts) == 1 and len(parts[0]) == 4:
            return date(int(parts[0]), 1, 1), "exact_year"
    except ValueError:
        return None, "unparseable"
    return None, "unparseable"


def month_diff(domestic: date, global_: date) -> int:
    return (domestic.year - global_.year) * 12 + (domestic.month - global_.month)


def peer_service_map(rows: list[dict[str, str]]) -> dict[str, dict[str, set[str]]]:
    out: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        bucket = out.setdefault(row["peer_group_id"], {"korean": set(), "global": set()})
        bucket["korean"].add(row["korean_service_std"])
        bucket["global"].add(row["global_service_std"])
    return out


def observed_peer_groups(rows: list[dict[str, str]]) -> list[str]:
    groups = sorted({row["peer_group_id"] for row in rows})
    return groups


def first_relevant(rows: list[dict[str, str]], basis: str) -> tuple[str, date | None, str]:
    if basis == "law":
        candidates = [r for r in rows if r["law_exists_flag"] == "yes" and r["law_effective_date"]]
        value_key = "law_effective_date"
    else:
        candidates = [r for r in rows if r["enforced_flag"] == "yes" and r["first_enforcement_date"]]
        value_key = "first_enforcement_date"

    if not candidates:
        return "", None, "missing"

    scored: list[tuple[date, str, str]] = []
    fallback_label = candidates[0][value_key]
    fallback_status = "unparseable"
    for row in candidates:
        parsed, status = parse_date_label(row[value_key])
        if parsed is not None:
            scored.append((parsed, row[value_key], status))
        else:
            fallback_label = row[value_key]
            fallback_status = status
    if not scored:
        return fallback_label, None, fallback_status
    scored.sort(key=lambda x: x[0])
    best = scored[0]
    return best[1], best[0], best[2]


def interpretation_for(
    basis: str,
    domestic_label: str,
    domestic_parsed: date | None,
    domestic_status: str,
    global_label: str,
    global_parsed: date | None,
    global_status: str,
    lag: str,
) -> str:
    basis_ko = "규제 도입" if basis == "law" else "집행"
    if not domestic_label and not global_label:
        return f"국내와 글로벌 모두 서비스-매칭된 {basis_ko} 날짜가 없어 직접 시차 비교가 불가하다."
    if not domestic_label:
        return f"국내 서비스-매칭 {basis_ko} 날짜가 없어 글로벌 peer와 직접 시차 비교가 불가하다."
    if not global_label:
        return f"글로벌 peer의 서비스-매칭 {basis_ko} 날짜가 없어 직접 시차 비교가 불가하다."
    if domestic_status in {"left_censored", "unparseable"} or global_status in {"left_censored", "unparseable"}:
        return f"한쪽 이상이 정확한 날짜가 아니라 left-censored 또는 불완전 날짜라서 {basis_ko} 월차를 계산하지 않았다."
    if lag == "":
        return f"{basis_ko} 날짜는 양쪽 모두 존재하지만 월차 계산에 필요한 정규화가 충분하지 않다."

    lag_int = int(lag)
    if lag_int < 0:
        return f"국내 {basis_ko}가 글로벌 peer보다 {abs(lag_int)}개월 빠르다."
    if lag_int > 0:
        return f"국내 {basis_ko}가 글로벌 peer보다 {lag_int}개월 늦다."
    return f"국내와 글로벌 peer의 {basis_ko} 시점이 같은 월로 관측된다."


def build_rows() -> list[dict[str, str]]:
    enforcement_rows = read_csv(ENFORCEMENT_PANEL_PATH)
    matched_rows = read_csv(MATCHED_PEER_PATH)
    peer_map = peer_service_map(matched_rows)
    groups = [g for g in observed_peer_groups(enforcement_rows) if g in peer_map]
    obligations = sorted({row["obligation_id"] for row in enforcement_rows})

    output_rows: list[dict[str, str]] = []
    for peer_group_id in groups:
        korean_services = peer_map[peer_group_id]["korean"]
        global_services = peer_map[peer_group_id]["global"]

        peer_rows = [r for r in enforcement_rows if r["peer_group_id"] == peer_group_id]
        domestic_pool = [
            r for r in peer_rows if r["country_std"] == "kr" and r["service_std"] in korean_services
        ]
        global_pool = [
            r for r in peer_rows if r["country_std"] != "kr" and r["service_std"] in global_services
        ]

        for obligation_id in obligations:
            domestic_obligation_rows = [r for r in domestic_pool if r["obligation_id"] == obligation_id]
            global_obligation_rows = [r for r in global_pool if r["obligation_id"] == obligation_id]

            for basis in ("law", "enforcement"):
                domestic_label, domestic_parsed, domestic_status = first_relevant(domestic_obligation_rows, basis)
                global_label, global_parsed, global_status = first_relevant(global_obligation_rows, basis)

                lag = ""
                if (
                    domestic_parsed is not None
                    and global_parsed is not None
                    and domestic_status not in {"left_censored", "unparseable"}
                    and global_status not in {"left_censored", "unparseable"}
                ):
                    lag = str(month_diff(domestic_parsed, global_parsed))

                output_rows.append(
                    {
                        "peer_group_id": peer_group_id,
                        "comparison_basis": basis,
                        "obligation_id": obligation_id,
                        "domestic_first_date": domestic_label,
                        "global_first_date": global_label,
                        "lag_months_domestic_minus_global": lag,
                        "interpretation": interpretation_for(
                            basis,
                            domestic_label,
                            domestic_parsed,
                            domestic_status,
                            global_label,
                            global_parsed,
                            global_status,
                            lag,
                        ),
                        "domestic_date_status": domestic_status,
                        "global_date_status": global_status,
                        "domestic_service_pool": "|".join(sorted(korean_services)),
                        "global_service_pool": "|".join(sorted(global_services)),
                    }
                )

    output_rows.sort(key=lambda r: (r["peer_group_id"], r["comparison_basis"], r["obligation_id"]))
    return output_rows


def build_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["peer_group_id"], row["comparison_basis"])].append(row)

    summary_rows: list[dict[str, str]] = []
    for (peer_group_id, basis), group_rows in sorted(grouped.items()):
        numeric = [int(r["lag_months_domestic_minus_global"]) for r in group_rows if r["lag_months_domestic_minus_global"] != ""]
        domestic_available = sum(1 for r in group_rows if r["domestic_first_date"])
        global_available = sum(1 for r in group_rows if r["global_first_date"])
        earlier = sum(1 for x in numeric if x < 0)
        later = sum(1 for x in numeric if x > 0)
        same = sum(1 for x in numeric if x == 0)
        non_comparable = len(group_rows) - len(numeric)
        if numeric:
            avg_lag = f"{sum(numeric) / len(numeric):.2f}"
            headline = (
                "domestic_earlier_on_average"
                if float(avg_lag) < 0
                else "domestic_later_on_average"
                if float(avg_lag) > 0
                else "same_month_on_average"
            )
        else:
            avg_lag = ""
            headline = "no_numeric_lag_available"

        summary_rows.append(
            {
                "peer_group_id": peer_group_id,
                "comparison_basis": basis,
                "obligation_rows": str(len(group_rows)),
                "domestic_date_available_count": str(domestic_available),
                "global_date_available_count": str(global_available),
                "numeric_lag_count": str(len(numeric)),
                "domestic_earlier_count": str(earlier),
                "domestic_later_count": str(later),
                "same_month_count": str(same),
                "non_comparable_count": str(non_comparable),
                "avg_lag_months_domestic_minus_global": avg_lag,
                "headline_result": headline,
            }
        )

    return summary_rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]], summary_rows: list[dict[str, str]]) -> None:
    total = len(rows)
    numeric = sum(1 for r in rows if r["lag_months_domestic_minus_global"] != "")
    law_rows = [r for r in rows if r["comparison_basis"] == "law"]
    enforcement_rows = [r for r in rows if r["comparison_basis"] == "enforcement"]
    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 17. 규제 도입·집행 시차 테이블 작성\n\n")
        f.write("- `regulatory_lag_comparison_table.csv`는 peer group별로 한국 서비스와 글로벌 peer의 earliest law/enforcement date를 obligation 단위로 맞대어 비교한 표다.\n")
        f.write("- 이번 단계는 `comparison_basis = law`와 `comparison_basis = enforcement`를 분리해 저장했고, 날짜가 없거나 left-censored인 경우에는 월차를 계산하지 않고 해석 문장으로만 남겼다.\n")
        f.write("- 현재 direct regulatory evidence 구조상 글로벌 side의 service-matched law/enforcement date가 거의 비어 있어 numeric lag는 매우 제한적이며, 이 사실 자체가 현재 strengthening chain의 규제시차 증거가 아직 얇다는 점을 보여준다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(f"- law rows: `{len(law_rows)}`\n")
        f.write(f"- enforcement rows: `{len(enforcement_rows)}`\n")
        f.write(f"- numeric lag rows: `{numeric}`\n")
        for row in summary_rows:
            f.write(
                f"- {row['peer_group_id']} | {row['comparison_basis']}: numeric `{row['numeric_lag_count']}`, non-comparable `{row['non_comparable_count']}`, headline `{row['headline_result']}`\n"
            )


def main() -> None:
    rows = build_rows()
    summary_rows = build_summary(rows)
    write_csv(
        OUTPUT_PATH,
        rows,
        [
            "peer_group_id",
            "comparison_basis",
            "obligation_id",
            "domestic_first_date",
            "global_first_date",
            "lag_months_domestic_minus_global",
            "interpretation",
            "domestic_date_status",
            "global_date_status",
            "domestic_service_pool",
            "global_service_pool",
        ],
    )
    write_csv(
        SUMMARY_PATH,
        summary_rows,
        [
            "peer_group_id",
            "comparison_basis",
            "obligation_rows",
            "domestic_date_available_count",
            "global_date_available_count",
            "numeric_lag_count",
            "domestic_earlier_count",
            "domestic_later_count",
            "same_month_count",
            "non_comparable_count",
            "avg_lag_months_domestic_minus_global",
            "headline_result",
        ],
    )
    write_log(rows, summary_rows)


if __name__ == "__main__":
    main()
