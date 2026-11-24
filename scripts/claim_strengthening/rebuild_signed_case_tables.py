#!/usr/bin/env python3
"""Propagate recomputed narrow risk evidence into signed_rebuild case tables.

This script preserves all archived codings not linked to changed narrow-risk inputs
(`s_reg_domestic_panel.csv`, `s_market_transfer_panel.csv`, `s_reach_gap_panel.csv`,
`s_creator_incidence_panel.csv`, and unlinked rows of `s_risk_recovery_panel.csv`),
recomputes linked `s_risk_recovery` rows directly from `i_risk_narrow_panel.csv`,
and deterministically rebuilds the derived signed case, audit, robustness, and
summary tables.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]

I_RISK_NARROW_PATH = ROOT / "data/processed/claim_strengthening/i_risk_narrow_panel.csv"
SIGNED_DATA_DIR = ROOT / "data/processed/claim_strengthening/signed_rebuild"
SIGNED_TABLE_DIR = ROOT / "outputs/tables/claim_strengthening/signed_rebuild"

# Exact evidence-quality axis weights verified against archived v1.0.0 WEQ02.
QUALITY_AXIS_WEIGHTS: Dict[str, float] = {
    "reg": 0.80,
    "risk": 1.00,
    "market": 0.45,
    "reach": 0.55,
    "creator": 0.40,
}

# Mapping from signed-case firm_std to firm_std in i_risk_narrow_panel.csv
SIGNED_TO_NARROW_FIRM: Dict[str, str] = {
    "dreamus_flo": "dreamus",
    "kakao_ent_melon": "kakao_ent",
    "sk_telecom": "sk_telecom",
    "kt": "kt",
    "lg_uplus": "lg_uplus",
}

# Foreign peer country codes used in LOC01..LOC03 stress tests
FOREIGN_PEER_COUNTRY: Dict[str, str] = {
    "spotify": "se",
    "youtube_music": "us",
    "youtube_premium_lite": "us",
    "apple_music": "us",
    "webtoon_us": "us",
    "piccoma": "jp",
    "netflix": "us",
}

# Direct-row classification matching archived v1.0.0 BASE01 / PER01 / PER02
# (rows with direct matched evidence across balanced periods vs bounded latest-period rows).
BALANCED_DIRECT_KEYS = {
    ("mus_streaming_paid_core", "kakao_ent_melon", "spotify"),
    ("mus_streaming_paid_core", "dreamus_flo", "spotify"),
    ("infra_traffic_ott", "sk_telecom", "netflix"),
    ("infra_traffic_ott", "kt", "netflix"),
    ("infra_traffic_ott", "lg_uplus", "netflix"),
}

REQUIRED_SECTORS = ("music", "webtoon_story", "digital_infra")
AXIS_ORDER = ("reg", "risk", "market", "reach", "creator")


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_opt_float(value: str) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def fmt6(value: Optional[float]) -> str:
    if value is None:
        return ""
    if abs(value) < 5e-13:
        value = 0.0
    return f"{value:.6f}"


def fmt2(value: float) -> str:
    return f"{value:.2f}"


def compute_narrow_risk_firm_means(i_risk_path: Path) -> Dict[Tuple[str, str], Dict[str, object]]:
    """Load computed i_risk_narrow rows by (peer_group_id, firm_std)."""
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in read_csv(i_risk_path):
        val = parse_opt_float(row.get("i_risk_narrow", ""))
        status = row.get("i_risk_narrow_status", "")
        if val is None or status == "no_direct_risk_coverage":
            continue
        key = (row["peer_group_id"], row["firm_std"])
        grouped.setdefault(key, []).append(row)

    summary: Dict[Tuple[str, str], Dict[str, object]] = {}
    for key, members in grouped.items():
        scores = [float(r["i_risk_narrow"]) for r in members]
        summary[key] = {
            "mean_score": statistics.mean(scores),
            "n_rows": len(scores),
        }
    return summary


def is_direct_cell(sector_std: str, axis: str) -> bool:
    if axis in {"reg", "risk"}:
        return True
    if axis == "reach" and sector_std == "digital_infra":
        return True
    return False


def format_axis_note_prefix(axes: Dict[str, float]) -> str:
    parts = [f"{axis}={fmt6(axes[axis])}" for axis in AXIS_ORDER if axis in axes]
    return "; ".join(parts)


def extract_headline_suffix(note: str) -> str:
    marker = "headline blocked:"
    idx = note.find(marker)
    if idx == -1:
        return ""
    return note[idx:]


def evaluate_robustness_scenario(
    scenario_template: Dict[str, str],
    case_records: List[Dict[str, object]],
) -> Dict[str, str]:
    row_mode = scenario_template["row_mode"]
    weight_mode = scenario_template["weight_mode"]
    drop_axis = scenario_template["drop_axis"].strip()
    drop_sector = scenario_template["drop_sector"].strip()
    drop_country = scenario_template["drop_foreign_country"].strip()
    period_filter = scenario_template["period_bucket_filter"].strip()

    filtered = []
    for rec in case_records:
        if drop_sector and rec["sector_std"] == drop_sector:
            continue
        if drop_country and rec["foreign_country"] == drop_country:
            continue
        if period_filter == "latest_period" and rec["is_direct_row"]:
            continue
        if period_filter == "balanced_period" and not rec["is_direct_row"]:
            continue

        axes: Dict[str, float] = dict(rec["axes"])  # type: ignore[arg-type]
        if drop_axis and drop_axis in axes:
            del axes[drop_axis]
        if row_mode == "direct_only":
            axes = {
                k: v for k, v in axes.items() if is_direct_cell(str(rec["sector_std"]), k)
            }
        if not axes:
            continue

        if weight_mode == "quality":
            num = sum(QUALITY_AXIS_WEIGHTS[k] * v for k, v in axes.items())
            den = sum(QUALITY_AXIS_WEIGHTS[k] for k in axes)
            score = num / den
        else:
            score = statistics.mean(axes.values())

        direct_cells = sum(1 for k in axes if is_direct_cell(str(rec["sector_std"]), k))
        bound_cells = len(axes) - direct_cells
        has_pos = any(v > 0 for v in axes.values())
        has_neg = any(v < 0 for v in axes.values())
        filtered.append(
            {
                **rec,
                "scenario_axes": axes,
                "scenario_score": score,
                "direct_cells": direct_cells,
                "bound_cells": bound_cells,
                "is_mixed_sign": has_pos and has_neg,
            }
        )

    sector_means: Dict[str, Optional[float]] = {}
    for sector in REQUIRED_SECTORS:
        vals = [float(r["scenario_score"]) for r in filtered if r["sector_std"] == sector]
        sector_means[sector] = statistics.mean(vals) if vals else None

    overall_mean = statistics.mean(float(r["scenario_score"]) for r in filtered) if filtered else None
    missing_sectors = [s for s in REQUIRED_SECTORS if sector_means[s] is None]
    positive_sectors = [
        s for s in REQUIRED_SECTORS if sector_means[s] is not None and float(sector_means[s]) > 0
    ]

    usable_direct_rows = sum(1 for r in filtered if r["is_direct_row"])
    bounded_support_rows = len(filtered) - usable_direct_rows
    direct_axis_cells = sum(int(r["direct_cells"]) for r in filtered)
    bound_axis_cells = sum(int(r["bound_cells"]) for r in filtered)
    mixed_sign_rows = sum(1 for r in filtered if r["is_mixed_sign"])
    headline_ready_rows = sum(1 for r in filtered if r["headline_eligible_flag"] == "yes")

    present_sectors = [(s, float(sector_means[s])) for s in REQUIRED_SECTORS if sector_means[s] is not None]
    weakest_sector, weakest_mean = min(present_sectors, key=lambda item: item[1])

    if missing_sectors:
        missing_str = "|".join(missing_sectors)
        tc01_status = "fail"
        tc01_reason = f"required sector missing: {missing_str}"
        tc04_status = "fail"
        tc04_reason = f"required sector missing: {missing_str}"
    elif len(positive_sectors) < len(REQUIRED_SECTORS):
        tc01_status = "fail"
        tc01_reason = "not all required sectors positive"
        tc04_status = "fail"
        tc04_reason = "not all required sectors positive"
    else:
        if usable_direct_rows < 6:
            tc01_status = "fail"
            tc01_reason = f"direct evidence rows below gate: {usable_direct_rows} < 6"
        else:
            tc01_status = "pass"
            tc01_reason = "all required sectors positive with full direct-row support"

        if usable_direct_rows < 5:
            tc04_status = "fail"
            tc04_reason = f"direct evidence rows below gate: {usable_direct_rows} < 5"
        else:
            tc04_status = "pass"
            tc04_reason = "broad positive direction survives with enough direct row support"

    out = dict(scenario_template)
    out.update(
        {
            "row_count": str(len(filtered)),
            "overall_score_mean": fmt6(overall_mean),
            "music_score_mean": fmt6(sector_means["music"]),
            "webtoon_story_score_mean": fmt6(sector_means["webtoon_story"]),
            "digital_infra_score_mean": fmt6(sector_means["digital_infra"]),
            "positive_required_sector_count": str(len(positive_sectors)),
            "missing_required_sectors": "|".join(missing_sectors),
            "usable_direct_row_count": str(usable_direct_rows),
            "bounded_support_row_count": str(bounded_support_rows),
            "direct_axis_cell_count": str(direct_axis_cells),
            "bound_axis_cell_count": str(bound_axis_cells),
            "mixed_sign_row_count": str(mixed_sign_rows),
            "headline_ready_row_count": str(headline_ready_rows),
            "weakest_sector": weakest_sector,
            "weakest_sector_mean": fmt6(weakest_mean),
            "tc01_strong_status": tc01_status,
            "tc01_failure_reason": tc01_reason,
            "tc04_base_status": tc04_status,
            "tc04_failure_reason": tc04_reason,
        }
    )
    return out


def rebuild_all(root: Path = ROOT) -> Dict[str, object]:
    i_risk_path = root / "data/processed/claim_strengthening/i_risk_narrow_panel.csv"
    signed_data_dir = root / "data/processed/claim_strengthening/signed_rebuild"
    signed_table_dir = root / "outputs/tables/claim_strengthening/signed_rebuild"

    narrow_means = compute_narrow_risk_firm_means(i_risk_path)

    # 1. Update s_risk_recovery_panel.csv from recomputed i_risk_narrow_panel.csv
    risk_path = signed_data_dir / "s_risk_recovery_panel.csv"
    risk_rows = read_csv(risk_path)
    risk_fields = list(risk_rows[0].keys())
    risk_changes: List[Dict[str, object]] = []

    for row in risk_rows:
        old_val = parse_opt_float(row.get("s_risk_recovery", ""))
        if old_val is None:
            continue
        peer_group = row["peer_group_id"]
        narrow_kr_firm = SIGNED_TO_NARROW_FIRM.get(row["firm_std"], row["firm_std"])
        narrow_foreign_firm = row["foreign_peer_std"]
        kr_info = narrow_means.get((peer_group, narrow_kr_firm))
        for_info = narrow_means.get((peer_group, narrow_foreign_firm))
        if kr_info is None or for_info is None:
            continue
        kr_score = float(kr_info["mean_score"])
        for_score = float(for_info["mean_score"])
        new_val = (kr_score - for_score) / 100.0
        row["s_risk_recovery"] = fmt6(new_val)
        if not math.isclose(old_val, new_val, abs_tol=1e-6):
            risk_changes.append(
                {
                    "peer_group_id": peer_group,
                    "firm_std": row["firm_std"],
                    "foreign_peer_std": narrow_foreign_firm,
                    "old_s_risk_recovery": old_val,
                    "new_s_risk_recovery": new_val,
                    "kr_i_risk_narrow": kr_score,
                    "foreign_i_risk_narrow": for_score,
                }
            )
            if row["firm_std"] == "dreamus_flo" and narrow_foreign_firm == "spotify":
                if abs(new_val) < 1e-9:
                    row["construction_note"] = (
                        f"Computed from the Korean-market direct-risk chain as "
                        f"`(Dreamus i_risk_narrow {kr_score:.6f} - Spotify i_risk_narrow {for_score:.6f}) / 100`. "
                        f"After the v1.0.1 FY2025 Spotify Notes 11-12 period correction, the row is neutral (0.000000) "
                        f"because Dreamus and Spotify offset across the two surviving matched components "
                        f"(`ip_assetization` and `recovery_horizon`)."
                    )
                else:
                    row["construction_note"] = (
                        f"Computed from the Korean-market direct-risk chain as "
                        f"`(Dreamus i_risk_narrow {kr_score:.6f} - Spotify i_risk_narrow {for_score:.6f}) / 100`."
                    )

    write_csv(risk_path, risk_rows, risk_fields)

    # 2. Load all five signed axis panels keyed by (peer_group_id, firm_std, foreign_peer_std)
    def axis_map(filename: str, value_col: str) -> Dict[Tuple[str, str, str], Optional[float]]:
        out: Dict[Tuple[str, str, str], Optional[float]] = {}
        for row in read_csv(signed_data_dir / filename):
            key = (row["peer_group_id"], row["firm_std"], row["foreign_peer_std"])
            out[key] = parse_opt_float(row.get(value_col, ""))
        return out

    reg_map = axis_map("s_reg_domestic_panel.csv", "s_reg_domestic")
    risk_map = axis_map("s_risk_recovery_panel.csv", "s_risk_recovery")
    market_map = axis_map("s_market_transfer_panel.csv", "s_market_transfer")
    reach_map = axis_map("s_reach_gap_panel.csv", "s_reach_gap")
    creator_map = axis_map("s_creator_incidence_panel.csv", "s_creator_incidence")

    # 3. Rebuild signed_reverse_discrimination_core.csv & signed_reverse_discrimination_extended.csv
    core_path = signed_data_dir / "signed_reverse_discrimination_core.csv"
    ext_path = signed_data_dir / "signed_reverse_discrimination_extended.csv"
    core_rows = read_csv(core_path)
    core_fields = list(core_rows[0].keys())

    case_records: List[Dict[str, object]] = []
    updated_by_key: Dict[Tuple[str, str, str], Dict[str, str]] = {}

    for row in core_rows:
        key = (row["peer_group_id"], row["firm_std"], row["foreign_peer_std"])
        axes: Dict[str, float] = {}
        # Notice webtoon reg=0.00 with coverage_status=no_direct_signal_same_service_thin
        # is excluded from observed core/extended axes in v1.0.0; preserve exact axis inclusion rule.
        reg_val = reg_map.get(key)
        if reg_val is not None and not (row["sector_std"] == "webtoon_story" and abs(reg_val) < 1e-12):
            axes["reg"] = reg_val
        risk_val = risk_map.get(key)
        if risk_val is not None:
            axes["risk"] = risk_val
        market_val = market_map.get(key)
        if market_val is not None:
            axes["market"] = market_val
        reach_val = reach_map.get(key)
        if reach_val is not None:
            axes["reach"] = reach_val
        creator_val = creator_map.get(key)
        if creator_val is not None:
            axes["creator"] = creator_val

        core_vals = [axes[k] for k in ("reg", "risk", "market") if k in axes]
        ext_vals = [axes[k] for k in AXIS_ORDER if k in axes]
        core_score = statistics.mean(core_vals)
        ext_score = statistics.mean(ext_vals)

        row["core_signed_score"] = fmt6(core_score)
        row["extended_signed_score"] = fmt6(ext_score)
        row["observed_core_axis_count"] = str(len(core_vals))
        row["observed_extended_axis_count"] = str(len(ext_vals))
        suffix = extract_headline_suffix(row["construction_note"])
        prefix = format_axis_note_prefix(axes)
        if suffix:
            row["construction_note"] = f"{prefix}; {suffix}"
        else:
            row["construction_note"] = prefix

        updated_by_key[key] = dict(row)
        case_records.append(
            {
                "key": key,
                "peer_group_id": row["peer_group_id"],
                "firm_std": row["firm_std"],
                "foreign_peer_std": row["foreign_peer_std"],
                "sector_std": row["sector_std"],
                "foreign_country": FOREIGN_PEER_COUNTRY[row["foreign_peer_std"]],
                "is_direct_row": key in BALANCED_DIRECT_KEYS,
                "headline_eligible_flag": row["headline_eligible_flag"],
                "core_signed_score": core_score,
                "extended_signed_score": ext_score,
                "observed_core_axis_count": len(core_vals),
                "observed_extended_axis_count": len(ext_vals),
                "axes": axes,
            }
        )

    write_csv(core_path, core_rows, core_fields)
    write_csv(ext_path, core_rows, core_fields)

    # 4. Update signed_headline_eligibility_audit.csv
    audit_path = signed_data_dir / "signed_headline_eligibility_audit.csv"
    audit_rows = read_csv(audit_path)
    audit_fields = list(audit_rows[0].keys())
    for row in audit_rows:
        key = (row["peer_group_id"], row["firm_std"], row["foreign_peer_std"])
        src = updated_by_key[key]
        row["core_signed_score"] = src["core_signed_score"]
        row["extended_signed_score"] = src["extended_signed_score"]
        row["observed_core_axis_count"] = src["observed_core_axis_count"]
        row["observed_extended_axis_count"] = src["observed_extended_axis_count"]
    write_csv(audit_path, audit_rows, audit_fields)

    # 5. Update T_signed_korea_market_case_studies.csv
    cases_path = signed_table_dir / "T_signed_korea_market_case_studies.csv"
    case_table_rows = read_csv(cases_path)
    case_table_fields = list(case_table_rows[0].keys())
    for row in case_table_rows:
        key = (row["peer_group_id"], row["firm_std"], row["foreign_peer_std"])
        src = updated_by_key[key]
        row["core_signed_score"] = src["core_signed_score"]
        row["extended_signed_score"] = src["extended_signed_score"]
        row["observed_core_axis_count"] = src["observed_core_axis_count"]
        row["observed_extended_axis_count"] = src["observed_extended_axis_count"]
        row["construction_note"] = src["construction_note"]
    write_csv(cases_path, case_table_rows, case_table_fields)

    # 6. Update T_signed_reverse_discrimination_summary.csv
    summary_path = signed_table_dir / "T_signed_reverse_discrimination_summary.csv"
    summary_rows = read_csv(summary_path)
    summary_fields = list(summary_rows[0].keys())
    for row in summary_rows:
        sector = row["sector_std"]
        members = [r for r in case_records if r["sector_std"] == sector]
        row["row_count"] = str(len(members))
        row["mean_core_signed_score"] = fmt6(
            statistics.mean(round(float(r["core_signed_score"]), 6) for r in members)
        )
        row["mean_extended_signed_score"] = fmt6(
            statistics.mean(round(float(r["extended_signed_score"]), 6) for r in members)
        )
        row["positive_core_row_count"] = str(
            sum(1 for r in members if float(r["core_signed_score"]) > 0)
        )
        row["positive_extended_row_count"] = str(
            sum(1 for r in members if float(r["extended_signed_score"]) > 0)
        )
        row["mean_observed_core_axis_count"] = fmt2(
            statistics.mean(int(r["observed_core_axis_count"]) for r in members)
        )
        row["mean_observed_extended_axis_count"] = fmt2(
            statistics.mean(int(r["observed_extended_axis_count"]) for r in members)
        )
        row["headline_eligible_row_count"] = str(
            sum(1 for r in members if r["headline_eligible_flag"] == "yes")
        )
    write_csv(summary_path, summary_rows, summary_fields)

    # 7. Rebuild signed_robustness_matrix.csv
    rob_path = signed_data_dir / "signed_robustness_matrix.csv"
    rob_templates = read_csv(rob_path)
    rob_fields = list(rob_templates[0].keys())
    rob_rows = [evaluate_robustness_scenario(tpl, case_records) for tpl in rob_templates]
    write_csv(rob_path, rob_rows, rob_fields)

    # 8. Rebuild T_signed_robustness_summary.csv
    rob_sum_path = signed_table_dir / "T_signed_robustness_summary.csv"
    rob_sum_templates = read_csv(rob_sum_path)
    rob_sum_fields = list(rob_sum_templates[0].keys())
    rob_sum_rows: List[Dict[str, str]] = []
    for tpl in rob_sum_templates:
        fam = tpl["test_family"]
        fam_rows = [r for r in rob_rows if r["test_family"] == fam]
        worst = min(fam_rows, key=lambda r: float(r["overall_score_mean"]))
        best = max(fam_rows, key=lambda r: float(r["overall_score_mean"]))
        tc01_any = "yes" if any(r["tc01_strong_status"] == "pass" for r in fam_rows) else "no"
        tc04_passes = sum(1 for r in fam_rows if r["tc04_base_status"] == "pass")
        tc04_any = "yes" if tc04_passes > 0 else "no"
        failures = [r["tc01_failure_reason"] for r in fam_rows if r["tc01_strong_status"] != "pass"]
        common_failure = max(dict.fromkeys(failures), key=failures.count) if failures else ""
        rob_sum_rows.append(
            {
                "test_family": fam,
                "scenario_count": str(len(fam_rows)),
                "min_overall_score_mean": worst["overall_score_mean"],
                "max_overall_score_mean": best["overall_score_mean"],
                "worst_scenario_id": worst["scenario_id"],
                "worst_scenario_label": worst["scenario_label"],
                "best_scenario_id": best["scenario_id"],
                "best_scenario_label": best["scenario_label"],
                "tc01_any_pass": tc01_any,
                "tc04_any_pass": tc04_any,
                "tc04_pass_count": str(tc04_passes),
                "most_common_tc01_failure": common_failure,
            }
        )
    write_csv(rob_sum_path, rob_sum_rows, rob_sum_fields)

    return {
        "risk_changes": risk_changes,
        "summary_rows": summary_rows,
        "robustness_baseline": rob_rows[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = rebuild_all(args.project_root)
    print(f"Rebuilt signed_rebuild tables; risk row updates={len(result['risk_changes'])}")
    for ch in result["risk_changes"]:
        print(
            f"  - {ch['peer_group_id']} | {ch['firm_std']} vs {ch['foreign_peer_std']}: "
            f"{ch['old_s_risk_recovery']:.6f} -> {ch['new_s_risk_recovery']:.6f}"
        )


if __name__ == "__main__":
    main()
