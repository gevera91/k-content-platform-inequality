from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "processed" / "claim_strengthening" / "music_econ_extension"
LOG_DIR = PROJECT_ROOT / "logs" / "claim_strengthening" / "music_econ_extension"

EVENT_PANEL_PATH = DATA_DIR / "premium_lite_post_remedy_panel.csv"
PRICE_PANEL_PATH = DATA_DIR / "platform_product_price_panel.csv"
OUTPUT_PATH = DATA_DIR / "premium_lite_did_results.csv"
LOG_PATH = LOG_DIR / "premium_lite_did_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def first_match(rows: list[dict[str, str]], **conditions: str) -> dict[str, str]:
    for row in rows:
        if all(row.get(k, "") == v for k, v in conditions.items()):
            return row
    raise ValueError(f"Could not find row in {conditions}")


def as_int(value: str) -> int:
    return int(float(value))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_results() -> list[dict[str, object]]:
    event_rows = read_csv(EVENT_PANEL_PATH)
    _price_rows = read_csv(PRICE_PANEL_PATH)

    treated_pre = as_int(
        first_match(event_rows, platform_std="youtube_music", month="2026-01")["price_proxy"]
    )
    treated_post = as_int(
        first_match(event_rows, platform_std="youtube", month="2026-03")["price_proxy"]
    )
    melon_post = as_int(first_match(event_rows, platform_std="melon", month="2026-03")["price_proxy"])
    spotify_post = as_int(
        first_match(event_rows, platform_std="spotify", month="2026-03")["price_proxy"]
    )

    def price_proxy_row(
        result_id: str,
        control_side: str,
        control_price_post: int,
        interpretation_note: str,
    ) -> dict[str, object]:
        pre_gap = treated_pre - control_price_post
        post_gap = treated_post - control_price_post
        estimate = post_gap - pre_gap
        return {
            "result_id": result_id,
            "outcome_name": "minimum_paid_entry_price_gap_change",
            "treated_side": "youtube_ecosystem_paid_entry_anchor",
            "control_side": control_side,
            "pre_period": "pre_lite_counterfactual_existing_youtube_music_price_anchor",
            "post_period": "2026-03",
            "pre_gap_value": pre_gap,
            "post_gap_value": post_gap,
            "estimate_value": estimate,
            "estimate_unit": "krw_gap_change",
            "estimation_status": "estimable_proxy_only",
            "identification_type": "calibrated_same_country_did_proxy",
            "identifying_assumption": (
                "The relevant pre-treatment paid-entry anchor for the YouTube ecosystem is the "
                "existing YouTube Music Premium price of KRW 11990, and the same-country control "
                "price is stable over the short January-to-March 2026 window."
            ),
            "pretrend_limit": (
                "No month-matched archived pre-launch control-price panel exists and there is no "
                "testable multi-period pretrend for this outcome in the current workspace."
            ),
            "why_same_country_better_than_legacy": (
                "This design keeps treatment and control inside Korea and therefore avoids the "
                "cross-country composition problem in the legacy mixed comparison when the question "
                "is specifically about the Korean Premium Lite remedy."
            ),
            "source_stack": (
                "premium_lite_post_remedy_panel.csv;platform_product_price_panel.csv;"
                "youtube_bundle_official_timeline.csv"
            ),
            "interpretation_note": interpretation_note,
        }

    results: list[dict[str, object]] = [
        price_proxy_row(
            "PLD01",
            "melon_streaming_club_regular",
            melon_post,
            (
                "Relative to Melon's regular domestic audio-first monthly plan, the YouTube "
                "ecosystem minimum paid-entry gap shifts from KRW 3300 above the control to "
                "KRW 190 below it, implying a KRW -3490 same-country price-entry DID-style proxy."
            ),
        ),
        price_proxy_row(
            "PLD02",
            "spotify_premium_individual",
            spotify_post,
            (
                "Relative to Spotify Premium Individual in the same Korean market, the YouTube "
                "ecosystem minimum paid-entry gap moves from parity to KRW 3490 below the control, "
                "again yielding a KRW -3490 DID-style proxy under the short-window stability assumption."
            ),
        ),
        {
            "result_id": "PLD03",
            "outcome_name": "domestic_audio_app_usage_proxy",
            "treated_side": "youtube_music_ecosystem",
            "control_side": "same_country_domestic_audio_apps",
            "pre_period": "2025-05",
            "post_period": "2026-01_to_2026-04",
            "pre_gap_value": "",
            "post_gap_value": "",
            "estimate_value": "",
            "estimate_unit": "not_available",
            "estimation_status": "not_estimable_current_archive",
            "identification_type": "stacked_event_study_not_feasible_yet",
            "identifying_assumption": (
                "A usable same-country usage DID would require archived post-launch Korean usage "
                "series for treated and control platforms."
            ),
            "pretrend_limit": (
                "Only one pre-remedy usage snapshot exists in the current archive and there is no "
                "post-launch usage series, so neither pretrend testing nor treatment estimation is possible."
            ),
            "why_same_country_better_than_legacy": (
                "If later expanded, the same-country archive would hold market environment fixed and "
                "be better suited than the legacy mixed peer design for remedy-effect questions."
            ),
            "source_stack": "premium_lite_post_remedy_panel.csv;music_demand_proxy_panel.csv",
            "interpretation_note": (
                "This outcome remains intentionally unestimated because the current workspace lacks "
                "archived post-launch usage observations."
            ),
        },
        {
            "result_id": "PLD04",
            "outcome_name": "app_rank_proxy",
            "treated_side": "youtube_music_ecosystem",
            "control_side": "same_country_domestic_audio_apps",
            "pre_period": "2025-05",
            "post_period": "2026-01_to_2026-04",
            "pre_gap_value": "",
            "post_gap_value": "",
            "estimate_value": "",
            "estimate_unit": "not_available",
            "estimation_status": "not_estimable_current_archive",
            "identification_type": "stacked_event_study_not_feasible_yet",
            "identifying_assumption": (
                "A usable same-country rank DID would require archived post-launch Korean app-rank "
                "or comparable rank-based outcome series for treated and control platforms."
            ),
            "pretrend_limit": (
                "The current archive contains only a single pre-remedy common-snapshot rank ordering "
                "and no post-launch rank series, so there is no event-study path to estimate."
            ),
            "why_same_country_better_than_legacy": (
                "If archived later, rank-based same-country evidence would isolate the Korean remedy "
                "question better than legacy cross-country reduced-form comparisons."
            ),
            "source_stack": "premium_lite_post_remedy_panel.csv;music_demand_proxy_panel.csv",
            "interpretation_note": (
                "This outcome remains intentionally unestimated because the current workspace lacks "
                "archived post-launch rank observations."
            ),
        },
    ]

    return results


def write_log(path: Path, results: list[dict[str, object]]) -> None:
    estimable = [row for row in results if row["estimation_status"] == "estimable_proxy_only"]
    blocked = [row for row in results if row["estimation_status"] != "estimable_proxy_only"]
    lines = [
        "# Music Econometric Extension 22. Premium Lite DID Log",
        "",
        f"- Created `{OUTPUT_PATH.name}` with {len(results)} result rows.",
        f"- Estimable proxy rows: {len(estimable)}.",
        f"- Not-estimable rows: {len(blocked)}.",
        "- The only outcome that the current archive supports is a calibrated same-country DID-style price-entry proxy.",
        "- The design compares the YouTube ecosystem's pre-Lite paid-entry anchor of KRW 11990 with the post-Lite KRW 8500 entry price and treats same-country control prices as stable over the short January-to-March 2026 window.",
        "- This is not a full panel DID because the current workspace lacks archived month-matched pre-launch control-price series and any post-launch usage or rank series.",
        "- The key design rule locked in here is that usage and rank outcomes remain explicitly unestimated until the archive gains post-launch Korean series rather than being backfilled with live lookups or unsupported assumptions.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = build_results()
    fieldnames = [
        "result_id",
        "outcome_name",
        "treated_side",
        "control_side",
        "pre_period",
        "post_period",
        "pre_gap_value",
        "post_gap_value",
        "estimate_value",
        "estimate_unit",
        "estimation_status",
        "identification_type",
        "identifying_assumption",
        "pretrend_limit",
        "why_same_country_better_than_legacy",
        "source_stack",
        "interpretation_note",
    ]
    write_csv(OUTPUT_PATH, fieldnames, results)
    write_log(LOG_PATH, results)


if __name__ == "__main__":
    main()
