"""Reproduce report-review diagnostics without replacing historical results."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

import build_policy_scenarios as policy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/tables/review_20260915"
SOURCES = [
    "data/processed/policy_simulator_baseline_inputs.csv",
    "data/processed/policy_simulator_calibrated_parameters.csv",
    "data/processed/variable_panel_sector_quarter.csv",
    "data/processed/variable_panel_platform_quarter.csv",
    "data/processed/subindex_panel_sector_quarter.csv",
    "outputs/tables/policy_scenario_summary.csv",
    "outputs/tables/policy_sensitivity_summary.csv",
    "outputs/tables/claim_strengthening/signed_rebuild/T_signed_korea_market_case_studies.csv",
]


def read(path):
    with (ROOT / path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def weighted_minimum(values):
    # A linear-fractional weighted mean attains its box minimum at a vertex.
    return min(
        sum(w * x for w, x in zip(weights, values)) / sum(weights)
        for weights in itertools.product((0.5, 2.0), repeat=len(values))
    )


def signed_checks():
    rows = read(SOURCES[-1])
    result = []
    for row in rows:
        axes = {k: float(v) for k, v in re.findall(
            r"(?:^|;\s*)(reg|risk|market|reach|creator)=(-?[\d.]+)",
            row["construction_note"],
        )}
        core = [v for k, v in axes.items() if k in ("reg", "risk", "market")]
        ext = list(axes.values())
        assert math.isclose(statistics.mean(core), float(row["core_signed_score"]), abs_tol=1e-6)
        assert math.isclose(statistics.mean(ext), float(row["extended_signed_score"]), abs_tol=1e-6)
        out = {"case": row["case_study_label"], "sector": row["sector_std"]}
        for label, values in (("core", core), ("extended", ext)):
            out[label + "_n"] = len(values)
            out[label + "_mean"] = statistics.mean(values)
            out[label + "_loo_min"] = min(
                statistics.mean(values[:i] + values[i + 1:]) for i in range(len(values))
            ) if len(values) > 1 else ""
            out[label + "_box_weight_min"] = weighted_minimum(values)
        nonreg = [v for k, v in axes.items() if k not in ("reg", "reach")]
        out["without_reg_and_reach"] = statistics.mean(nonreg) if nonreg else ""
        result.append(out)
    write("signed_axis_robustness.csv", result)
    return result


def policy_checks():
    sector = read(SOURCES[2])
    platform = read(SOURCES[3])
    anchors, inactive = policy.build_anchor_profiles(sector)
    active = policy.subindex_components_active(anchors)
    lookup = policy.build_structural_metric_lookup(sector, platform)
    params = policy.scenario_parameter_map(read(SOURCES[1]))
    saved = {(r["baseline_id"], r["scenario_code"]): r for r in read(SOURCES[5])}
    result, cap_cases, zero_changes = [], [], []
    for base in read(SOURCES[0]):
        raw, notes = policy.enrich_baseline_raw_variables(base, lookup)
        unchanged = policy.recompute_indices(raw, anchors, active, inactive)[-1]
        for code in policy.SCENARIO_ORDER:
            key = base["baseline_id"], code
            if key not in saved:
                continue
            par = params[base["baseline_id"]][code]
            scenario = policy.evaluate_scenario(base, raw, code, par, anchors, active, inactive)
            historical = saved[key]
            assert math.isclose(scenario["CPII_scenario"], float(historical["CPII_scenario"]), abs_tol=1e-8)
            zero = policy.evaluate_scenario(base, raw, code, {k: 0.0 for k in par}, anchors, active, inactive)
            if not math.isclose(zero["CPII_scenario"], unchanged, abs_tol=1e-8):
                zero_changes.append({"baseline_id": base["baseline_id"], "scenario": code,
                                     "zero_intensity_difference": unchanged - zero["CPII_scenario"]})
            if code == "CBA":
                delta = par["theta_bargain"] * float(base["collective_bargaining_premium_base"])
                if (raw["creator_share_ratio"] or 0.0) + delta > 1:
                    cap_cases.append(base["baseline_id"])
            offset = float(base["CPII_base"]) - unchanged
            change = unchanged - scenario["CPII_scenario"]
            assert math.isclose(offset + change, float(historical["Delta_CPII"]), abs_tol=1e-8)
            result.append({"baseline_id": base["baseline_id"], "sector": base["sector_std"],
                           "quarter": base["year_quarter"], "scenario": code,
                           "published_baseline": float(base["CPII_base"]),
                           "unchanged_recomputed": unchanged,
                           "scenario_cpii": scenario["CPII_scenario"],
                           "reported_delta": float(historical["Delta_CPII"]),
                           "rebase_offset": offset, "same_input_difference": change})
    assert len(result) == len(saved) == 44
    write("policy_baseline_decomposition.csv", result)
    grouped = defaultdict(list)
    for row in result:
        grouped[(row["sector"], row["scenario"])].append(row)
    summary = []
    for (sector_name, code), members in sorted(grouped.items()):
        latest = max(members, key=lambda r: r["quarter"])
        summary.append({"sector": sector_name, "scenario": code, "n": len(members),
                        "mean_reported_delta": statistics.mean(r["reported_delta"] for r in members),
                        "mean_rebase_offset": statistics.mean(r["rebase_offset"] for r in members),
                        "mean_same_input_difference": statistics.mean(r["same_input_difference"] for r in members),
                        "latest_quarter": latest["quarter"],
                        "latest_same_input_difference": latest["same_input_difference"]})
    write("policy_baseline_decomposition_summary.csv", summary)
    by_cell = defaultdict(dict)
    for row in result:
        by_cell[(row["sector"], row["quarter"])][row["scenario"]] = row["same_input_difference"]
    contrasts = []
    for (sector_name, quarter), scores in sorted(by_cell.items()):
        for other in ("BND", "IPF", "CBA"):
            if "NET" in scores and other in scores:
                contrasts.append({"sector": sector_name, "quarter": quarter, "other": other,
                                  "net_advantage": scores["NET"] - scores[other]})
    write("policy_matched_contrasts.csv", contrasts)
    sensitivity = defaultdict(lambda: defaultdict(list))
    for row in read(SOURCES[6]):
        sensitivity[(row["sector_std"], row["year_quarter"])][row["scenario_code"]].append(float(row["Delta_CPII"]))
    adverse = []
    for (sector_name, quarter), scores in sorted(sensitivity.items()):
        for other in ("BND", "IPF", "CBA"):
            if "NET" in scores and other in scores:
                adverse.append({"sector": sector_name, "quarter": quarter, "other": other,
                                "adverse_net_advantage": min(scores["NET"]) - max(scores[other])})
    write("policy_adverse_sensitivity_contrasts.csv", adverse)
    assert len(adverse) == 30
    return summary, contrasts, {"active": active, "inactive": inactive,
                               "cba_cap_cases": cap_cases, "zero_intensity_changes": zero_changes,
                               "adverse_sensitivity": {
                                   p: {"n": len(v := [r["adverse_net_advantage"] for r in adverse if r["other"] == p]),
                                       "positive": sum(x > 1e-9 for x in v), "min": min(v)}
                                   for p in ("BND", "IPF", "CBA")}}


def channel_checks():
    result = []
    for row in read(SOURCES[4]):
        if not all(row[k] for k in ("I_reg", "I_risk", "I_market")):
            continue
        reg, risk, market = [float(row[k]) for k in ("I_reg", "I_risk", "I_market")]
        result.append({"sector": row["sector_std"], "quarter": row["year_quarter"],
                       "risk_minus_reg": risk - reg, "risk_minus_market": risk - market,
                       "market_minus_reg": market - reg, "market_minus_risk": market - risk})
    write("subindex_channel_contrasts.csv", result)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    signed = signed_checks()
    policy_summary, contrasts, details = policy_checks()
    channels = channel_checks()
    manifest = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    report = {"source_sha256": manifest, "policy_checks": details,
              "policy_summary": policy_summary,
              "matched_NET_comparisons": {
                  p: {"n": len(v := [r["net_advantage"] for r in contrasts if r["other"] == p]),
                      "positive": sum(x > 1e-9 for x in v), "min": min(v), "mean": statistics.mean(v)}
                  for p in ("BND", "IPF", "CBA")},
              "signed_sector_summary": {
                  sector: {"n": len(v := [r for r in signed if r["sector"] == sector]),
                           "extended_loo_min": min(r["extended_loo_min"] for r in v),
                           "extended_box_weight_min": min(r["extended_box_weight_min"] for r in v),
                           "core_loo_available": sum(r["core_loo_min"] != "" for r in v),
                           "core_loo_positive": sum(r["core_loo_min"] != "" and r["core_loo_min"] > 0 for r in v)}
                  for sector in sorted({r["sector"] for r in signed})},
              "channel_contrasts": channels,
              "limits": ["No new source observations; frozen historical data.",
                         "Sensitivity results are deterministic, not confidence intervals.",
                         "Policy decomposition does not repair historical scenario boundary rules."]}
    with (OUT / "review_checks.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
