#!/usr/bin/env python3

from __future__ import annotations

import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_PATH = BASE_DIR / "data/processed/cpii_panel_firm_country_quarter.csv"
OUT_SUMMARY_PATH = BASE_DIR / "outputs/tables/firm_comparison_summary.csv"
OUT_RANK_PATH = BASE_DIR / "outputs/tables/firm_rank_table.csv"
LOG_PATH = BASE_DIR / "logs/firm_comparison_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 27"


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> Optional[float]:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def join_nonempty(values: Iterable[str]) -> str:
    cleaned = sorted({value for value in values if value})
    return "|".join(cleaned)


def quarter_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[-1])


def mean_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def stdev_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if len(cleaned) < 2:
        return None
    return statistics.stdev(cleaned)


def dense_rank_desc(items: List[Tuple[str, float]]) -> Dict[str, int]:
    sorted_items = sorted(items, key=lambda item: (-item[1], item[0]))
    out: Dict[str, int] = {}
    last_value: Optional[float] = None
    current_rank = 0
    for key, value in sorted_items:
        if last_value is None or value != last_value:
            current_rank += 1
            last_value = value
        out[key] = current_rank
    return out


def main() -> None:
    raw_rows = read_csv(INPUT_PATH)
    all_firms = sorted({row["firm_std"] for row in raw_rows if row.get("firm_std", "")})

    raw_computed_rows = [row for row in raw_rows if safe_float(row.get("CPII", "")) is not None]
    firm_quarter_grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    firm_info: Dict[str, Dict[str, str]] = {}
    for row in raw_rows:
        if row.get("firm_std", ""):
            firm_info.setdefault(
                row["firm_std"],
                {
                    "sector_std": row.get("sector_std", ""),
                    "home_country": row.get("home_country", ""),
                },
            )
        if safe_float(row.get("CPII", "")) is None:
            continue
        firm_quarter_grouped[(row["firm_std"], row["year_quarter"])].append(row)

    firm_quarter_rows: List[Dict[str, str]] = []
    firm_quarters_by_firm: Dict[str, Dict[str, Dict[str, object]]] = defaultdict(dict)
    firms_by_sector: Dict[str, set] = defaultdict(set)
    for (firm_std, year_quarter), members in sorted(firm_quarter_grouped.items()):
        i_reg = mean_or_none(safe_float(member["I_reg"]) for member in members)
        i_risk = mean_or_none(safe_float(member["I_risk"]) for member in members)
        i_market = mean_or_none(safe_float(member["I_market"]) for member in members)
        cpii = mean_or_none(safe_float(member["CPII"]) for member in members)
        row = {
            "firm_std": firm_std,
            "sector_std": members[0]["sector_std"],
            "home_country": members[0]["home_country"],
            "year_quarter": year_quarter,
            "country_count_used": str(len({member["country_std"] for member in members if member.get("country_std", "")})),
            "country_list_used": join_nonempty(member["country_std"] for member in members),
            "raw_firm_country_quarter_count": str(len(members)),
            "I_reg": fmt(i_reg),
            "I_risk": fmt(i_risk),
            "I_market": fmt(i_market),
            "CPII": fmt(cpii),
        }
        firm_quarter_rows.append(row)
        firm_quarters_by_firm[firm_std][year_quarter] = {
            "sector_std": members[0]["sector_std"],
            "home_country": members[0]["home_country"],
            "I_reg": i_reg,
            "I_risk": i_risk,
            "I_market": i_market,
            "CPII": cpii,
        }
        firms_by_sector[members[0]["sector_std"]].add(firm_std)

    sector_allfirm_common_quarters: Dict[str, List[str]] = {}
    for sector_std, firms in firms_by_sector.items():
        quarter_sets = []
        for firm_std in sorted(firms):
            quarter_sets.append(set(firm_quarters_by_firm[firm_std].keys()))
        common = set.intersection(*quarter_sets) if quarter_sets else set()
        sector_allfirm_common_quarters[sector_std] = sorted(common, key=quarter_sort_key)

    summary_rows: List[Dict[str, str]] = []
    for firm_std in all_firms:
        info = firm_info.get(firm_std, {"sector_std": "", "home_country": ""})
        sector_std = info["sector_std"]
        home_country = info["home_country"]
        firm_quarter_map = firm_quarters_by_firm.get(firm_std, {})
        firm_quarters = sorted(firm_quarter_map.keys(), key=quarter_sort_key)
        peer_firms = sorted(
            peer
            for peer in firms_by_sector.get(sector_std, set())
            if peer != firm_std
        )
        diff_country_peers = sorted(
            peer
            for peer in peer_firms
            if firm_info.get(peer, {}).get("home_country", "") != home_country
        )

        overlap_quarters = sorted(
            [
                quarter
                for quarter in firm_quarters
                if any(quarter in firm_quarters_by_firm.get(peer, {}) for peer in diff_country_peers)
            ],
            key=quarter_sort_key,
        )
        peer_overlap_rows = [
            firm_quarters_by_firm[peer][quarter]
            for peer in diff_country_peers
            for quarter in overlap_quarters
            if quarter in firm_quarters_by_firm.get(peer, {})
        ]
        common_peer_ready = "yes" if len(overlap_quarters) >= 2 and peer_overlap_rows else "no"

        mean_i_reg = mean_or_none(entry["I_reg"] for entry in firm_quarter_map.values())
        mean_i_risk = mean_or_none(entry["I_risk"] for entry in firm_quarter_map.values())
        mean_i_market = mean_or_none(entry["I_market"] for entry in firm_quarter_map.values())
        mean_cpii = mean_or_none(entry["CPII"] for entry in firm_quarter_map.values())
        cpii_values = [entry["CPII"] for entry in firm_quarter_map.values() if entry["CPII"] is not None]
        mean_common_peer_cpii = mean_or_none(
            firm_quarter_map[quarter]["CPII"] for quarter in overlap_quarters if quarter in firm_quarter_map
        )
        peer_mean_common_peer_cpii = mean_or_none(entry["CPII"] for entry in peer_overlap_rows)
        peer_gap = None
        if mean_common_peer_cpii is not None and peer_mean_common_peer_cpii is not None:
            peer_gap = mean_common_peer_cpii - peer_mean_common_peer_cpii

        summary_rows.append(
            {
                "firm_std": firm_std,
                "sector_std": sector_std,
                "home_country": home_country,
                "comparison_status": "computed" if mean_cpii is not None else "no_cpii_observation",
                "raw_firm_country_quarter_observation_count": str(
                    sum(1 for row in raw_computed_rows if row["firm_std"] == firm_std)
                ),
                "firm_quarter_observation_count": str(len(firm_quarters)),
                "market_country_count_used": str(
                    len(
                        {
                            row["country_std"]
                            for row in raw_computed_rows
                            if row["firm_std"] == firm_std and row.get("country_std", "")
                        }
                    )
                ),
                "market_country_list_used": join_nonempty(
                    row["country_std"]
                    for row in raw_computed_rows
                    if row["firm_std"] == firm_std
                ),
                "year_quarter_min": firm_quarters[0] if firm_quarters else "",
                "year_quarter_max": firm_quarters[-1] if firm_quarters else "",
                "mean_I_reg": fmt(mean_i_reg),
                "mean_I_risk": fmt(mean_i_risk),
                "mean_I_market": fmt(mean_i_market),
                "mean_CPII": fmt(mean_cpii),
                "stddev_CPII": fmt(stdev_or_none(cpii_values)),
                "min_CPII": fmt(min(cpii_values) if cpii_values else None),
                "max_CPII": fmt(max(cpii_values) if cpii_values else None),
                "range_CPII": fmt((max(cpii_values) - min(cpii_values)) if cpii_values else None),
                "sector_peer_count": str(len(peer_firms)),
                "different_home_country_peer_count": str(len(diff_country_peers)),
                "different_home_country_peer_list": join_nonempty(diff_country_peers),
                "cross_country_overlap_quarter_count": str(len(overlap_quarters)),
                "cross_country_overlap_quarters": join_nonempty(overlap_quarters),
                "common_period_ready_flag": common_peer_ready,
                "mean_CPII_common_peer_period": fmt(mean_common_peer_cpii),
                "peer_mean_CPII_common_peer_period": fmt(peer_mean_common_peer_cpii),
                "peer_gap_CPII_common_peer_period": fmt(peer_gap),
                "sector_allfirm_common_quarter_count": str(len(sector_allfirm_common_quarters.get(sector_std, []))),
                "sector_allfirm_common_quarters": join_nonempty(sector_allfirm_common_quarters.get(sector_std, [])),
            }
        )

    computed_summary_rows = [row for row in summary_rows if safe_float(row["mean_CPII"]) is not None]
    overall_rank_map = dense_rank_desc(
        [(row["firm_std"], float(row["mean_CPII"])) for row in computed_summary_rows]
    )

    sector_rank_map: Dict[Tuple[str, str], int] = {}
    common_period_sector_rank_map: Dict[Tuple[str, str], int] = {}
    for sector_std in sorted({row["sector_std"] for row in computed_summary_rows}):
        sector_rows = [row for row in computed_summary_rows if row["sector_std"] == sector_std]
        local_rank = dense_rank_desc([(row["firm_std"], float(row["mean_CPII"])) for row in sector_rows])
        for firm_std, rank in local_rank.items():
            sector_rank_map[(sector_std, firm_std)] = rank

        common_ready_rows = [
            row for row in sector_rows
            if safe_float(row["mean_CPII_common_peer_period"]) is not None
        ]
        common_rank = dense_rank_desc(
            [(row["firm_std"], float(row["mean_CPII_common_peer_period"])) for row in common_ready_rows]
        )
        for firm_std, rank in common_rank.items():
            common_period_sector_rank_map[(sector_std, firm_std)] = rank

    rank_rows: List[Dict[str, str]] = []
    computed_firm_count = len(computed_summary_rows)
    for row in sorted(summary_rows, key=lambda item: (item["sector_std"], item["firm_std"])):
        mean_cpii = safe_float(row["mean_CPII"])
        mean_common = safe_float(row["mean_CPII_common_peer_period"])
        overall_rank = overall_rank_map.get(row["firm_std"])
        sector_rank = sector_rank_map.get((row["sector_std"], row["firm_std"]))
        common_rank = common_period_sector_rank_map.get((row["sector_std"], row["firm_std"]))
        if overall_rank is None:
            rank_group = "no_rank"
        elif overall_rank <= 3:
            rank_group = "top3_high_cpii"
        elif overall_rank > max(computed_firm_count - 3, 0):
            rank_group = "bottom3_low_cpii"
        else:
            rank_group = "middle"

        rank_rows.append(
            {
                "firm_std": row["firm_std"],
                "sector_std": row["sector_std"],
                "home_country": row["home_country"],
                "comparison_status": row["comparison_status"],
                "overall_rank_desc_mean_CPII": str(overall_rank or ""),
                "sector_rank_desc_mean_CPII": str(sector_rank or ""),
                "sector_rank_desc_common_peer_period_CPII": str(common_rank or ""),
                "rank_group": rank_group,
                "mean_CPII": row["mean_CPII"],
                "mean_I_reg": row["mean_I_reg"],
                "mean_I_risk": row["mean_I_risk"],
                "mean_I_market": row["mean_I_market"],
                "stddev_CPII": row["stddev_CPII"],
                "firm_quarter_observation_count": row["firm_quarter_observation_count"],
                "market_country_count_used": row["market_country_count_used"],
                "common_period_ready_flag": row["common_period_ready_flag"],
                "mean_CPII_common_peer_period": row["mean_CPII_common_peer_period"],
                "peer_gap_CPII_common_peer_period": row["peer_gap_CPII_common_peer_period"],
                "different_home_country_peer_count": row["different_home_country_peer_count"],
                "sector_allfirm_common_quarter_count": row["sector_allfirm_common_quarter_count"],
                "rank_direction_note": "higher_cpii_means_worse",
            }
        )

    summary_fields = list(summary_rows[0].keys()) if summary_rows else []
    rank_fields = list(rank_rows[0].keys()) if rank_rows else []
    write_csv(OUT_SUMMARY_PATH, summary_rows, summary_fields)
    write_csv(OUT_RANK_PATH, rank_rows, rank_fields)

    top3 = sorted(
        (
            (row["firm_std"], float(row["mean_CPII"]))
            for row in computed_summary_rows
        ),
        key=lambda item: (-item[1], item[0]),
    )[:3]
    bottom3 = sorted(
        (
            (row["firm_std"], float(row["mean_CPII"]))
            for row in computed_summary_rows
        ),
        key=lambda item: (item[1], item[0]),
    )[:3]
    common_ready_count = sum(1 for row in summary_rows if row["common_period_ready_flag"] == "yes")
    no_obs_firms = sorted(row["firm_std"] for row in summary_rows if row["comparison_status"] == "no_cpii_observation")

    log_lines = [
        "# Firm Comparison Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "- 기업 비교는 `firm-country-quarter` 원패널을 그대로 평균하지 않고, 먼저 `firm-quarter`로 접은 뒤 그 값을 기준으로 요약했다.",
        "- 따라서 시장 수가 많은 기업이 단순 row count 때문에 평균 CPII를 과도하게 지배하지 않도록 조정했다.",
        "",
        "## Coverage",
        f"- input `cpii_panel_firm_country_quarter.csv`: `{len(raw_rows)}` rows",
        f"- computed `firm-country-quarter` rows: `{len(raw_computed_rows)}`",
        f"- collapsed `firm-quarter` rows: `{len(firm_quarter_rows)}`",
        f"- firms in universe: `{len(all_firms)}`",
        f"- firms with computed CPII: `{len(computed_summary_rows)}`",
        f"- firms without computed CPII: `{len(no_obs_firms)}` -> `{join_nonempty(no_obs_firms) or 'none'}`",
        f"- common-peer-period ready firms: `{common_ready_count}`",
        "",
        "## Required Analyses Covered",
        "- 기업별 평균 CPII와 하위 지수 평균을 `firm_comparison_summary.csv`에 기록했다.",
        "- 상위/하위 기업 순위를 `firm_rank_table.csv`에 overall rank와 sector rank로 분리해 기록했다.",
        "- 기간별 변동성은 `stddev_CPII`, `min_CPII`, `max_CPII`, `range_CPII`로 기록했다.",
        "- 동일 섹터 내 국가가 다른 peer 비교는 `peer_mean_CPII_common_peer_period`와 `peer_gap_CPII_common_peer_period`로 기록했다.",
        "- 공통 관측 기간 기준 비교 가능 여부는 `common_period_ready_flag`와 `cross_country_overlap_quarter_count`로 표시했다.",
        "",
        "## Sector Common Periods",
    ]
    for sector_std in sorted(sector_allfirm_common_quarters):
        log_lines.append(
            f"- `{sector_std}` strict common quarters: `{join_nonempty(sector_allfirm_common_quarters[sector_std]) or 'none'}`"
        )
    log_lines.extend(
        [
            "",
            "## Top And Bottom Firms By Mean CPII",
            f"- top 3 high CPII: `{top3}`",
            f"- bottom 3 low CPII: `{bottom3}`",
            "",
            "## Notes",
            "- `common_period_ready_flag=yes`는 같은 섹터의 다른 본국 기업과 겹치는 분기가 2개 이상 있음을 뜻한다.",
            "- 일부 기업은 관측치 1개 또는 0개이므로 rank 해석보다 표본 상태 확인이 우선이다.",
            "- 다음 단계의 국가 비교표는 본 단계와 동일하게 공통 관측 기간과 표본 구성 차이를 함께 표시해야 한다.",
        ]
    )
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_firm_comparison_tables.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds firm comparison summary and ranking tables from the firm-country-quarter CPII panel.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/firm_comparison_summary.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_comparison_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Firm-level summary table with average CPII, subindex means, volatility, and common-period peer comparison fields.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/firm_rank_table.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_comparison_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Firm ranking table with overall and sector ranks based on mean CPII.",
        },
        {
            "artifact_type": "log",
            "path": "logs/firm_comparison_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Coverage, ranking, and common-period comparison notes for firm-level CPII tables.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 기업별 비교 기초통계"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `outputs/tables/firm_comparison_summary.csv`와 `firm_rank_table.csv`를 생성",
                "- firm-country-quarter CPII를 먼저 firm-quarter로 접은 뒤 기업별 평균 CPII, 하위 지수 평균, 기간 변동성, cross-country peer gap을 계산",
                "- `logs/firm_comparison_log.md`에 상하위 기업, 공통 관측 기간, 표본 제약을 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
