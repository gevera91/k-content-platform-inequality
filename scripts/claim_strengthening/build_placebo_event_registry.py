from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = PROJECT_ROOT / "data/registry/event_registry.csv"
OUTPUT_PATH = (
    PROJECT_ROOT / "data/registry/claim_strengthening/placebo_event_registry.csv"
)
LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/placebo_event_registry_log.md"
)


PLACEBO_RULES: dict[str, dict[str, str]] = {
    "naver_webtoon_cuts_kr_20250901": {
        "placebo_class": "domestic_incumbent_self_upgrade",
        "why_unrelated_to_claim": (
            "Korean incumbent self-upgrade should not be used as evidence that global big-tech entry "
            "or foreign burden asymmetry harms Korean platforms."
        ),
        "expected_effect_on_claim_outcomes": (
            "If anything, this should improve the local incumbent's own platform outcomes rather than "
            "proxying reverse discrimination."
        ),
        "selection_basis": (
            "Official event with observed pre/post window, but mechanism runs in the opposite direction "
            "from the claim-strengthening global-peer shock."
        ),
        "claim_overlap_risk": "low",
    },
    "piccoma_kuji_jp_20251203": {
        "placebo_class": "korean_owned_foreign_expansion",
        "why_unrelated_to_claim": (
            "Korean-owned service expansion abroad should not be interpreted as a global big-tech shock "
            "imposing reverse discrimination on Korean firms."
        ),
        "expected_effect_on_claim_outcomes": (
            "This event is more consistent with Korean-platform overseas expansion than with Korean "
            "disadvantage inside a global-peer comparison."
        ),
        "selection_basis": (
            "Official event with a treated panel row, included to test whether the claim framework "
            "spuriously flags Korean-owned foreign launches as adverse shocks."
        ),
        "claim_overlap_risk": "low",
    },
    "webtoon_video_episodes_uk_20250818": {
        "placebo_class": "noncore_foreign_feature_launch",
        "why_unrelated_to_claim": (
            "A weak-support UK-facing feature launch in a noncore cell should not be treated as direct "
            "evidence of Korean reverse discrimination."
        ),
        "expected_effect_on_claim_outcomes": (
            "At most this is a distant product-iteration shock; it should not systematically reproduce "
            "the claimed Korean disadvantage pattern."
        ),
        "selection_basis": (
            "Official event deliberately excluded from the narrow claim registry because regression "
            "support is weak and the country cell is not a core comparable setting."
        ),
        "claim_overlap_risk": "medium",
    },
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_rows() -> list[dict[str, str]]:
    source_rows = {row["event_id"]: row for row in read_rows(SOURCE_PATH)}
    output_rows: list[dict[str, str]] = []
    for event_id, rule in PLACEBO_RULES.items():
        row = source_rows[event_id]
        output_rows.append(
            {
                "event_id": row["event_id"],
                "event_label": row["event_label"],
                "sector_std": row["sector_std"],
                "country_std": row["country_std"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "event_date": row["event_date"],
                "panel_type": row["panel_type"],
                "sample_strength": row["sample_strength"],
                "recommended_for_regression_flag": row["recommended_for_regression_flag"],
                "placebo_class": rule["placebo_class"],
                "why_unrelated_to_claim": rule["why_unrelated_to_claim"],
                "expected_effect_on_claim_outcomes": rule["expected_effect_on_claim_outcomes"],
                "selection_basis": rule["selection_basis"],
                "claim_overlap_risk": rule["claim_overlap_risk"],
                "source_url": row["source_url"],
            }
        )
    output_rows.sort(key=lambda item: (item["sector_std"], item["event_id"]))
    return output_rows


def write_csv(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_id",
        "event_label",
        "sector_std",
        "country_std",
        "firm_std",
        "service_std",
        "event_date",
        "panel_type",
        "sample_strength",
        "recommended_for_regression_flag",
        "placebo_class",
        "why_unrelated_to_claim",
        "expected_effect_on_claim_outcomes",
        "selection_basis",
        "claim_overlap_risk",
        "source_url",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]]) -> None:
    class_counts = Counter(row["placebo_class"] for row in rows)
    sector_counts = Counter(row["sector_std"] for row in rows)
    strength_counts = Counter(row["sample_strength"] for row in rows)
    regression_counts = Counter(row["recommended_for_regression_flag"] for row in rows)

    with LOG_PATH.open("w", encoding="utf-8") as handle:
        handle.write("# Strength Prompt 42. Placebo Event Registry\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- placebo event count: `{len(rows)}`\n")
        handle.write("- selection rule: keep only official events that should be orthogonal to the reverse-discrimination claim mechanism or move in the opposite direction\n\n")

        handle.write("## By Placebo Class\n\n")
        for key in sorted(class_counts):
            handle.write(f"- `{key}`: `{class_counts[key]}`\n")
        handle.write("\n")

        handle.write("## By Sector\n\n")
        for key in sorted(sector_counts):
            handle.write(f"- `{key}`: `{sector_counts[key]}`\n")
        handle.write("\n")

        handle.write("## Strength And Regression Support\n\n")
        for key in sorted(strength_counts):
            handle.write(f"- `sample_strength={key}`: `{strength_counts[key]}`\n")
        for key in sorted(regression_counts):
            handle.write(
                f"- `recommended_for_regression_flag={key}`: `{regression_counts[key]}`\n"
            )
        handle.write("\n")

        handle.write("## Event Notes\n\n")
        for row in rows:
            handle.write(
                f"- `{row['event_id']}` | class=`{row['placebo_class']}` | "
                f"risk=`{row['claim_overlap_risk']}` | {row['selection_basis']}\n"
            )


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_log(rows)


if __name__ == "__main__":
    main()
