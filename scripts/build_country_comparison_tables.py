#!/usr/bin/env python3

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

COUNTRY_CPII_PATH = BASE_DIR / "data/processed/cpii_panel_sector_country_quarter.csv"
FIRM_CPII_PATH = BASE_DIR / "data/processed/cpii_panel_firm_country_quarter.csv"
OUT_SUMMARY_PATH = BASE_DIR / "outputs/tables/country_comparison_summary.csv"
OUT_RANK_PATH = BASE_DIR / "outputs/tables/country_rank_table.csv"
LOG_PATH = BASE_DIR / "logs/country_comparison_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 28"


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


def build_composition_note(
    sector_count_used: int,
    firm_count_used: int,
    domestic_firm_count: int,
    foreign_firm_count: int,
    common_pair_count: int,
    common_pair_universe_count: int,
) -> str:
    notes = []
    if sector_count_used < 3:
        notes.append("partial_sector_coverage")
    if firm_count_used <= 3:
        notes.append("thin_firm_base")
    if domestic_firm_count == 0 and firm_count_used > 0:
        notes.append("foreign_only_composition")
    elif foreign_firm_count == 0 and firm_count_used > 0:
        notes.append("domestic_only_composition")
    else:
        notes.append("mixed_domestic_foreign")
    if common_pair_count < common_pair_universe_count:
        notes.append("common_period_incomplete")
    return "|".join(notes)


def main() -> None:
    country_rows_all = read_csv(COUNTRY_CPII_PATH)
    firm_rows_all = read_csv(FIRM_CPII_PATH)

    country_rows = [row for row in country_rows_all if safe_float(row.get("CPII", "")) is not None]
    firm_rows = [row for row in firm_rows_all if safe_float(row.get("CPII", "")) is not None]

    all_countries = sorted({row["country_std"] for row in country_rows_all if row.get("country_std", "")})

    country_pair_sets: Dict[str, set] = defaultdict(set)
    for row in country_rows:
        country_pair_sets[row["country_std"]].add((row["sector_std"], row["year_quarter"]))
    common_pairs = (
        set.intersection(*(country_pair_sets[country] for country in all_countries))
        if all_countries
        else set()
    )
    common_pairs_sorted = sorted(common_pairs, key=lambda item: (item[0], quarter_sort_key(item[1])))

    country_firm_info: Dict[str, Dict[str, set]] = defaultdict(lambda: {
        "firms": set(),
        "domestic": set(),
        "foreign": set(),
        "sectors": set(),
    })
    for row in firm_rows:
        country = row["country_std"]
        country_firm_info[country]["firms"].add(row["firm_std"])
        country_firm_info[country]["sectors"].add(row["sector_std"])
        if row["home_country"] == country:
            country_firm_info[country]["domestic"].add(row["firm_std"])
        else:
            country_firm_info[country]["foreign"].add(row["firm_std"])

    summary_rows: List[Dict[str, str]] = []
    for country_std in all_countries:
        rows = [row for row in country_rows if row["country_std"] == country_std]
        rows_common = [
            row
            for row in rows
            if (row["sector_std"], row["year_quarter"]) in common_pairs
        ]
        sectors_used = sorted({row["sector_std"] for row in rows})
        quarters_used = sorted({row["year_quarter"] for row in rows}, key=quarter_sort_key)
        common_quarters_used = sorted({row["year_quarter"] for row in rows_common}, key=quarter_sort_key)
        common_sectors_used = sorted({row["sector_std"] for row in rows_common})

        mean_i_reg_all = mean_or_none(safe_float(row["I_reg"]) for row in rows)
        mean_i_risk_all = mean_or_none(safe_float(row["I_risk"]) for row in rows)
        mean_i_market_all = mean_or_none(safe_float(row["I_market"]) for row in rows)
        mean_cpii_all = mean_or_none(safe_float(row["CPII"]) for row in rows)

        mean_i_reg_common = mean_or_none(safe_float(row["I_reg"]) for row in rows_common)
        mean_i_risk_common = mean_or_none(safe_float(row["I_risk"]) for row in rows_common)
        mean_i_market_common = mean_or_none(safe_float(row["I_market"]) for row in rows_common)
        mean_cpii_common = mean_or_none(safe_float(row["CPII"]) for row in rows_common)

        firm_info = country_firm_info.get(country_std, {"firms": set(), "domestic": set(), "foreign": set(), "sectors": set()})
        composition_note = build_composition_note(
            sector_count_used=len(sectors_used),
            firm_count_used=len(firm_info["firms"]),
            domestic_firm_count=len(firm_info["domestic"]),
            foreign_firm_count=len(firm_info["foreign"]),
            common_pair_count=len(rows_common),
            common_pair_universe_count=len(common_pairs_sorted),
        )

        summary_rows.append(
            {
                "country_std": country_std,
                "comparison_status": "computed" if mean_cpii_all is not None else "no_cpii_observation",
                "raw_sector_country_quarter_observation_count": str(len(rows)),
                "sector_count_used": str(len(sectors_used)),
                "sector_list_used": join_nonempty(sectors_used),
                "year_quarter_count_used": str(len(quarters_used)),
                "year_quarter_min": quarters_used[0] if quarters_used else "",
                "year_quarter_max": quarters_used[-1] if quarters_used else "",
                "mean_I_reg_all_obs": fmt(mean_i_reg_all),
                "mean_I_risk_all_obs": fmt(mean_i_risk_all),
                "mean_I_market_all_obs": fmt(mean_i_market_all),
                "mean_CPII_all_obs": fmt(mean_cpii_all),
                "common_pair_universe_count": str(len(common_pairs_sorted)),
                "common_pair_count_used": str(len(rows_common)),
                "common_pair_list_used": join_nonempty(
                    f"{sector}:{quarter}" for sector, quarter in common_pairs_sorted if (sector, quarter) in country_pair_sets[country_std]
                ),
                "common_quarter_count_used": str(len(common_quarters_used)),
                "common_quarter_list_used": join_nonempty(common_quarters_used),
                "common_sector_count_used": str(len(common_sectors_used)),
                "common_sector_list_used": join_nonempty(common_sectors_used),
                "common_period_ready_flag": "yes" if len(rows_common) == len(common_pairs_sorted) and len(common_pairs_sorted) > 0 else "no",
                "mean_I_reg_common_sample": fmt(mean_i_reg_common),
                "mean_I_risk_common_sample": fmt(mean_i_risk_common),
                "mean_I_market_common_sample": fmt(mean_i_market_common),
                "mean_CPII_common_sample": fmt(mean_cpii_common),
                "computed_firm_count_used": str(len(firm_info["firms"])),
                "computed_firm_list_used": join_nonempty(firm_info["firms"]),
                "domestic_home_firm_count": str(len(firm_info["domestic"])),
                "domestic_home_firm_list": join_nonempty(firm_info["domestic"]),
                "foreign_home_firm_count": str(len(firm_info["foreign"])),
                "foreign_home_firm_list": join_nonempty(firm_info["foreign"]),
                "composition_limit_note": composition_note,
            }
        )

    global_mean_all = mean_or_none(safe_float(row["mean_CPII_all_obs"]) for row in summary_rows)
    global_mean_common = mean_or_none(safe_float(row["mean_CPII_common_sample"]) for row in summary_rows)

    for row in summary_rows:
        mean_all = safe_float(row["mean_CPII_all_obs"])
        mean_common = safe_float(row["mean_CPII_common_sample"])
        row["gap_vs_global_mean_all_obs"] = fmt(mean_all - global_mean_all if mean_all is not None and global_mean_all is not None else None)
        row["gap_vs_global_mean_common_sample"] = fmt(mean_common - global_mean_common if mean_common is not None and global_mean_common is not None else None)

    top_country_all = max(
        (safe_float(row["mean_CPII_all_obs"]) for row in summary_rows if safe_float(row["mean_CPII_all_obs"]) is not None),
        default=None,
    )
    bottom_country_all = min(
        (safe_float(row["mean_CPII_all_obs"]) for row in summary_rows if safe_float(row["mean_CPII_all_obs"]) is not None),
        default=None,
    )
    top_country_common = max(
        (safe_float(row["mean_CPII_common_sample"]) for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None),
        default=None,
    )
    bottom_country_common = min(
        (safe_float(row["mean_CPII_common_sample"]) for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None),
        default=None,
    )
    for row in summary_rows:
        mean_all = safe_float(row["mean_CPII_all_obs"])
        mean_common = safe_float(row["mean_CPII_common_sample"])
        row["gap_to_top_country_all_obs"] = fmt(mean_all - top_country_all if mean_all is not None and top_country_all is not None else None)
        row["gap_to_bottom_country_all_obs"] = fmt(mean_all - bottom_country_all if mean_all is not None and bottom_country_all is not None else None)
        row["gap_to_top_country_common_sample"] = fmt(mean_common - top_country_common if mean_common is not None and top_country_common is not None else None)
        row["gap_to_bottom_country_common_sample"] = fmt(mean_common - bottom_country_common if mean_common is not None and bottom_country_common is not None else None)

    rank_all_map = dense_rank_desc(
        [(row["country_std"], float(row["mean_CPII_all_obs"])) for row in summary_rows if safe_float(row["mean_CPII_all_obs"]) is not None]
    )
    rank_common_map = dense_rank_desc(
        [(row["country_std"], float(row["mean_CPII_common_sample"])) for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None]
    )

    rank_rows: List[Dict[str, str]] = []
    computed_common_count = sum(1 for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None)
    for row in sorted(summary_rows, key=lambda item: item["country_std"]):
        rank_all = rank_all_map.get(row["country_std"])
        rank_common = rank_common_map.get(row["country_std"])
        if rank_common is None:
            rank_group = "no_rank"
        elif rank_common <= 3:
            rank_group = "top3_high_cpii_common_sample"
        elif rank_common > max(computed_common_count - 3, 0):
            rank_group = "bottom3_low_cpii_common_sample"
        else:
            rank_group = "middle"
        rank_rows.append(
            {
                "country_std": row["country_std"],
                "comparison_status": row["comparison_status"],
                "overall_rank_desc_mean_CPII_all_obs": str(rank_all or ""),
                "overall_rank_desc_mean_CPII_common_sample": str(rank_common or ""),
                "rank_group": rank_group,
                "mean_CPII_all_obs": row["mean_CPII_all_obs"],
                "mean_CPII_common_sample": row["mean_CPII_common_sample"],
                "mean_I_reg_common_sample": row["mean_I_reg_common_sample"],
                "mean_I_risk_common_sample": row["mean_I_risk_common_sample"],
                "mean_I_market_common_sample": row["mean_I_market_common_sample"],
                "gap_vs_global_mean_common_sample": row["gap_vs_global_mean_common_sample"],
                "computed_firm_count_used": row["computed_firm_count_used"],
                "domestic_home_firm_count": row["domestic_home_firm_count"],
                "foreign_home_firm_count": row["foreign_home_firm_count"],
                "sector_count_used": row["sector_count_used"],
                "common_pair_count_used": row["common_pair_count_used"],
                "common_period_ready_flag": row["common_period_ready_flag"],
                "composition_limit_note": row["composition_limit_note"],
                "rank_direction_note": "higher_cpii_means_worse",
            }
        )

    summary_fields = list(summary_rows[0].keys()) if summary_rows else []
    rank_fields = list(rank_rows[0].keys()) if rank_rows else []
    write_csv(OUT_SUMMARY_PATH, summary_rows, summary_fields)
    write_csv(OUT_RANK_PATH, rank_rows, rank_fields)

    top3_common = sorted(
        ((row["country_std"], float(row["mean_CPII_common_sample"])) for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None),
        key=lambda item: (-item[1], item[0]),
    )[:3]
    bottom3_common = sorted(
        ((row["country_std"], float(row["mean_CPII_common_sample"])) for row in summary_rows if safe_float(row["mean_CPII_common_sample"]) is not None),
        key=lambda item: (item[1], item[0]),
    )[:3]

    log_lines = [
        "# Country Comparison Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "- 국가 비교는 `sector-country-quarter` CPII를 기준으로 수행하고, `전체 관측 평균`과 `공통 sector-quarter 표본 평균`을 분리해 기록했다.",
        "- 공통 비교 표본은 모든 retained country에서 동시에 관측되는 `sector-quarter`의 교집합으로 정의했다.",
        "",
        "## Coverage",
        f"- input `cpii_panel_sector_country_quarter.csv`: `{len(country_rows_all)}` rows",
        f"- computed `sector-country-quarter` rows: `{len(country_rows)}`",
        f"- countries in comparison: `{len(all_countries)}`",
        f"- common sector-quarter universe count: `{len(common_pairs_sorted)}`",
        f"- common sector-quarter universe: `{join_nonempty(f'{sector}:{quarter}' for sector, quarter in common_pairs_sorted)}`",
        "",
        "## Required Analyses Covered",
        "- 국가별 평균 CPII와 하위 지수 평균을 `country_comparison_summary.csv`에 기록했다.",
        "- 공통 기간 기준 비교는 `mean_CPII_common_sample`와 `common_pair_count_used`로 분리 기록했다.",
        "- 국가 간 격차는 global mean 대비 gap과 top/bottom country 대비 gap으로 기록했다.",
        "- 기업구성이 다른 경우의 비교 제한은 `domestic_home_firm_count`, `foreign_home_firm_count`, `composition_limit_note`로 남겼다.",
        "- 국가별 표본 구성 차이는 sector coverage, firm count, domestic/foreign mix로 함께 표시했다.",
        "",
        "## Top And Bottom Countries By Common Sample Mean CPII",
        f"- top 3 high CPII: `{top3_common}`",
        f"- bottom 3 low CPII: `{bottom3_common}`",
        "",
        "## Composition Notes",
        "- `foreign_only_composition`은 해당 국가의 계산된 firm 표본이 모두 비본국 기업이라는 뜻이다.",
        "- `partial_sector_coverage`는 webtoon 또는 일부 sector가 빠져 국가 평균 해석이 제한됨을 뜻한다.",
        "- `thin_firm_base`는 계산 가능한 firm 수가 3개 이하인 국가를 의미한다.",
        "",
        "## Notes",
        "- 현재 공통 표본에서는 webtoon이 빠지고 `digital_infra 2025Q3~2025Q4`, `music 2025Q4~2026Q1`만 남는다.",
        "- 따라서 공통기간 기준 rank는 국가 전반 순위라기보다 `공통으로 관측된 인프라+음악 구간` 비교로 읽어야 한다.",
        "- 다음 단계의 시계열 분석은 본 단계의 country rank보다 quarter-level 변화와 전환점 후보를 우선 보여줘야 한다.",
    ]
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_country_comparison_tables.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds country comparison summary and ranking tables from the sector-country-quarter CPII panel.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/country_comparison_summary.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_comparison_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Country-level summary table with all-observation means, common-sample means, composition fields, and comparison gaps.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/country_rank_table.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_comparison_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Country ranking table with all-observation and common-sample CPII ranks plus composition flags.",
        },
        {
            "artifact_type": "log",
            "path": "logs/country_comparison_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Coverage, common-sample definition, and interpretation limits for country CPII comparison tables.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 국가별 비교 기초통계"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `outputs/tables/country_comparison_summary.csv`와 `country_rank_table.csv`를 생성",
                "- `sector-country-quarter` CPII 기준으로 국가별 평균 CPII, 하위 지수 평균, 공통 표본 평균, 국가 간 gap, firm composition 제약을 계산",
                "- `logs/country_comparison_log.md`에 공통 sector-quarter 표본 정의와 해석 제한을 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
