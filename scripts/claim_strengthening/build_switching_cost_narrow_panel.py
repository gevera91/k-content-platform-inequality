from __future__ import annotations

import csv
import re
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
COUNTRY_USAGE_REGISTRY_PATH = ROOT / "data/interim/country_market_usage_registry.csv"
MONTH_PANEL_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
EVENT_REGISTRY_NARROW_PATH = (
    ROOT / "data/registry/claim_strengthening/event_registry_narrow.csv"
)
EVENT_STUDY_PANEL_PATH = ROOT / "data/processed/event_study_panel.csv"

OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/switching_cost_narrow_panel.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.9f}".rstrip("0").rstrip(".")


def parse_kr_multihoming_rate() -> float | None:
    rows = read_csv(COUNTRY_USAGE_REGISTRY_PATH)
    kr_row = next((row for row in rows if row["country_std"] == "kr"), None)
    if kr_row is None:
        return None
    match = re.search(r"average\s+([0-9.]+)\s+subscriptions", kr_row["notes"])
    if not match:
        return None
    return float(match.group(1))


def latest_month_metrics() -> tuple[dict[tuple[str, str, str], tuple[str, float]], dict[tuple[str, str, str], tuple[str, float]]]:
    rows = read_csv(MONTH_PANEL_PATH)
    bundle_lookup: dict[tuple[str, str, str], tuple[str, float]] = {}
    chart_lookup: dict[tuple[str, str, str], tuple[str, float]] = {}

    for row in rows:
        key = (row["firm_std"], row["service_std"], row["country_std"])
        ym = row["year_month"]
        bundle = safe_float(row.get("bundle_leverage_index"))
        chart = safe_float(row.get("chart_share_proxy"))

        if bundle is not None:
            previous = bundle_lookup.get(key)
            if previous is None or ym > previous[0]:
                bundle_lookup[key] = (ym, bundle)
        if chart is not None:
            previous = chart_lookup.get(key)
            if previous is None or ym > previous[0]:
                chart_lookup[key] = (ym, chart)

    return bundle_lookup, chart_lookup


def music_event_windows() -> dict[tuple[str, str, str], dict[str, float | str]]:
    narrow_rows = read_csv(EVENT_REGISTRY_NARROW_PATH)
    spotify_event_ids = {
        row["event_id"]
        for row in narrow_rows
        if row["linked_peer_group_id"] == "mus_streaming_paid_core"
    }

    rows = read_csv(EVENT_STUDY_PANEL_PATH)
    deduped: dict[tuple[str, str, str, str, int], dict[str, str]] = {}
    for row in rows:
        if row["event_id"] not in spotify_event_ids:
            continue
        if row["country_std"] != "kr":
            continue
        if row["service_std"] not in {"melon", "flo"}:
            continue
        if row["panel_type"] != "platform_month":
            continue
        if row["control_flag"] != "1":
            continue
        chart = safe_float(row.get("chart_share_proxy"))
        if chart is None:
            continue
        key = (
            row["firm_std"],
            row["service_std"],
            row["country_std"],
            row["year_month"],
            int(row["relative_period"]),
        )
        deduped[key] = row

    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in deduped.values():
        key = (row["firm_std"], row["service_std"], row["country_std"])
        grouped.setdefault(key, []).append(row)

    output: dict[tuple[str, str, str], dict[str, float | str]] = {}
    for key, values in grouped.items():
        values.sort(key=lambda row: int(row["relative_period"]))
        pre = [safe_float(row["chart_share_proxy"]) for row in values if int(row["relative_period"]) < 0]
        post = [safe_float(row["chart_share_proxy"]) for row in values if int(row["relative_period"]) > 0]
        pre = [value for value in pre if value is not None]
        post = [value for value in post if value is not None]
        if len(pre) < 2 or len(post) < 2:
            continue
        pre_mean = mean(pre)
        post_mean = mean(post)
        trough = min(post)
        output[key] = {
            "observed_local_share_event_window_flag": "yes",
            "local_share_erosion_flag": "yes" if post_mean < pre_mean and trough < pre_mean else "no",
            "local_share_change_post_minus_pre": post_mean - pre_mean,
            "local_share_trough_gap_vs_pre": trough - pre_mean,
        }

    return output


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    kr_multihoming_rate = parse_kr_multihoming_rate()
    bundle_lookup, chart_lookup = latest_month_metrics()
    event_window_lookup = music_event_windows()

    output_rows: list[dict[str, str]] = []
    for row in core_rows:
        key = (row["firm_std"], row["service_std"], row["country_std"])
        bundle_period, bundle_value = ("", None)
        if key in bundle_lookup:
            bundle_period, bundle_value = bundle_lookup[key]

        chart_period, chart_value = ("", None)
        if key in chart_lookup:
            chart_period, chart_value = chart_lookup[key]

        event_window = event_window_lookup.get(key, {})

        country_multihoming_rate = None
        country_multihoming_source = ""
        if row["peer_group_id"] == "infra_traffic_ott" and row["country_std"] == "kr":
            country_multihoming_rate = kr_multihoming_rate
            country_multihoming_source = "country_market_usage_registry_kr_direct_summary"

        signals = 0
        if country_multihoming_rate is not None:
            signals += 1
        if bundle_value is not None:
            signals += 1
        if chart_value is not None:
            signals += 1
        if event_window.get("observed_local_share_event_window_flag") == "yes":
            signals += 1

        if row["peer_group_id"] == "mus_label_ip_export":
            status = "not_applicable_content_ip_peer"
            note = "음악 IP 포트폴리오 peer는 이용자 멀티호밍·전환비용보다 콘텐츠 투자·회수 비교가 핵심이라 narrow switching panel에서 out of scope로 둔다."
        elif row["peer_group_id"] == "infra_traffic_ott":
            status = (
                "partial_country_multihoming_only"
                if country_multihoming_rate is not None
                else "no_public_switching_proxy"
            )
            note = "국내 OTT 평균 구독 개수 2.1은 직접 멀티호밍 증거지만 서비스별 switching proxy는 공개자료로 직접 확인되지 않는다."
        elif row["peer_group_id"] == "mus_streaming_paid_core":
            if event_window.get("observed_local_share_event_window_flag") == "yes" and bundle_value is not None and chart_value is not None:
                status = "stronger_music_switching_evidence"
            elif bundle_value is not None or event_window.get("observed_local_share_event_window_flag") == "yes":
                status = "partial_music_switching_evidence"
            else:
                status = "thin_music_switching_evidence"

            if row["firm_std"] == "kakao_ent":
                note = "멜론은 bundle proxy와 직접 local share event window가 함께 남고 실제 erosion episode도 관측된다."
            elif row["firm_std"] == "dreamus":
                note = "FLO는 같은 event window가 존재하지만 post-share erosion이 아니라 개선으로 나타나 switching cost 완화 신호가 일관되지 않는다."
            else:
                note = "Spotify는 직접 bundle proxy는 있으나 한국 내 chart-share 또는 local erosion window가 없어 상대 row보다 switching evidence가 얇다."
        else:
            status = "no_public_switching_proxy"
            note = "현재 공개자료에서 직접 switching proxy를 찾지 못했다."

        output_rows.append(
            {
                "peer_group_id": row["peer_group_id"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "country_std": row["country_std"],
                "analysis_role": row["analysis_role"],
                "country_multihoming_rate": fmt(country_multihoming_rate),
                "country_multihoming_source": country_multihoming_source,
                "bundle_leverage_index_latest": fmt(bundle_value),
                "bundle_reference_period": bundle_period,
                "chart_share_latest": fmt(chart_value),
                "chart_share_latest_period": chart_period,
                "observed_local_share_event_window_flag": str(
                    event_window.get("observed_local_share_event_window_flag", "")
                ),
                "local_share_erosion_flag": str(event_window.get("local_share_erosion_flag", "")),
                "local_share_change_post_minus_pre": fmt(
                    event_window.get("local_share_change_post_minus_pre")  # type: ignore[arg-type]
                ),
                "local_share_trough_gap_vs_pre": fmt(
                    event_window.get("local_share_trough_gap_vs_pre")  # type: ignore[arg-type]
                ),
                "switching_cost_signal_count": str(signals),
                "switching_cost_narrow_status": status,
                "construction_note": note,
            }
        )

    output_rows.sort(
        key=lambda row: (
            row["peer_group_id"],
            row["country_std"],
            row["firm_std"],
            row["service_std"],
        )
    )

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "country_multihoming_rate",
        "country_multihoming_source",
        "bundle_leverage_index_latest",
        "bundle_reference_period",
        "chart_share_latest",
        "chart_share_latest_period",
        "observed_local_share_event_window_flag",
        "local_share_erosion_flag",
        "local_share_change_post_minus_pre",
        "local_share_trough_gap_vs_pre",
        "switching_cost_signal_count",
        "switching_cost_narrow_status",
        "construction_note",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)


if __name__ == "__main__":
    main()
