from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

EVENT_REGISTRY_PATH = ROOT / "data/registry/event_registry.csv"
MATCHED_PEER_REGISTRY_PATH = ROOT / "data/processed/claim_strengthening/matched_peer_registry.csv"
COMPARABLE_CELL_FILTER_PATH = ROOT / "data/processed/claim_strengthening/comparable_country_cell_filter.csv"
CORE_SAMPLE_PATH = (
    ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)

OUTPUT_PATH = ROOT / "data/registry/claim_strengthening/event_registry_narrow.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/event_registry_narrow_log.md"


SERVICE_RULES = {
    "spotify": {
        "linked_peer_group_id": "mus_streaming_paid_core",
        "narrow_event_type": "국내 서비스와 직접 겹치는 기능 추가",
        "relevance_note": "Spotify의 Lossless 추가는 한국 유료 음악 스트리밍과 직접 겹치는 품질 기능을 확장하는 사건이다.",
    },
    "webtoon": {
        "linked_peer_group_id": "webtoon_serial_platform",
        "narrow_event_type": "인접시장 진입",
        "relevance_note": "WEBTOON Video Episodes는 글로벌 웹툰 플랫폼이 영상 소비로 인접 진입하는 사건으로 attention transfer 분석에 직접 연결된다.",
    },
    "youtube": {
        "linked_peer_group_id": "infra_traffic_video",
        "narrow_event_type": "요금 인하 또는 Lite 출시",
        "relevance_note": "YouTube Premium Lite는 글로벌 동영상 플랫폼의 저가 진입 확대 사건으로 네트워크 및 attention burden 강화 논리에 직접 연결된다.",
    },
}

EXCLUDE_REASONS = {
    "naver_webtoon_cuts_kr_20250901": "국내 incumbent의 축소/조정 사건이라 글로벌 빅테크 확장 사건에 해당하지 않아 narrow v1에서 제외",
    "piccoma_kuji_jp_20251203": "한국계 서비스의 일본 확장 사건이라 역차별 강화용 글로벌 peer shock으로 보기 어려워 제외",
    "webtoon_video_episodes_uk_20250818": "동일 이벤트군이지만 sample_strength가 medium이고 regression 권장 no라 narrow v1의 direct evidence 세트에서 제외",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_peer_lookup(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    korean_firms: dict[str, list[str]] = defaultdict(list)
    priority_tier: dict[str, str] = {}

    for row in rows:
        group = row["peer_group_id"]
        korean_firm = row["korean_firm_std"]
        if korean_firm not in korean_firms[group]:
            korean_firms[group].append(korean_firm)
        priority_tier[group] = row["priority_tier"]

    lookup: dict[str, dict[str, str]] = {}
    for service_std, rule in SERVICE_RULES.items():
        group = rule["linked_peer_group_id"]
        lookup[service_std] = {
            "linked_peer_group_id": group,
            "priority_tier": priority_tier[group],
            "target_korean_firm_list": "|".join(sorted(korean_firms[group])),
        }
    return lookup


def build_comparable_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    return {
        (row["peer_group_id"], row["country_std"]): row["cell_comparable_flag"] for row in rows
    }


def build_core_peer_group_set(rows: list[dict[str, str]]) -> set[str]:
    return {
        row["peer_group_id"]
        for row in rows
        if row["include_flag"] == "yes" and row["analysis_role"] == "global_peer"
    } | {
        row["peer_group_id"]
        for row in rows
        if row["include_flag"] == "yes" and row["analysis_role"] == "korean_anchor"
    }


def classify_use(core_link: str, comparable_flag: str) -> str:
    if core_link == "yes" and comparable_flag == "yes":
        return "direct_matched_event_candidate"
    if core_link == "yes":
        return "supportive_core_event_reference"
    return "supportive_noncore_event_reference"


def main() -> None:
    event_rows = read_csv(EVENT_REGISTRY_PATH)
    peer_rows = read_csv(MATCHED_PEER_REGISTRY_PATH)
    comparable_rows = read_csv(COMPARABLE_CELL_FILTER_PATH)
    core_rows = read_csv(CORE_SAMPLE_PATH)

    peer_lookup = build_peer_lookup(peer_rows)
    comparable_lookup = build_comparable_lookup(comparable_rows)
    core_peer_groups = build_core_peer_group_set(core_rows)

    output_rows: list[dict[str, str]] = []
    excluded_rows: list[tuple[str, str]] = []

    for row in event_rows:
        service_std = row["service_std"]
        if service_std not in SERVICE_RULES:
            excluded_rows.append((row["event_id"], EXCLUDE_REASONS.get(row["event_id"], "글로벌 peer 사건 유형에 해당하지 않아 제외")))
            continue

        if row["recommended_for_regression_flag"] != "yes":
            excluded_rows.append((row["event_id"], EXCLUDE_REASONS.get(row["event_id"], "regression 권장 no라 narrow v1에서 제외")))
            continue

        rule = SERVICE_RULES[service_std]
        peer_meta = peer_lookup[service_std]
        peer_group_id = peer_meta["linked_peer_group_id"]
        country_comparable_flag = comparable_lookup.get((peer_group_id, row["country_std"]), "no")
        core_sample_link_flag = "yes" if peer_group_id in core_peer_groups else "no"

        output_rows.append(
            {
                "event_id": row["event_id"],
                "event_label": row["event_label"],
                "sector_std": row["sector_std"],
                "country_std": row["country_std"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "event_date": row["event_date"],
                "original_event_type": row["event_type"],
                "narrow_event_type": rule["narrow_event_type"],
                "linked_peer_group_id": peer_group_id,
                "target_korean_firm_list": peer_meta["target_korean_firm_list"],
                "peer_priority_tier": peer_meta["priority_tier"],
                "core_sample_link_flag": core_sample_link_flag,
                "country_comparable_flag": country_comparable_flag,
                "sample_strength": row["sample_strength"],
                "recommended_for_regression_flag": row["recommended_for_regression_flag"],
                "downstream_use": classify_use(core_sample_link_flag, country_comparable_flag),
                "direct_relevance_note": rule["relevance_note"],
                "source_url": row["source_url"],
                "notes": row["notes"],
            }
        )

    output_rows.sort(
        key=lambda r: (
            r["linked_peer_group_id"],
            r["event_date"],
            r["country_std"],
            r["event_id"],
        )
    )

    fieldnames = [
        "event_id",
        "event_label",
        "sector_std",
        "country_std",
        "firm_std",
        "service_std",
        "event_date",
        "original_event_type",
        "narrow_event_type",
        "linked_peer_group_id",
        "target_korean_firm_list",
        "peer_priority_tier",
        "core_sample_link_flag",
        "country_comparable_flag",
        "sample_strength",
        "recommended_for_regression_flag",
        "downstream_use",
        "direct_relevance_note",
        "source_url",
        "notes",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    included_type_counts = Counter(row["narrow_event_type"] for row in output_rows)
    linked_group_counts = Counter(row["linked_peer_group_id"] for row in output_rows)
    core_link_counts = Counter(row["core_sample_link_flag"] for row in output_rows)
    comparable_counts = Counter(row["country_comparable_flag"] for row in output_rows)

    lines = [
        "# Event Registry Narrow Log",
        "",
        "## Summary",
        "",
        f"- base event registry rows: `{len(event_rows)}`",
        f"- narrow registry rows: `{len(output_rows)}`",
        f"- excluded rows: `{len(excluded_rows)}`",
        f"- included by narrow event type: `{dict(sorted(included_type_counts.items()))}`",
        f"- included by linked peer group: `{dict(sorted(linked_group_counts.items()))}`",
        f"- core sample link flag: `{dict(sorted(core_link_counts.items()))}`",
        f"- country comparable flag: `{dict(sorted(comparable_counts.items()))}`",
        "",
        "## Inclusion Rule",
        "",
        "- 글로벌 peer 사건만 유지함: `spotify`, `webtoon_ent`, `alphabet` 계열 사건",
        "- `recommended_for_regression_flag = yes`를 만족하는 row만 narrow v1에 남김",
        "- 사건 유형은 프롬프트 우선 유형에 맞춰 `Lite/요금 인하`, `인접시장 진입`, `직접 겹치는 기능 추가`로 재분류함",
        "",
        "## Excluded Rows",
        "",
    ]

    for event_id, reason in excluded_rows:
        lines.append(f"- `{event_id}`: {reason}")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- 현재 narrow registry는 글로벌 peer 확장 사건 중에서도 회귀 권장 신호가 있는 row만 남긴 보수적 세트다.",
            "- `spotify_lossless_*`는 core streaming peer에 직접 연결되지만 동일 국가 comparable cell은 아직 없어 supportive core event reference로 분류된다.",
            "- `webtoon_video_episodes_*`와 `youtube_premium_lite_*`는 시장 간 전이와 점유율 잠식 에피소드 분석에는 유용하지만 core sample 직접 비교로는 아직 제한적이다.",
        ]
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
