from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

MONTH_PANEL_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
QUARTER_PANEL_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
EVENT_REGISTRY_PATH = ROOT / "data/registry/event_registry.csv"
EVENT_STUDY_PANEL_PATH = ROOT / "data/processed/event_study_panel.csv"
EVENT_LOG_PATH = ROOT / "logs/event_registry_log.md"


@dataclass(frozen=True)
class EventDefinition:
    event_id: str
    event_label: str
    event_type: str
    sector_std: str
    country_std: str
    firm_std: str
    service_std: str
    panel_type: str
    event_date: str
    source_published_date: str
    event_date_basis: str
    source_title: str
    source_url: str
    window_pre: int
    window_post: int
    notes: str


EVENTS: list[EventDefinition] = [
    EventDefinition(
        event_id="spotify_lossless_au_20250910",
        event_label="Spotify Lossless rollout in Australia",
        event_type="service_launch",
        sector_std="music",
        country_std="au",
        firm_std="spotify",
        service_std="spotify",
        panel_type="platform_month",
        event_date="2025-09-10",
        source_published_date="2025-09-10",
        event_date_basis="official_publication_date",
        source_title="Lossless listening arrives on Spotify Premium with a richer, more detailed listening experience",
        source_url="https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/",
        window_pre=3,
        window_post=5,
        notes="Official Spotify rollout article states that Australia had already started getting access in the September 2025 rollout window.",
    ),
    EventDefinition(
        event_id="spotify_lossless_de_20250910",
        event_label="Spotify Lossless rollout in Germany",
        event_type="service_launch",
        sector_std="music",
        country_std="de",
        firm_std="spotify",
        service_std="spotify",
        panel_type="platform_month",
        event_date="2025-09-10",
        source_published_date="2025-09-10",
        event_date_basis="official_publication_date",
        source_title="Lossless listening arrives on Spotify Premium with a richer, more detailed listening experience",
        source_url="https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/",
        window_pre=3,
        window_post=5,
        notes="Official Spotify rollout article states that Germany had already started getting access in the September 2025 rollout window.",
    ),
    EventDefinition(
        event_id="spotify_lossless_jp_20250910",
        event_label="Spotify Lossless rollout in Japan",
        event_type="service_launch",
        sector_std="music",
        country_std="jp",
        firm_std="spotify",
        service_std="spotify",
        panel_type="platform_month",
        event_date="2025-09-10",
        source_published_date="2025-09-10",
        event_date_basis="official_publication_date",
        source_title="Lossless listening arrives on Spotify Premium with a richer, more detailed listening experience",
        source_url="https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/",
        window_pre=3,
        window_post=5,
        notes="Official Spotify rollout article states that Japan had already started getting access in the September 2025 rollout window.",
    ),
    EventDefinition(
        event_id="spotify_lossless_uk_20250910",
        event_label="Spotify Lossless rollout in the UK",
        event_type="service_launch",
        sector_std="music",
        country_std="uk",
        firm_std="spotify",
        service_std="spotify",
        panel_type="platform_month",
        event_date="2025-09-10",
        source_published_date="2025-09-10",
        event_date_basis="official_publication_date",
        source_title="Lossless listening arrives on Spotify Premium with a richer, more detailed listening experience",
        source_url="https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/",
        window_pre=3,
        window_post=5,
        notes="Official Spotify rollout article states that the UK had already started getting access in the September 2025 rollout window.",
    ),
    EventDefinition(
        event_id="spotify_lossless_us_20250910",
        event_label="Spotify Lossless rollout in the US",
        event_type="service_launch",
        sector_std="music",
        country_std="us",
        firm_std="spotify",
        service_std="spotify",
        panel_type="platform_month",
        event_date="2025-09-10",
        source_published_date="2025-09-10",
        event_date_basis="official_publication_date",
        source_title="Lossless listening arrives on Spotify Premium with a richer, more detailed listening experience",
        source_url="https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/",
        window_pre=3,
        window_post=5,
        notes="Official Spotify rollout article states that the US had already started getting access in the September 2025 rollout window.",
    ),
    EventDefinition(
        event_id="youtube_premium_lite_au_20250305",
        event_label="YouTube Premium Lite pilot expansion in Australia",
        event_type="pricing_bundle_upgrade",
        sector_std="digital_infra",
        country_std="au",
        firm_std="alphabet",
        service_std="youtube",
        panel_type="platform_quarter",
        event_date="2025-03-05",
        source_published_date="2025-04-02",
        event_date_basis="official_announcement_date",
        source_title="YouTube announcements from March - Introducing Premium Lite",
        source_url="https://blog.youtube/news-and-events/the-latest-news-we-announced-in-march/",
        window_pre=1,
        window_post=2,
        notes="Official YouTube March announcements recap states that Premium Lite would be made available to all users in the current pilot country Australia after the March 2025 announcement.",
    ),
    EventDefinition(
        event_id="youtube_premium_lite_de_20250305",
        event_label="YouTube Premium Lite pilot expansion in Germany",
        event_type="pricing_bundle_upgrade",
        sector_std="digital_infra",
        country_std="de",
        firm_std="alphabet",
        service_std="youtube",
        panel_type="platform_quarter",
        event_date="2025-03-05",
        source_published_date="2025-03-05",
        event_date_basis="official_announcement_date",
        source_title="Premium Lite: ein Großteil deiner Lieblingsinhalte ohne Werbeunterbrechungen",
        source_url="https://blog.youtube/intl/de-de/inside-youtube/neu-premium-lite-ein-grossteil-deiner-lieblingsinhalte-ohne-werbeunterbrechungen/",
        window_pre=1,
        window_post=2,
        notes="Official German YouTube blog announced on March 5, 2025 and stated that the product would become available in Germany from April 10, 2025.",
    ),
    EventDefinition(
        event_id="webtoon_video_episodes_us_20250818",
        event_label="WEBTOON Video Episodes launch in the US-facing platform",
        event_type="service_launch",
        sector_std="webtoon_story",
        country_std="us",
        firm_std="webtoon_ent",
        service_std="webtoon",
        panel_type="platform_quarter",
        event_date="2025-08-18",
        source_published_date="2025-08-18",
        event_date_basis="official_publication_date",
        source_title="WEBTOON Entertainment Brings Webcomics to Life with Video Episodes",
        source_url="https://ir.webtoon.com/node/7501/pdf",
        window_pre=1,
        window_post=2,
        notes="Official WEBTOON Entertainment release introducing Video Episodes on the English-language platform.",
    ),
    EventDefinition(
        event_id="webtoon_video_episodes_ca_20250818",
        event_label="WEBTOON Video Episodes launch in the Canada-facing platform",
        event_type="service_launch",
        sector_std="webtoon_story",
        country_std="ca",
        firm_std="webtoon_ent",
        service_std="webtoon",
        panel_type="platform_quarter",
        event_date="2025-08-18",
        source_published_date="2025-08-18",
        event_date_basis="official_publication_date",
        source_title="WEBTOON Entertainment Brings Webcomics to Life with Video Episodes",
        source_url="https://ir.webtoon.com/node/7501/pdf",
        window_pre=1,
        window_post=2,
        notes="Official WEBTOON Entertainment release introducing Video Episodes on the English-language platform.",
    ),
    EventDefinition(
        event_id="webtoon_video_episodes_uk_20250818",
        event_label="WEBTOON Video Episodes launch in the UK-facing platform",
        event_type="service_launch",
        sector_std="webtoon_story",
        country_std="uk",
        firm_std="webtoon_ent",
        service_std="webtoon",
        panel_type="platform_quarter",
        event_date="2025-08-18",
        source_published_date="2025-08-18",
        event_date_basis="official_publication_date",
        source_title="WEBTOON Entertainment Brings Webcomics to Life with Video Episodes",
        source_url="https://ir.webtoon.com/node/7501/pdf",
        window_pre=1,
        window_post=2,
        notes="Official WEBTOON Entertainment release introducing Video Episodes on the English-language platform.",
    ),
    EventDefinition(
        event_id="naver_webtoon_cuts_kr_20250901",
        event_label="NAVER WEBTOON Cuts debut in Korea",
        event_type="service_launch",
        sector_std="webtoon_story",
        country_std="kr",
        firm_std="naver",
        service_std="naver_webtoon",
        panel_type="platform_quarter",
        event_date="2025-09-01",
        source_published_date="2025-09-04",
        event_date_basis="official_service_start_date",
        source_title="WEBTOON Entertainment's NAVER WEBTOON Debuts Cuts, a New Short-Form Animated Video Feature in Korea",
        source_url="https://ir.webtoon.com/news-releases/news-release-details/webtoon-entertainments-naver-webtoon-debuts-cuts-new-short-form",
        window_pre=1,
        window_post=2,
        notes="Official press release states that NAVER WEBTOON officially launched Cuts on September 1, 2025 in Korea.",
    ),
    EventDefinition(
        event_id="piccoma_kuji_jp_20251203",
        event_label="Piccoma Kuji online raffle service launch in Japan",
        event_type="service_launch",
        sector_std="webtoon_story",
        country_std="jp",
        firm_std="kakao_piccoma",
        service_std="piccoma",
        panel_type="platform_quarter",
        event_date="2025-12-03",
        source_published_date="2025-12-03",
        event_date_basis="official_service_start_date",
        source_title="PRESS RELEASE",
        source_url="https://www.kakaopiccoma.com/wp-content/uploads/PR_piccoma_kuji_2501203.pdf",
        window_pre=1,
        window_post=2,
        notes="Official Kakao Piccoma press release states that Piccoma Kuji would open on December 3, 2025 at around 12:00 JST.",
    ),
]


REJECTED_EVENTS = [
    {
        "event_id": "netflix_naver_plus_kr_20241126",
        "reason": "Current digital_infra platform-quarter panel has no treated pre-period with available variables before the bundle launch.",
        "source_title": "Netflix and Naver Plus come together in Korea",
        "source_url": "https://about.netflix.com/en/news/naver-plus-korea",
    },
    {
        "event_id": "youtube_premium_lite_kr_20260130",
        "reason": "Current digital_infra platform-quarter panel has no treated post-period after the Korea launch date.",
        "source_title": "YouTube Premium Lite gets background play and downloads",
        "source_url": "https://blog.youtube/news-and-events/youtube-premium-lite-background-play-downloads/",
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def quarter_from_date(d: date) -> str:
    return f"{d.year}Q{((d.month - 1) // 3) + 1}"


def quarter_index(value: str) -> int:
    year = int(value[:4])
    quarter = int(value[-1])
    return year * 4 + quarter - 1


def month_index(value: str) -> int:
    year, month = map(int, value.split("-"))
    return year * 12 + month - 1


def month_from_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def get_panel_rows(panel_type: str, month_rows: list[dict[str, str]], quarter_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if panel_type == "platform_month":
        return month_rows
    if panel_type == "platform_quarter":
        return quarter_rows
    raise ValueError(f"Unsupported panel_type: {panel_type}")


def get_panel_time_value(panel_type: str, row: dict[str, str]) -> str:
    return row["year_month"] if panel_type == "platform_month" else row["year_quarter"]


def get_panel_row_id(panel_type: str, row: dict[str, str]) -> str:
    return row["panel_platform_month_id"] if panel_type == "platform_month" else row["panel_platform_quarter_id"]


def relative_period(panel_type: str, panel_time_value: str, event_date_value: date) -> int:
    if panel_type == "platform_month":
        return month_index(panel_time_value) - month_index(month_from_date(event_date_value))
    return quarter_index(panel_time_value) - quarter_index(quarter_from_date(event_date_value))


def within_window(rel: int, pre: int, post: int) -> bool:
    return -pre <= rel <= post


def is_yes(value: str) -> bool:
    return (value or "").strip().lower() == "yes"


def as_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def event_strength(pre_available: int, post_available: int) -> str:
    if pre_available >= 1 and post_available >= 1:
        return "strong"
    if pre_available + post_available >= 1:
        return "medium"
    return "weak"


def build_outputs() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int], dict[str, Counter]]:
    month_rows = read_csv(MONTH_PANEL_PATH)
    quarter_rows = read_csv(QUARTER_PANEL_PATH)

    registry_rows: list[dict[str, str]] = []
    event_panel_rows: list[dict[str, str]] = []

    summary_counts = {
        "event_count": 0,
        "panel_row_count": 0,
        "treated_panel_row_count": 0,
        "control_panel_row_count": 0,
    }
    strength_counter: Counter[str] = Counter()
    sector_counter: Counter[str] = Counter()
    panel_counter: Counter[str] = Counter()

    for event in EVENTS:
        event_date_value = date.fromisoformat(event.event_date)
        panel_rows = get_panel_rows(event.panel_type, month_rows, quarter_rows)
        candidate_rows = [row for row in panel_rows if row["sector_std"] == event.sector_std]

        window_rows: list[dict[str, str]] = []
        treated_rows: list[dict[str, str]] = []
        for row in candidate_rows:
            panel_time = get_panel_time_value(event.panel_type, row)
            rel = relative_period(event.panel_type, panel_time, event_date_value)
            if not within_window(rel, event.window_pre, event.window_post):
                continue

            treated_flag = (
                row["country_std"] == event.country_std
                and row["firm_std"] == event.firm_std
                and row["service_std"] == event.service_std
            )
            available_count = as_int(row.get("available_variable_count", "0"))
            observed_flag = is_yes(row.get("observed_any_flag", ""))
            row_out = {
                "event_panel_row_id": f"{event.event_id}__{get_panel_row_id(event.panel_type, row)}",
                "event_id": event.event_id,
                "event_label": event.event_label,
                "event_type": event.event_type,
                "panel_type": event.panel_type,
                "relative_period": str(rel),
                "relative_period_unit": "month" if event.panel_type == "platform_month" else "quarter",
                "treated_flag": "1" if treated_flag else "0",
                "control_flag": "0" if treated_flag else "1",
                "pre_flag": "1" if rel < 0 else "0",
                "event_period_flag": "1" if rel == 0 else "0",
                "post_flag": "1" if rel > 0 else "0",
                "in_event_window_flag": "1",
                "event_date": event.event_date,
                "event_year_month": month_from_date(event_date_value),
                "event_year_quarter": quarter_from_date(event_date_value),
                "source_published_date": event.source_published_date,
                "event_date_basis": event.event_date_basis,
                "source_title": event.source_title,
                "source_url": event.source_url,
                "window_pre": str(event.window_pre),
                "window_post": str(event.window_post),
                "panel_time_key": panel_time,
                "panel_row_id": get_panel_row_id(event.panel_type, row),
                "available_variable_count_int": str(available_count),
                "observed_any_flag_standardized": "yes" if observed_flag else "no",
                "candidate_strength_note": event.notes,
            }
            row_out.update(row)
            window_rows.append(row_out)
            if treated_flag:
                treated_rows.append(row_out)

        treated_pre = [row for row in treated_rows if int(row["relative_period"]) < 0]
        treated_post = [row for row in treated_rows if int(row["relative_period"]) > 0]
        treated_event = [row for row in treated_rows if int(row["relative_period"]) == 0]
        treated_available_pre = sum(as_int(row.get("available_variable_count", "0")) > 0 for row in treated_pre)
        treated_available_post = sum(as_int(row.get("available_variable_count", "0")) > 0 for row in treated_post)
        treated_observed_pre = sum(is_yes(row.get("observed_any_flag", "")) for row in treated_pre)
        treated_observed_post = sum(is_yes(row.get("observed_any_flag", "")) for row in treated_post)
        strength = event_strength(treated_available_pre, treated_available_post)
        recommended = "yes" if strength == "strong" else "no"

        for row in window_rows:
            row["sample_strength"] = strength
            row["recommended_for_regression_flag"] = recommended
            event_panel_rows.append(row)

        registry_rows.append(
            {
                "event_id": event.event_id,
                "event_label": event.event_label,
                "event_type": event.event_type,
                "sector_std": event.sector_std,
                "country_std": event.country_std,
                "firm_std": event.firm_std,
                "service_std": event.service_std,
                "event_date": event.event_date,
                "relative_period": "0",
                "treated_flag": "1",
                "panel_type": event.panel_type,
                "relative_period_unit": "month" if event.panel_type == "platform_month" else "quarter",
                "event_year_month": month_from_date(event_date_value),
                "event_year_quarter": quarter_from_date(event_date_value),
                "source_published_date": event.source_published_date,
                "event_date_basis": event.event_date_basis,
                "source_title": event.source_title,
                "source_url": event.source_url,
                "window_pre": str(event.window_pre),
                "window_post": str(event.window_post),
                "treated_panel_row_count": str(len(treated_rows)),
                "treated_pre_count": str(len(treated_pre)),
                "treated_event_period_count": str(len(treated_event)),
                "treated_post_count": str(len(treated_post)),
                "treated_available_pre_count": str(treated_available_pre),
                "treated_available_post_count": str(treated_available_post),
                "treated_observed_pre_count": str(treated_observed_pre),
                "treated_observed_post_count": str(treated_observed_post),
                "sample_strength": strength,
                "recommended_for_regression_flag": recommended,
                "notes": event.notes,
            }
        )

        summary_counts["event_count"] += 1
        summary_counts["panel_row_count"] += len(window_rows)
        summary_counts["treated_panel_row_count"] += len(treated_rows)
        summary_counts["control_panel_row_count"] += len(window_rows) - len(treated_rows)
        strength_counter[strength] += 1
        sector_counter[event.sector_std] += 1
        panel_counter[event.panel_type] += 1

    auxiliary_counters = {
        "strength": strength_counter,
        "sector": sector_counter,
        "panel": panel_counter,
    }
    return registry_rows, event_panel_rows, summary_counts, auxiliary_counters


def registry_fieldnames(rows: Iterable[dict[str, str]]) -> list[str]:
    preferred = [
        "event_id",
        "event_label",
        "event_type",
        "sector_std",
        "country_std",
        "firm_std",
        "service_std",
        "event_date",
        "relative_period",
        "treated_flag",
        "panel_type",
        "relative_period_unit",
        "event_year_month",
        "event_year_quarter",
        "source_published_date",
        "event_date_basis",
        "source_title",
        "source_url",
        "window_pre",
        "window_post",
        "treated_panel_row_count",
        "treated_pre_count",
        "treated_event_period_count",
        "treated_post_count",
        "treated_available_pre_count",
        "treated_available_post_count",
        "treated_observed_pre_count",
        "treated_observed_post_count",
        "sample_strength",
        "recommended_for_regression_flag",
        "notes",
    ]
    all_keys = set().union(*(row.keys() for row in rows))
    remainder = sorted(key for key in all_keys if key not in preferred)
    return preferred + remainder


def panel_fieldnames(rows: Iterable[dict[str, str]]) -> list[str]:
    preferred = [
        "event_panel_row_id",
        "event_id",
        "event_label",
        "event_type",
        "sector_std",
        "panel_type",
        "relative_period",
        "relative_period_unit",
        "treated_flag",
        "control_flag",
        "pre_flag",
        "event_period_flag",
        "post_flag",
        "in_event_window_flag",
        "country_std",
        "firm_std",
        "service_std",
        "event_date",
        "event_year_month",
        "event_year_quarter",
        "source_published_date",
        "event_date_basis",
        "source_title",
        "source_url",
        "sample_strength",
        "recommended_for_regression_flag",
        "window_pre",
        "window_post",
        "panel_time_key",
        "panel_row_id",
        "year_month",
        "year_quarter",
        "available_variable_count_int",
        "observed_any_flag_standardized",
    ]
    all_keys = set().union(*(row.keys() for row in rows))
    remainder = sorted(key for key in all_keys if key not in preferred)
    return preferred + remainder


def write_log(
    registry_rows: list[dict[str, str]],
    event_panel_rows: list[dict[str, str]],
    summary_counts: dict[str, int],
    counters: dict[str, Counter],
) -> None:
    treated_rows = [row for row in event_panel_rows if row["treated_flag"] == "1"]
    regression_ready = [row for row in registry_rows if row["recommended_for_regression_flag"] == "yes"]
    strength_lines = "\n".join(
        f"- `{key}`: {value}" for key, value in sorted(counters["strength"].items())
    )
    sector_lines = "\n".join(
        f"- `{key}`: {value}" for key, value in sorted(counters["sector"].items())
    )
    panel_lines = "\n".join(
        f"- `{key}`: {value}" for key, value in sorted(counters["panel"].items())
    )
    event_lines = "\n".join(
        (
            f"- `{row['event_id']}` | `{row['sector_std']}` | `{row['panel_type']}` | "
            f"`strength={row['sample_strength']}` | "
            f"`pre_avail={row['treated_available_pre_count']}` | "
            f"`post_avail={row['treated_available_post_count']}` | "
            f"[source]({row['source_url']})"
        )
        for row in registry_rows
    )
    rejected_lines = "\n".join(
        f"- `{item['event_id']}`: {item['reason']} ([source]({item['source_url']}))"
        for item in REJECTED_EVENTS
    )

    content = f"""# Exec Prompt 30 Event Registry Log

## Summary

- Included event count: `{summary_counts['event_count']}`
- Event-study panel row count: `{summary_counts['panel_row_count']}`
- Treated row count: `{summary_counts['treated_panel_row_count']}`
- Control row count: `{summary_counts['control_panel_row_count']}`
- Regression-ready events: `{len(regression_ready)}`

## By Strength

{strength_lines}

## By Sector

{sector_lines}

## By Panel Type

{panel_lines}

## Window Rules

- `platform_month`: relative month window `[-3, +5]`
- `platform_quarter`: relative quarter window `[-1, +2]`
- `sample_strength=strong`: treated panel has at least one pre-event and one post-event row with `available_variable_count > 0`
- `recommended_for_regression_flag=yes`: only strong events

## Included Events

{event_lines}

## Rejected But Documented Candidates

{rejected_lines}

## Notes

- This registry is anchored to official publisher, platform, or corporate IR pages only.
- The event-study panel keeps both treated and untreated rows from the same sector and source panel so later regressions can tighten the control definition without rebuilding the event table.
- Some digital infrastructure events are intentionally kept as `medium` because the current platform-quarter build has thin pre-treatment observable coverage even though the official event date is verified.
"""
    EVENT_LOG_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    registry_rows, event_panel_rows, summary_counts, counters = build_outputs()
    registry_rows = sorted(registry_rows, key=lambda row: row["event_id"])
    event_panel_rows = sorted(
        event_panel_rows,
        key=lambda row: (
            row["event_id"],
            row["panel_type"],
            row["panel_time_key"],
            row["treated_flag"] != "1",
            row["country_std"],
            row["firm_std"],
            row["service_std"],
        ),
    )

    write_csv(EVENT_REGISTRY_PATH, registry_rows, registry_fieldnames(registry_rows))
    write_csv(EVENT_STUDY_PANEL_PATH, event_panel_rows, panel_fieldnames(event_panel_rows))
    write_log(registry_rows, event_panel_rows, summary_counts, counters)


if __name__ == "__main__":
    main()
