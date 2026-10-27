#!/usr/bin/env python3

from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from build_subindex_panels import (
    BASE_DIR,
    MISSING_SHARE_THRESHOLD,
    SUBINDEX_COMPONENTS,
    VARIABLE_DIRECTION,
    VARIABLE_LOG_RULE,
    WINSOR_P_LOWER,
    WINSOR_P_UPPER,
    fmt,
    join_nonempty,
    quantile,
    read_csv,
    safe_float,
    signed_log1p,
    subindex_components_active,
    write_csv,
)


SECTOR_VARIABLE_PATH = BASE_DIR / "data/processed/variable_panel_sector_quarter.csv"
PLATFORM_VARIABLE_PATH = BASE_DIR / "data/processed/variable_panel_platform_quarter.csv"
SUBINDEX_SECTOR_PATH = BASE_DIR / "data/processed/subindex_panel_sector_quarter.csv"
SUBINDEX_SECTOR_COUNTRY_PATH = BASE_DIR / "data/processed/subindex_panel_sector_country_quarter.csv"

OUT_SECTOR_PATH = BASE_DIR / "data/processed/cpii_panel_sector_quarter.csv"
OUT_SECTOR_COUNTRY_PATH = BASE_DIR / "data/processed/cpii_panel_sector_country_quarter.csv"
OUT_FIRM_COUNTRY_PATH = BASE_DIR / "data/processed/cpii_panel_firm_country_quarter.csv"
LOG_PATH = BASE_DIR / "logs/cpii_calculation_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 26"

ANCHOR_SPEC_CODE = "POOL_SCQ_P01_P99_EMP_RANK_V1"
SECTOR_SPEC_CODE = "CPII_SQ_BASE_EQW_V1"
SECTOR_COUNTRY_SPEC_CODE = "CPII_SCQ_EXPANDED_EQW_V1"
FIRM_COUNTRY_SPEC_CODE = "CPII_FCQ_EXPANDED_EQW_V1"
TOP_LEVEL_WEIGHT = 1.0 / 3.0


def build_anchor_profiles(
    sector_rows: List[Dict[str, str]],
) -> Tuple[Dict[str, Dict[str, object]], Dict[str, Dict[str, str]]]:
    all_variables = sorted({variable for items in SUBINDEX_COMPONENTS.values() for variable in items})
    anchor_profiles: Dict[str, Dict[str, object]] = {}
    inactive_variables: Dict[str, Dict[str, str]] = {}

    for variable_name in all_variables:
        direction = VARIABLE_DIRECTION[variable_name]
        log_rule = VARIABLE_LOG_RULE[variable_name]
        transformed_values: List[float] = []

        for row in sector_rows:
            raw_value = safe_float(row.get(variable_name, ""))
            if raw_value is None:
                continue
            directed = raw_value * direction
            transformed = signed_log1p(directed) if log_rule == "signed_log1p" else directed
            transformed_values.append(transformed)

        if len(transformed_values) < 2:
            inactive_variables[variable_name] = {
                "reason": "n_lt_2",
                "n_obs": str(len(transformed_values)),
            }
            continue

        lower = quantile(transformed_values, WINSOR_P_LOWER)
        upper = quantile(transformed_values, WINSOR_P_UPPER)
        winsorized_values = sorted(min(max(value, lower), upper) for value in transformed_values)
        unique_count = len(set(winsorized_values))
        if unique_count < 2:
            inactive_variables[variable_name] = {
                "reason": "winsorized_zero_variation",
                "n_obs": str(len(transformed_values)),
                "winsor_lower": fmt(lower),
                "winsor_upper": fmt(upper),
            }
            continue

        anchor_profiles[variable_name] = {
            "direction_code": direction,
            "log_rule": log_rule,
            "winsor_lower": lower,
            "winsor_upper": upper,
            "reference_winsorized_values": winsorized_values,
            "reference_n": len(winsorized_values),
        }

    return anchor_profiles, inactive_variables


def normalize_with_anchor(raw_value: float, profile: Dict[str, object]) -> float:
    directed = raw_value * int(profile["direction_code"])
    log_rule = str(profile["log_rule"])
    transformed = signed_log1p(directed) if log_rule == "signed_log1p" else directed
    winsor_lower = float(profile["winsor_lower"])
    winsor_upper = float(profile["winsor_upper"])
    winsorized = min(max(transformed, winsor_lower), winsor_upper)
    reference = list(profile["reference_winsorized_values"])
    n = int(profile["reference_n"])

    lo = bisect.bisect_left(reference, winsorized)
    hi = bisect.bisect_right(reference, winsorized)
    avg_rank = ((lo + 1) + hi) / 2.0
    return (avg_rank - 1.0) / (n - 1.0)


def compute_subindex_dict(
    normalized_values: Dict[str, float],
    active_components: Dict[str, List[str]],
    inactive_variables: Dict[str, Dict[str, str]],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    inactive_by_subindex = {
        subindex_name: [variable for variable in SUBINDEX_COMPONENTS[subindex_name] if variable in inactive_variables]
        for subindex_name in SUBINDEX_COMPONENTS
    }

    for subindex_name in ["I_reg", "I_risk", "I_market"]:
        active = active_components[subindex_name]
        observed = [variable for variable in active if variable in normalized_values]
        active_count = len(active)
        observed_count = len(observed)
        missing_count = active_count - observed_count
        missing_share = (missing_count / active_count) if active_count else 1.0
        threshold_failed = active_count == 0 or observed_count == 0 or missing_share >= MISSING_SHARE_THRESHOLD

        if threshold_failed:
            score = None
            weight_sum = None
            status = "not_computed"
        else:
            score = 100.0 * sum(normalized_values[variable] for variable in observed) / observed_count
            weight_sum = 1.0
            status = "computed"

        prefix = subindex_name.lower()
        out[subindex_name] = fmt(score)
        out[f"{prefix}_active_component_count"] = str(active_count)
        out[f"{prefix}_observed_component_count"] = str(observed_count)
        out[f"{prefix}_missing_component_count"] = str(missing_count)
        out[f"{prefix}_missing_share"] = fmt(missing_share)
        out[f"{prefix}_component_names_active"] = join_nonempty(active)
        out[f"{prefix}_component_names_used"] = join_nonempty(observed)
        out[f"{prefix}_component_names_missing"] = join_nonempty(
            variable for variable in active if variable not in observed
        )
        out[f"{prefix}_component_names_inactive"] = join_nonempty(inactive_by_subindex[subindex_name])
        out[f"{prefix}_weight_sum"] = fmt(weight_sum)
        out[f"{prefix}_status"] = status

    return out


def compute_cpii_fields(i_reg: Optional[float], i_risk: Optional[float], i_market: Optional[float]) -> Dict[str, str]:
    observed = {
        "I_reg": i_reg,
        "I_risk": i_risk,
        "I_market": i_market,
    }
    used = [name for name, value in observed.items() if value is not None]
    missing = [name for name, value in observed.items() if value is None]
    missing_share = len(missing) / 3.0

    if len(used) >= 2 and missing_share < MISSING_SHARE_THRESHOLD:
        cpii = sum(observed[name] for name in used if observed[name] is not None) / len(used)
        raw_score = cpii / 100.0
        weight_sum = 1.0
        status = "computed"
    else:
        cpii = None
        raw_score = None
        weight_sum = None
        status = "not_computed"

    return {
        "top_level_weight_scheme": "equal_weight_reweighted_over_observed",
        "top_level_base_weight_reg": fmt(TOP_LEVEL_WEIGHT),
        "top_level_base_weight_risk": fmt(TOP_LEVEL_WEIGHT),
        "top_level_base_weight_market": fmt(TOP_LEVEL_WEIGHT),
        "cpii_observed_subindex_count": str(len(used)),
        "cpii_missing_subindex_count": str(len(missing)),
        "cpii_missing_share": fmt(missing_share),
        "cpii_subindex_names_used": join_nonempty(used),
        "cpii_subindex_names_missing": join_nonempty(missing),
        "cpii_weight_sum": fmt(weight_sum),
        "cpii_raw_score": fmt(raw_score),
        "cpii_status": status,
        "CPII": fmt(cpii),
    }


def add_cpii_to_subindex_rows(
    rows: List[Dict[str, str]],
    spec_code: str,
    row_type: str,
) -> List[Dict[str, str]]:
    out_rows: List[Dict[str, str]] = []
    for row in rows:
        i_reg = safe_float(row.get("I_reg", ""))
        i_risk = safe_float(row.get("I_risk", ""))
        i_market = safe_float(row.get("I_market", ""))
        cpii_fields = compute_cpii_fields(i_reg, i_risk, i_market)

        out_row = dict(row)
        out_row["spec_code"] = spec_code
        out_row["anchor_spec_code"] = ANCHOR_SPEC_CODE
        out_row["row_type"] = row_type
        out_row["country_std"] = row.get("country_std", "")
        out_row["firm_std"] = row.get("firm_std", "")
        if "sector_std" not in out_row:
            out_row["sector_std"] = ""
        if "year_quarter" not in out_row:
            out_row["year_quarter"] = ""
        out_row.update(cpii_fields)
        out_rows.append(out_row)
    return out_rows


def build_firm_country_panel(
    platform_rows: List[Dict[str, str]],
    anchor_profiles: Dict[str, Dict[str, object]],
    active_components: Dict[str, List[str]],
    inactive_variables: Dict[str, Dict[str, str]],
) -> List[Dict[str, str]]:
    grouped_rows: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = defaultdict(list)
    variable_names = sorted({variable for items in SUBINDEX_COMPONENTS.values() for variable in items})
    for row in platform_rows:
        key = (row["firm_std"], row["country_std"], row["sector_std"], row["year_quarter"])
        grouped_rows[key].append(row)

    out_rows: List[Dict[str, str]] = []
    for (firm_std, country_std, sector_std, year_quarter), members in sorted(grouped_rows.items()):
        aggregated = {
            variable: (
                sum(safe_float(member.get(variable, "")) for member in members if safe_float(member.get(variable, "")) is not None)
                / sum(1 for member in members if safe_float(member.get(variable, "")) is not None)
                if any(safe_float(member.get(variable, "")) is not None for member in members)
                else None
            )
            for variable in variable_names
        }

        normalized_values = {
            variable: normalize_with_anchor(value, anchor_profiles[variable])
            for variable, value in aggregated.items()
            if value is not None and variable in anchor_profiles
        }
        subindex_fields = compute_subindex_dict(normalized_values, active_components, inactive_variables)
        cpii_fields = compute_cpii_fields(
            safe_float(subindex_fields.get("I_reg", "")),
            safe_float(subindex_fields.get("I_risk", "")),
            safe_float(subindex_fields.get("I_market", "")),
        )

        available_variable_names = [variable for variable, value in aggregated.items() if value is not None]
        out_row = {
            "firm_std": firm_std,
            "country_std": country_std,
            "sector_std": sector_std,
            "year_quarter": year_quarter,
            "home_country": members[0].get("home_country", ""),
            "country_priority_tier": members[0].get("country_priority_tier", ""),
            "quarter_start_date": members[0].get("quarter_start_date", ""),
            "quarter_end_date": members[0].get("quarter_end_date", ""),
            "service_row_count": str(len(members)),
            "service_list": join_nonempty(member.get("service_std", "") for member in members),
            "spec_code": FIRM_COUNTRY_SPEC_CODE,
            "anchor_spec_code": ANCHOR_SPEC_CODE,
            "row_type": "firm_country_quarter_expanded",
            "available_variable_count": str(len(available_variable_names)),
            "available_variable_names": join_nonempty(available_variable_names),
            "inactive_component_names": join_nonempty(inactive_variables.keys()),
        }
        for variable in variable_names:
            out_row[variable] = fmt(aggregated[variable])
        out_row.update(subindex_fields)
        out_row.update(cpii_fields)
        out_rows.append(out_row)

    return out_rows


def validation_counter(rows: List[Dict[str, str]], fields: Iterable[str]) -> Counter:
    counter = Counter()
    for row in rows:
        for field in fields:
            value = safe_float(row.get(field, ""))
            if value is not None and not (0.0 <= value <= 100.0):
                counter[field] += 1
    return counter


def weight_issue_counter(rows: List[Dict[str, str]]) -> Counter:
    counter = Counter()
    for row in rows:
        for field in ["i_reg_weight_sum", "i_risk_weight_sum", "i_market_weight_sum", "cpii_weight_sum"]:
            value = safe_float(row.get(field, ""))
            status_field = "cpii_status" if field == "cpii_weight_sum" else field.replace("_weight_sum", "_status")
            if value is not None and row.get(status_field, "") == "computed" and abs(value - 1.0) > 1e-9:
                counter[field] += 1
    return counter


def entity_obs_counter(rows: List[Dict[str, str]], entity_field: str) -> Counter:
    counter = Counter()
    for row in rows:
        if safe_float(row.get("CPII", "")) is not None and row.get(entity_field, ""):
            counter[row[entity_field]] += 1
    return counter


def build_log(
    sector_rows: List[Dict[str, str]],
    sector_country_rows: List[Dict[str, str]],
    firm_country_rows: List[Dict[str, str]],
    active_components: Dict[str, List[str]],
    inactive_variables: Dict[str, Dict[str, str]],
) -> str:
    sector_range = validation_counter(sector_rows, ["I_reg", "I_risk", "I_market", "CPII"])
    sector_country_range = validation_counter(sector_country_rows, ["I_reg", "I_risk", "I_market", "CPII"])
    firm_country_range = validation_counter(firm_country_rows, ["I_reg", "I_risk", "I_market", "CPII"])

    sector_weight = weight_issue_counter(sector_rows)
    sector_country_weight = weight_issue_counter(sector_country_rows)
    firm_country_weight = weight_issue_counter(firm_country_rows)

    country_obs = entity_obs_counter(sector_country_rows, "country_std")
    firm_obs = entity_obs_counter(firm_country_rows, "firm_std")
    all_countries = sorted({row["country_std"] for row in sector_country_rows if row.get("country_std", "")})
    all_firms = sorted({row["firm_std"] for row in firm_country_rows if row.get("firm_std", "")})
    country_obs_full = {country: country_obs.get(country, 0) for country in all_countries}
    firm_obs_full = {firm: firm_obs.get(firm, 0) for firm in all_firms}

    comparable_country_min = min(country_obs.values()) if country_obs else 0
    comparable_firm_min = min(firm_obs.values()) if firm_obs else 0
    country_below_two = sorted(country for country, count in country_obs.items() if count < 2)
    firm_below_two = sorted(firm for firm, count in firm_obs.items() if count < 2)
    country_zero = sorted(country for country, count in country_obs_full.items() if count == 0)
    firm_zero = sorted(firm for firm, count in firm_obs_full.items() if count == 0)

    sector_computed = sum(1 for row in sector_rows if safe_float(row.get("CPII", "")) is not None)
    sector_country_computed = sum(1 for row in sector_country_rows if safe_float(row.get("CPII", "")) is not None)
    firm_country_computed = sum(1 for row in firm_country_rows if safe_float(row.get("CPII", "")) is not None)

    lines = [
        "# CPII Calculation Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Sector-quarter CPII spec: `{SECTOR_SPEC_CODE}`",
        f"- Sector-country-quarter CPII spec: `{SECTOR_COUNTRY_SPEC_CODE}`",
        f"- Firm-country-quarter CPII spec: `{FIRM_COUNTRY_SPEC_CODE}`",
        f"- Shared anchor spec reused from subindex stage: `{ANCHOR_SPEC_CODE}`",
        "",
        "## Aggregation Rule",
        "- 최종 CPII는 `I_reg`, `I_risk`, `I_market`의 기준 동일가중 `1/3`을 사용한다.",
        f"- 상위 단계에서도 결측 재정규화를 적용하여 missing share가 `{fmt(MISSING_SHARE_THRESHOLD)}` 미만이면 관측된 하위지수만으로 재가중 평균한다.",
        "- 따라서 하위지수 3개 중 2개 이상이 관측되면 CPII를 계산하고, 2개 이상이 결측이면 CPII를 산출하지 않는다.",
        "",
        "## Active Subindex Components",
        f"- `I_reg`: `{join_nonempty(active_components['I_reg'])}`",
        f"- `I_risk`: `{join_nonempty(active_components['I_risk'])}`",
        f"- `I_market`: `{join_nonempty(active_components['I_market'])}`",
        f"- inactive variables carried from subindex stage: `{join_nonempty(inactive_variables.keys())}`",
        "",
        "## Coverage Summary",
        f"- `cpii_panel_sector_quarter.csv`: `{len(sector_rows)}` rows, computed CPII `{sector_computed}`",
        f"- `cpii_panel_sector_country_quarter.csv`: `{len(sector_country_rows)}` rows, computed CPII `{sector_country_computed}`",
        f"- `cpii_panel_firm_country_quarter.csv`: `{len(firm_country_rows)}` rows, computed CPII `{firm_country_computed}`",
        "",
        "## Spec Difference",
        "- `sector-quarter` 본문 사양은 `primary country`만 사용한 하위지수 집계를 다시 동일가중으로 합성한 결과다.",
        "- `sector-country-quarter` 확장 사양은 모든 retained country를 유지하며 국가별 비교표의 입력으로 사용된다.",
        "- `firm-country-quarter` 확장 사양은 platform-quarter 변수 테이블에 sector-quarter anchor를 재사용해 firm-level 하위지수와 CPII를 계산한 결과다.",
        "",
        "## Validation",
        f"- sector-quarter out-of-range: `{dict(sector_range)}`",
        f"- sector-country-quarter out-of-range: `{dict(sector_country_range)}`",
        f"- firm-country-quarter out-of-range: `{dict(firm_country_range)}`",
        f"- sector-quarter weight-sum issues: `{dict(sector_weight)}`",
        f"- sector-country-quarter weight-sum issues: `{dict(sector_country_weight)}`",
        f"- firm-country-quarter weight-sum issues: `{dict(firm_country_weight)}`",
        "",
        "## Minimum Observation Check",
        f"- country computed CPII counts: `{dict(country_obs_full)}`",
        f"- firm computed CPII counts: `{dict(firm_obs_full)}`",
        f"- minimum computed observations by country: `{comparable_country_min}`",
        f"- minimum computed observations by firm: `{comparable_firm_min}`",
        f"- countries below 2 computed observations: `{join_nonempty(country_below_two) or 'none'}`",
        f"- firms below 2 computed observations: `{join_nonempty(firm_below_two) or 'none'}`",
        f"- countries with 0 computed observations: `{join_nonempty(country_zero) or 'none'}`",
        f"- firms with 0 computed observations: `{join_nonempty(firm_zero) or 'none'}`",
        "",
        "## Notes",
        "- `sector-quarter`와 `sector-country-quarter` 패널의 `country_std`, `firm_std`는 비교 단위에 따라 공란이 허용된다.",
        "- firm panel은 현재 자료 구조상 대부분 `firm-country-quarter`와 `firm-service-country-quarter`가 1:1이라 별도 서비스 집계 왜곡이 크지 않다.",
        "- 이후 기업별 비교와 국가별 비교 표는 본 단계의 CPII 패널을 직접 입력으로 사용한다.",
    ]

    return "\n".join(lines) + "\n"


def main() -> None:
    sector_variable_rows = read_csv(SECTOR_VARIABLE_PATH)
    platform_variable_rows = read_csv(PLATFORM_VARIABLE_PATH)
    subindex_sector_rows = read_csv(SUBINDEX_SECTOR_PATH)
    subindex_sector_country_rows = read_csv(SUBINDEX_SECTOR_COUNTRY_PATH)

    anchor_profiles, inactive_variables = build_anchor_profiles(sector_variable_rows)
    active_components = subindex_components_active(
        {
            variable: {"status": "active"}
            for variable in anchor_profiles
        }
    )

    sector_rows = add_cpii_to_subindex_rows(
        subindex_sector_rows,
        SECTOR_SPEC_CODE,
        "sector_quarter_base",
    )
    for row in sector_rows:
        row["country_std"] = ""
        row["firm_std"] = ""

    sector_country_rows = add_cpii_to_subindex_rows(
        subindex_sector_country_rows,
        SECTOR_COUNTRY_SPEC_CODE,
        "sector_country_quarter_expanded",
    )
    for row in sector_country_rows:
        row["firm_std"] = ""

    firm_country_rows = build_firm_country_panel(
        platform_variable_rows,
        anchor_profiles,
        active_components,
        inactive_variables,
    )

    sector_fields = list(sector_rows[0].keys()) if sector_rows else []
    sector_country_fields = list(sector_country_rows[0].keys()) if sector_country_rows else []
    firm_country_fields = list(firm_country_rows[0].keys()) if firm_country_rows else []

    write_csv(OUT_SECTOR_PATH, sector_rows, sector_fields)
    write_csv(OUT_SECTOR_COUNTRY_PATH, sector_country_rows, sector_country_fields)
    write_csv(OUT_FIRM_COUNTRY_PATH, firm_country_rows, firm_country_fields)

    log_text = build_log(
        sector_rows,
        sector_country_rows,
        firm_country_rows,
        active_components,
        inactive_variables,
    )
    LOG_PATH.write_text(log_text, encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_cpii_panels.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds final CPII panels for sector-quarter, sector-country-quarter, and firm-country-quarter using equal-weight top-level aggregation.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/cpii_panel_sector_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_cpii_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Base report CPII panel at sector-quarter level.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/cpii_panel_sector_country_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_cpii_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expanded CPII panel at sector-country-quarter level for country comparisons.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/cpii_panel_firm_country_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_cpii_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expanded CPII panel at firm-country-quarter level using the sector anchor specification.",
        },
        {
            "artifact_type": "log",
            "path": "logs/cpii_calculation_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Final CPII aggregation rules, validation results, and minimum observation checks by country and firm.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 최종 CPII 계산"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `data/processed/cpii_panel_sector_quarter.csv`, `cpii_panel_sector_country_quarter.csv`, `cpii_panel_firm_country_quarter.csv`를 생성",
                "- 상위 가중치는 기준 동일가중 `1/3`으로 고정하고, 하위지수 결측 시 관측된 하위지수만으로 재정규화해 `CPII`를 계산",
                "- `logs/cpii_calculation_log.md`에 범위 검증, 가중치 합 검증, 국가별/기업별 최소 관측 수 점검, 기준 사양과 확장 사양 차이를 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
