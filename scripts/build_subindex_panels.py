#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_PATH = BASE_DIR / "data/processed/variable_panel_sector_quarter.csv"
OUT_SECTOR_QUARTER_PATH = BASE_DIR / "data/processed/subindex_panel_sector_quarter.csv"
OUT_SECTOR_COUNTRY_QUARTER_PATH = BASE_DIR / "data/processed/subindex_panel_sector_country_quarter.csv"
LOG_PATH = BASE_DIR / "logs/subindex_calculation_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 25"

COUNTRY_SPEC_CODE = "SCQ_EXPANDED_REDUCED_V1"
BASE_SPEC_CODE = "SQ_BASE_PRIMARY_REDUCED_V1"
ANCHOR_SPEC_CODE = "POOL_SCQ_P01_P99_EMP_RANK_V1"
WINSOR_P_LOWER = 0.01
WINSOR_P_UPPER = 0.99
MISSING_SHARE_THRESHOLD = 0.40

SUBINDEX_COMPONENTS = {
    "I_reg": [
        "effective_tax_rate_gap",
        "network_cost_ratio",
        "infra_dependency_ratio",
    ],
    "I_risk": [
        "funding_cost_spread",
        "ip_assetization_gap",
        "investment_recovery_ratio",
        "cashflow_recovery_ratio",
        "creator_share_ratio",
    ],
    "I_market": [
        "bundle_leverage_index",
        "cross_market_transfer_index",
        "foreign_dependency_ratio",
        "outflow_to_capex_ratio",
    ],
}

VARIABLE_DIRECTION = {
    "effective_tax_rate_gap": 1,
    "network_cost_ratio": 1,
    "infra_dependency_ratio": 1,
    "funding_cost_spread": 1,
    "ip_assetization_gap": 1,
    "investment_recovery_ratio": -1,
    "cashflow_recovery_ratio": -1,
    "creator_share_ratio": -1,
    "bundle_leverage_index": 1,
    "cross_market_transfer_index": 1,
    "foreign_dependency_ratio": 1,
    "outflow_to_capex_ratio": 1,
}

VARIABLE_LOG_RULE = {
    "effective_tax_rate_gap": "signed_log1p",
    "network_cost_ratio": "signed_log1p",
    "infra_dependency_ratio": "signed_log1p",
    "funding_cost_spread": "signed_log1p",
    "ip_assetization_gap": "signed_log1p",
    "investment_recovery_ratio": "signed_log1p",
    "cashflow_recovery_ratio": "signed_log1p",
    "creator_share_ratio": "identity",
    "bundle_leverage_index": "identity",
    "cross_market_transfer_index": "signed_log1p",
    "foreign_dependency_ratio": "identity",
    "outflow_to_capex_ratio": "signed_log1p",
}


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


def quantile(values: List[float], p: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return ordered[lo]
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def signed_log1p(value: float) -> float:
    if value == 0:
        return 0.0
    return math.copysign(math.log1p(abs(value)), value)


def average_rank_percentiles(indexed_values: List[Tuple[int, float]]) -> Dict[int, float]:
    if len(indexed_values) < 2:
        return {}
    ordered = sorted(indexed_values, key=lambda item: item[1])
    out: Dict[int, float] = {}
    i = 0
    n = len(ordered)
    while i < n:
        j = i
        current_value = ordered[i][1]
        while j + 1 < n and ordered[j + 1][1] == current_value:
            j += 1
        avg_rank = ((i + 1) + (j + 1)) / 2
        percentile = (avg_rank - 1) / (n - 1)
        for k in range(i, j + 1):
            out[ordered[k][0]] = percentile
        i = j + 1
    return out


def join_nonempty(values: Iterable[str]) -> str:
    cleaned = sorted({value for value in values if value})
    return "|".join(cleaned)


def variable_pipeline(
    rows: List[Dict[str, str]],
) -> Tuple[
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, str]],
    Dict[str, Dict[str, str]],
]:
    normalized_by_row: Dict[str, Dict[str, float]] = defaultdict(dict)
    variable_stats: Dict[str, Dict[str, str]] = {}
    inactive_variables: Dict[str, Dict[str, str]] = {}

    all_variables = sorted({variable for items in SUBINDEX_COMPONENTS.values() for variable in items})
    row_ids = [row["panel_sector_quarter_id"] for row in rows]

    for variable_name in all_variables:
        observed: List[Tuple[int, float, float, float]] = []
        direction = VARIABLE_DIRECTION[variable_name]
        log_rule = VARIABLE_LOG_RULE[variable_name]

        for idx, row in enumerate(rows):
            raw_value = safe_float(row.get(variable_name, ""))
            if raw_value is None:
                continue
            directed = raw_value * direction
            transformed = signed_log1p(directed) if log_rule == "signed_log1p" else directed
            observed.append((idx, raw_value, directed, transformed))

        if len(observed) < 2:
            inactive_variables[variable_name] = {
                "reason": "n_lt_2",
                "n_obs": str(len(observed)),
            }
            continue

        transformed_values = [item[3] for item in observed]
        lower = quantile(transformed_values, WINSOR_P_LOWER)
        upper = quantile(transformed_values, WINSOR_P_UPPER)
        winsorized = [(idx, min(max(transformed, lower), upper)) for idx, _, _, transformed in observed]
        winsorized_values = [value for _, value in winsorized]
        unique_count = len(set(winsorized_values))

        if unique_count < 2:
            inactive_variables[variable_name] = {
                "reason": "winsorized_zero_variation",
                "n_obs": str(len(observed)),
                "winsor_lower": fmt(lower),
                "winsor_upper": fmt(upper),
            }
            continue

        percentiles = average_rank_percentiles(winsorized)
        if not percentiles:
            inactive_variables[variable_name] = {
                "reason": "normalization_not_feasible",
                "n_obs": str(len(observed)),
                "winsor_lower": fmt(lower),
                "winsor_upper": fmt(upper),
            }
            continue

        for idx, raw_value, directed, transformed in observed:
            winsor_value = min(max(transformed, lower), upper)
            row_id = row_ids[idx]
            normalized_by_row[row_id][variable_name] = percentiles[idx]

        variable_stats[variable_name] = {
            "n_obs": str(len(observed)),
            "direction_code": str(direction),
            "log_rule": log_rule,
            "winsor_lower": fmt(lower),
            "winsor_upper": fmt(upper),
            "winsor_p_lower": fmt(WINSOR_P_LOWER),
            "winsor_p_upper": fmt(WINSOR_P_UPPER),
            "unique_count_post_winsor": str(unique_count),
            "anchor_spec_code": ANCHOR_SPEC_CODE,
            "status": "active",
        }

    return normalized_by_row, variable_stats, inactive_variables


def subindex_components_active(
    variable_stats: Dict[str, Dict[str, str]],
) -> Dict[str, List[str]]:
    return {
        subindex_name: [variable for variable in components if variable in variable_stats]
        for subindex_name, components in SUBINDEX_COMPONENTS.items()
    }


def calculate_country_panel(
    rows: List[Dict[str, str]],
    normalized_by_row: Dict[str, Dict[str, float]],
    variable_stats: Dict[str, Dict[str, str]],
    inactive_variables: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, str]], Dict[str, Counter], Dict[str, List[str]]]:
    active_components = subindex_components_active(variable_stats)
    component_counts: Dict[str, Counter] = {
        "active": Counter(),
        "computed": Counter(),
        "blocked": Counter(),
    }
    inactive_by_subindex: Dict[str, List[str]] = {
        subindex_name: [variable for variable in SUBINDEX_COMPONENTS[subindex_name] if variable in inactive_variables]
        for subindex_name in SUBINDEX_COMPONENTS
    }

    out_rows: List[Dict[str, str]] = []
    for row in rows:
        row_id = row["panel_sector_quarter_id"]
        normalized_values = normalized_by_row.get(row_id, {})
        out_row = {
            "panel_sector_quarter_id": row["panel_sector_quarter_id"],
            "sector_std": row["sector_std"],
            "country_std": row["country_std"],
            "country_priority_tier": row["country_priority_tier"],
            "year_quarter": row["year_quarter"],
            "quarter_start_date": row["quarter_start_date"],
            "quarter_end_date": row["quarter_end_date"],
            "spec_code": COUNTRY_SPEC_CODE,
            "anchor_spec_code": ANCHOR_SPEC_CODE,
            "aggregation_scope": "sector_country_quarter_expanded",
            "available_variable_count": row["available_variable_count"],
            "available_variable_names": row["available_variable_names"],
            "construction_status": row["construction_status"],
            "inactive_component_names": join_nonempty(
                variable for values in inactive_by_subindex.values() for variable in values
            ),
        }

        any_subindex_ready = False
        for subindex_name in ["I_reg", "I_risk", "I_market"]:
            active = active_components[subindex_name]
            observed = [variable for variable in active if variable in normalized_values]
            active_count = len(active)
            observed_count = len(observed)
            missing_count = active_count - observed_count
            missing_share = (missing_count / active_count) if active_count else 1.0
            threshold_failed = active_count == 0 or missing_share >= MISSING_SHARE_THRESHOLD or observed_count == 0

            if threshold_failed:
                score = None
                weight_sum = None
                status = "not_computed"
                component_counts["blocked"][subindex_name] += 1
            else:
                weight = 1.0 / observed_count
                score = 100.0 * sum(normalized_values[variable] * weight for variable in observed)
                weight_sum = 1.0
                status = "computed"
                any_subindex_ready = True
                component_counts["computed"][subindex_name] += 1

            component_counts["active"][subindex_name] = active_count
            prefix = subindex_name.lower()
            out_row[f"{prefix}_active_component_count"] = str(active_count)
            out_row[f"{prefix}_observed_component_count"] = str(observed_count)
            out_row[f"{prefix}_missing_component_count"] = str(missing_count)
            out_row[f"{prefix}_missing_share"] = fmt(missing_share)
            out_row[f"{prefix}_component_names_active"] = join_nonempty(active)
            out_row[f"{prefix}_component_names_used"] = join_nonempty(observed)
            out_row[f"{prefix}_component_names_missing"] = join_nonempty(
                variable for variable in active if variable not in observed
            )
            out_row[f"{prefix}_component_names_inactive"] = join_nonempty(inactive_by_subindex[subindex_name])
            out_row[f"{prefix}_weight_sum"] = fmt(weight_sum)
            out_row[f"{prefix}_status"] = status
            out_row[subindex_name] = fmt(score)

        out_row["subindex_any_ready_flag"] = "yes" if any_subindex_ready else "no"
        out_rows.append(out_row)

    return out_rows, component_counts, inactive_by_subindex


def calculate_sector_quarter_panel(country_rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], Counter]:
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in country_rows:
        grouped[(row["sector_std"], row["year_quarter"])].append(row)

    out_rows: List[Dict[str, str]] = []
    computed_counter = Counter()

    for (sector_std, year_quarter), members in sorted(grouped.items()):
        primary_members = [row for row in members if row["country_priority_tier"] == "primary"]
        out_row = {
            "sector_std": sector_std,
            "year_quarter": year_quarter,
            "spec_code": BASE_SPEC_CODE,
            "anchor_spec_code": ANCHOR_SPEC_CODE,
            "country_scope": "primary_only",
            "country_count_total": str(len(members)),
            "country_count_primary_scope": str(len(primary_members)),
            "country_list_primary_scope": join_nonempty(row["country_std"] for row in primary_members),
        }

        any_ready = False
        for subindex_name in ["I_reg", "I_risk", "I_market"]:
            usable = [
                row for row in primary_members
                if safe_float(row.get(subindex_name, "")) is not None
            ]
            if usable:
                score = sum(float(row[subindex_name]) for row in usable) / len(usable)
                any_ready = True
                computed_counter[subindex_name] += 1
            else:
                score = None

            prefix = subindex_name.lower()
            out_row[subindex_name] = fmt(score)
            out_row[f"{prefix}_country_count_used"] = str(len(usable))
            out_row[f"{prefix}_country_list_used"] = join_nonempty(row["country_std"] for row in usable)

        out_row["subindex_any_ready_flag"] = "yes" if any_ready else "no"
        out_rows.append(out_row)

    return out_rows, computed_counter


def build_log(
    rows: List[Dict[str, str]],
    country_rows: List[Dict[str, str]],
    sector_rows: List[Dict[str, str]],
    variable_stats: Dict[str, Dict[str, str]],
    inactive_variables: Dict[str, Dict[str, str]],
    component_counts: Dict[str, Counter],
    inactive_by_subindex: Dict[str, List[str]],
    sector_computed_counter: Counter,
) -> str:
    active_components = subindex_components_active(variable_stats)
    country_range_counter = Counter()
    weight_issue_counter = Counter()
    for row in country_rows:
        for subindex_name in ["I_reg", "I_risk", "I_market"]:
            score = safe_float(row.get(subindex_name, ""))
            if score is not None and not (0.0 <= score <= 100.0):
                country_range_counter[subindex_name] += 1
            weight_sum = safe_float(row.get(f"{subindex_name.lower()}_weight_sum", ""))
            if score is not None and weight_sum is not None and abs(weight_sum - 1.0) > 1e-9:
                weight_issue_counter[subindex_name] += 1

    sector_range_counter = Counter()
    for row in sector_rows:
        for subindex_name in ["I_reg", "I_risk", "I_market"]:
            score = safe_float(row.get(subindex_name, ""))
            if score is not None and not (0.0 <= score <= 100.0):
                sector_range_counter[subindex_name] += 1

    lines = [
        "# Subindex Calculation Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Input: `data/processed/variable_panel_sector_quarter.csv` with `{len(rows)}` rows",
        f"- Country comparison spec: `{COUNTRY_SPEC_CODE}`",
        f"- Report base spec: `{BASE_SPEC_CODE}`",
        f"- Shared anchor spec: `{ANCHOR_SPEC_CODE}`",
        "",
        "## Spec Split",
        "- 보고서 기준 사양은 `sector-quarter` 본문 구조를 유지하기 위해 `primary country`만 사용하고, 이미 계산된 `sector-country-quarter` 하위지수를 동일가중 평균해 집계한다.",
        "- 국가 비교 확장 사양은 `sector-country-quarter` 수준에서 직접 하위지수를 계산하며, `primary`와 `secondary` 국가를 모두 유지한다.",
        "- 현재 실행 단계는 실제 수집 변수의 제약 때문에 보고서의 이론 풀셋이 아니라 `reduced empirical component set`을 사용한다.",
        "",
        "## Reduced Empirical Component Set",
        f"- `I_reg`: `{join_nonempty(active_components['I_reg'])}`",
        f"- `I_risk`: `{join_nonempty(active_components['I_risk'])}`",
        f"- `I_market`: `{join_nonempty(active_components['I_market'])}`",
        "",
        "## Inactive Theoretical Components",
        f"- `I_reg`: `{join_nonempty(inactive_by_subindex['I_reg']) or 'none'}`",
        f"- `I_risk`: `{join_nonempty(inactive_by_subindex['I_risk']) or 'none'}`",
        f"- `I_market`: `{join_nonempty(inactive_by_subindex['I_market']) or 'none'}`",
        "",
        "## Direction And Anchor Rules",
        "- 방향성 통일은 `higher = worse competitive pressure` 기준으로 고정했다. 따라서 회수율·현금흐름 회수율·창작자 몫은 `-1` 방향코드를 적용했다.",
        "- 로그변환은 보고서 순서를 보존하기 위해 지정 변수에 `signed_log1p`를 적용했다. 기준 정규화가 empirical rank이므로 변환은 순위를 크게 바꾸지 않지만, tail clipping 기준과 재현성 로그를 위해 유지한다.",
        f"- 기준 winsorization은 pooled `sector-country-quarter` 분포 기준 `{int(WINSOR_P_LOWER * 100)}`% / `{int(WINSOR_P_UPPER * 100)}`%이다.",
        "- 기준 정규화는 winsorized 값의 empirical percentile normalization이다.",
        f"- 결측 재정규화는 하위지수 active component 기준 missing share가 `{fmt(MISSING_SHARE_THRESHOLD)}` 이상이면 산출하지 않고, 그렇지 않으면 관측 항목 동일가중으로 재가중한다.",
        "",
        "## Variable Anchor Summary",
    ]

    for variable_name in sorted(set(variable_stats) | set(inactive_variables)):
        if variable_name in variable_stats:
            stats = variable_stats[variable_name]
            lines.append(
                f"- `{variable_name}`: status `{stats['status']}`, n `{stats['n_obs']}`, direction `{stats['direction_code']}`, log `{stats['log_rule']}`, winsor [`{stats['winsor_lower']}`, `{stats['winsor_upper']}`], unique post-winsor `{stats['unique_count_post_winsor']}`"
            )
        else:
            stats = inactive_variables[variable_name]
            note = f"- `{variable_name}`: status `inactive`, reason `{stats['reason']}`, n `{stats['n_obs']}`"
            if stats.get("winsor_lower") or stats.get("winsor_upper"):
                note += f", winsor [`{stats.get('winsor_lower', '')}`, `{stats.get('winsor_upper', '')}`]"
            lines.append(note)

    lines.extend(
        [
            "",
            "## Coverage Summary",
            f"- `subindex_panel_sector_country_quarter.csv`: `{len(country_rows)}` rows",
            f"- `subindex_panel_sector_quarter.csv`: `{len(sector_rows)}` rows",
            f"- country spec computed counts: `I_reg {component_counts['computed']['I_reg']}`, `I_risk {component_counts['computed']['I_risk']}`, `I_market {component_counts['computed']['I_market']}`",
            f"- report base sector-quarter computed counts: `I_reg {sector_computed_counter['I_reg']}`, `I_risk {sector_computed_counter['I_risk']}`, `I_market {sector_computed_counter['I_market']}`",
            "",
            "## Validation",
            f"- country spec out-of-range count: `{dict(country_range_counter)}`",
            f"- country spec weight-sum issue count: `{dict(weight_issue_counter)}`",
            f"- sector-quarter out-of-range count: `{dict(sector_range_counter)}`",
            "",
            "## Notes",
            "- `creator_share_ratio`와 `bundle_leverage_index`는 현재 pooled 실행 표본에서 유효 관측 수 또는 분산이 충분하지 않아 active component에서 제외됐다.",
            "- `outflow_to_capex_ratio`는 현재 단계에서 `market/infrastructure pressure`를 대표하는 실행용 보조 변수로 `I_market`에 포함했다.",
            "- 보고서의 5%/95% winsorization은 소표본 강건성 대체 사양으로 남기고, 이번 기준 산출은 보고서 본사양과 맞춰 1%/99%를 사용했다.",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    rows = read_csv(INPUT_PATH)
    normalized_by_row, variable_stats, inactive_variables = variable_pipeline(rows)
    country_rows, component_counts, inactive_by_subindex = calculate_country_panel(
        rows,
        normalized_by_row,
        variable_stats,
        inactive_variables,
    )
    sector_rows, sector_computed_counter = calculate_sector_quarter_panel(country_rows)

    country_fields = list(country_rows[0].keys()) if country_rows else []
    sector_fields = list(sector_rows[0].keys()) if sector_rows else []
    write_csv(OUT_SECTOR_COUNTRY_QUARTER_PATH, country_rows, country_fields)
    write_csv(OUT_SECTOR_QUARTER_PATH, sector_rows, sector_fields)

    log_text = build_log(
        rows,
        country_rows,
        sector_rows,
        variable_stats,
        inactive_variables,
        component_counts,
        inactive_by_subindex,
        sector_computed_counter,
    )
    LOG_PATH.write_text(log_text, encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_subindex_panels.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds sector-country-quarter and sector-quarter subindex panels using pooled anchors and reduced empirical component sets.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/subindex_panel_sector_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_subindex_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Report-base sector-quarter subindex panel aggregated from primary-country sector-country-quarter scores.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/subindex_panel_sector_country_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_subindex_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expanded sector-country-quarter subindex panel with component coverage and missing-reweight metadata.",
        },
        {
            "artifact_type": "log",
            "path": "logs/subindex_calculation_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Spec split, anchor rules, variable activity, and validation summary for subindex calculation.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 하위 지수 계산"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `data/processed/subindex_panel_sector_country_quarter.csv`와 `subindex_panel_sector_quarter.csv`를 생성",
                "- 방향성 통일, 지정 로그변환, pooled 1%/99% winsorization, empirical percentile normalization, 결측 재정규화 규칙을 고정",
                "- `logs/subindex_calculation_log.md`에 보고서 기준 사양과 국가 비교 확장 사양의 차이, inactive component, 범위 검증 결과를 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
