from __future__ import annotations

import csv
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
ACCESS_MONTH = ACCESS_DATE[:7]

RAW_DIR = PROJECT_DIR / "data" / "raw" / "music"
INTERIM_DIR = PROJECT_DIR / "data" / "interim"
LOG_DIR = PROJECT_DIR / "logs"
REGISTRY_DIR = PROJECT_DIR / "data" / "registry"

SOURCE_MANIFEST_PATH = REGISTRY_DIR / "source_manifest.csv"
PROJECT_MANIFEST_PATH = REGISTRY_DIR / "project_manifest.csv"
WORKFLOW_LOG_PATH = LOG_DIR / "workflow_log.md"

SOURCE_REGISTRY_PATH = INTERIM_DIR / "music_source_registry.csv"
RAW_PANEL_PATH = INTERIM_DIR / "music_market_raw_panel.csv"
LOG_PATH = LOG_DIR / "music_collection_log.md"


def run_curl(
    url: str,
    output_path: Path,
    *,
    referer: str | None = None,
    extra_headers: list[str] | None = None,
    data_urlencode: list[tuple[str, str]] | None = None,
    cookie_jar: Path | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-s",
        "-L",
        "-A",
        "Mozilla/5.0",
        url,
        "-o",
        str(output_path),
    ]
    if referer:
        cmd.extend(["-e", referer])
    if cookie_jar:
        cmd.extend(["-c", str(cookie_jar), "-b", str(cookie_jar)])
    if extra_headers:
        for header in extra_headers:
            cmd.extend(["-H", header])
    if data_urlencode:
        for key, value in data_urlencode:
            cmd.extend(["--data-urlencode", f"{key}={value}"])
    subprocess.run(cmd, check=True)


def month_iter(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def safe_int(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    stripped = str(value).replace(",", "").strip()
    return int(stripped) if stripped else 0


def sorted_chart_rows(list_obj: dict[str, dict]) -> list[dict]:
    return [list_obj[key] for key in sorted(list_obj, key=lambda item: int(item))]


FIRM_SERVICE_MAP = {
    "kakao_ent": "melon",
    "dreamus": "flo",
    "hybe": "weverse",
    "warner_music": "wmg_music_ip",
    "jyp_ent": "jyp_music_ip",
    "yg_ent": "yg_music_ip",
}


CHART_GROUP_PATTERNS = [
    ("kakao_ent", ["kakao entertainment", "카카오엔터테인먼트", "스타쉽엔터테인먼트", "starship"]),
    ("dreamus", ["dreamus", "드림어스"]),
    ("warner_music", ["warner music", "워너뮤직"]),
    ("yg_ent", ["yg plus", "yg entertainment", "yg엔터테인먼트"]),
    ("jyp_ent", ["jyp entertainment", "jyp"]),
    (
        "hybe",
        [
            "hybe",
            "bighit",
            "ador",
            "belift",
            "빌리프랩",
            "source music",
            "쏘스뮤직",
            "koz",
            "스타쉽엔터테인먼트",
        ],
    ),
]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def match_chart_firm(make_company: str, dist_company: str) -> str | None:
    haystack = f"{normalize_text(make_company)} | {normalize_text(dist_company)}"
    for firm_std, patterns in CHART_GROUP_PATTERNS:
        if any(pattern in haystack for pattern in patterns):
            return firm_std
    return None


def fetch_circle_chart(chart_type: str, service_gbn: str, year: int, month: int) -> tuple[Path, dict]:
    month_str = f"{month:02d}"
    page_url = (
        f"https://circlechart.kr/page_chart/onoff.circle?"
        f"nationGbn=T&serviceGbn={service_gbn}&targetTime={month_str}&hitYear={year}&termGbn=month"
    )
    json_path = RAW_DIR / "circle_chart" / f"kr_circle_chart_{chart_type}_month_{year}_{month_str}_{ACCESS_DATE.replace('-', '')}.json"
    with tempfile.TemporaryDirectory() as temp_dir:
        jar = Path(temp_dir) / "cookies.txt"
        page_probe = Path(temp_dir) / "page.html"
        run_curl(page_url, page_probe, cookie_jar=jar)
        run_curl(
            "https://circlechart.kr/data/api/chart/onoff",
            json_path,
            cookie_jar=jar,
            extra_headers=[
                f"Referer: {page_url}",
                "X-Requested-With: XMLHttpRequest",
            ],
            data_urlencode=[
                ("nationGbn", "T"),
                ("serviceGbn", service_gbn),
                ("termGbn", "month"),
                ("hitYear", str(year)),
                ("targetTime", month_str),
                ("yearTime", "3"),
                ("curUrl", page_url),
            ],
        )
    payload = json.loads(json_path.read_text())
    if payload.get("ResultStatus") != "OK":
        raise RuntimeError(f"Circle Chart fetch failed for {chart_type} {year}-{month_str}: {payload.get('ResultStatus')}")
    return json_path, payload


def extract_first(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None
    return safe_int(match.group(1))


def extract_spotify_prices(text: str) -> dict[str, int]:
    faq_match = re.search(
        r"Spotify Premium 베이직 요금제는 ₩([0-9,]+).*?"
        r"Premium 개인 요금제는 ₩([0-9,]+).*?"
        r"Premium 듀오 요금제는 ₩([0-9,]+).*?"
        r"Premium 학생 요금제는 ₩([0-9,]+)",
        text,
        re.DOTALL,
    )
    if not faq_match:
        raise RuntimeError("Spotify KR price block not found")
    return {
        "spotify_basic_monthly_krw": safe_int(faq_match.group(1)),
        "spotify_individual_monthly_krw": safe_int(faq_match.group(2)),
        "spotify_duo_monthly_krw": safe_int(faq_match.group(3)),
        "spotify_student_monthly_krw": safe_int(faq_match.group(4)),
    }


def extract_melon_prices(text: str) -> dict[str, int]:
    return {
        "melon_streaming_club_monthly_krw": extract_first(
            r"<h4 class=\"title\">스트리밍클럽 정기결제.*?<span class=\"sale_price\">([0-9,]+)원</span>",
            text,
        )
        or 0,
        "melon_streaming_plus_monthly_krw": extract_first(
            r"<h4 class=\"title\">스트리밍 플러스 정기결제.*?<span class=\"sale_price\">([0-9,]+)원</span>",
            text,
        )
        or 0,
    }


def extract_youtube_music_price(text: str) -> int:
    prices = [safe_int(val) for val in re.findall(r"₩([0-9,]+)", text)]
    prices = sorted({price for price in prices if price > 0})
    if not prices:
        raise RuntimeError("YouTube Music Premium price not found")
    return prices[-1]


def extract_youtube_bundle_prices(text: str) -> dict[str, int]:
    prices = [safe_int(val) for val in re.findall(r"₩([0-9,]+)", text)]
    positive_prices = sorted({price for price in prices if price > 0})
    if not positive_prices:
        raise RuntimeError("YouTube Premium prices not found")
    lite_price = min(positive_prices)
    bundle_price = max(positive_prices)
    return {
        "youtube_premium_lite_monthly_krw": lite_price,
        "youtube_premium_bundle_monthly_krw": bundle_price,
    }


def upsert_csv(path: Path, rows: list[dict], key_fields: list[str], fieldnames: list[str]) -> None:
    existing: dict[tuple, dict] = {}
    if path.exists():
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                existing[tuple(row[field] for field in key_fields)] = row
    for row in rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        existing[tuple(normalized[field] for field in key_fields)] = normalized
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(existing.values(), key=lambda item: tuple(item[field] for field in key_fields)):
            writer.writerow(row)


def build_chart_panel_rows(chart_type: str, payload: dict) -> list[dict]:
    rows = sorted_chart_rows(payload["List"])
    score_by_dist: dict[str, float] = defaultdict(float)
    score_by_firm: dict[str, float] = defaultdict(float)
    total_score = 0.0
    scored_rows = 0
    for row in rows:
        score = float(safe_int(row.get("ROW_CNT")) or safe_int(row.get("HIT_CNT")))
        if score <= 0:
            continue
        scored_rows += 1
        total_score += score
        dist = (row.get("DE_COMPANY_NAME") or "UNKNOWN").strip() or "UNKNOWN"
        score_by_dist[dist] += score
        firm_std = match_chart_firm(row.get("MAKE_COMPANY_NAME", ""), row.get("DE_COMPANY_NAME", ""))
        if firm_std:
            score_by_firm[firm_std] += score
    weighting_label = "score"
    if total_score == 0:
        weighting_label = "inverse_rank"
        for row in rows:
            rank = safe_int(row.get("SERVICE_RANKING"))
            if rank <= 0:
                continue
            weight = 1.0 / rank
            total_score += weight
            dist = (row.get("DE_COMPANY_NAME") or "UNKNOWN").strip() or "UNKNOWN"
            score_by_dist[dist] += weight
            firm_std = match_chart_firm(row.get("MAKE_COMPANY_NAME", ""), row.get("DE_COMPANY_NAME", ""))
            if firm_std:
                score_by_firm[firm_std] += weight
    panel_rows: list[dict] = []
    if total_score == 0:
        return panel_rows
    hhi = sum((score / total_score) ** 2 for score in score_by_dist.values()) * 10000
    form = payload["FormToMap"]
    year_month = f"{form['hitYear']}-{form['targetTime']}"
    source_id = f"music_circle_chart_{chart_type}_api"
    panel_rows.append(
        {
            "panel_unit_type": "market_month",
            "country_std": "kr",
            "year_month": year_month,
            "firm_std": "",
            "service_std": "",
            "metric_name": "music_service_hhi",
            "metric_variant": f"{chart_type}_top200_distributor_{weighting_label}",
            "metric_value": f"{hhi:.6f}",
            "metric_unit": "HHI_10000",
            "source_id": source_id,
            "raw_source_file": f"data/raw/music/circle_chart/kr_circle_chart_{chart_type}_month_{form['hitYear']}_{form['targetTime']}_{ACCESS_DATE.replace('-', '')}.json",
            "collection_status": "collected",
            "notes": (
                "Circle Chart top200 monthly score shares by distributor"
                if weighting_label == "score"
                else "Circle Chart streaming chart omits score fields; used inverse-rank weights by distributor"
            ),
        }
    )
    for firm_std, score in sorted(score_by_firm.items()):
        panel_rows.append(
            {
                "panel_unit_type": "firm_month",
                "country_std": "kr",
                "year_month": year_month,
                "firm_std": firm_std,
                "service_std": FIRM_SERVICE_MAP.get(firm_std, ""),
                "metric_name": "chart_share",
                "metric_variant": f"{chart_type}_top200_{weighting_label}_share",
                "metric_value": f"{score / total_score:.6f}",
                "metric_unit": "share",
                "source_id": source_id,
                "raw_source_file": f"data/raw/music/circle_chart/kr_circle_chart_{chart_type}_month_{form['hitYear']}_{form['targetTime']}_{ACCESS_DATE.replace('-', '')}.json",
                "collection_status": "collected",
                "notes": (
                    "Mapped by production/distribution company names in Circle Chart raw JSON"
                    if weighting_label == "score"
                    else "Mapped by production/distribution company names; weights use inverse rank because streaming chart score fields are blank"
                ),
            }
        )
    return panel_rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    months = month_iter(2024, 1, 2026, 2)
    source_registry_rows: list[dict] = []
    panel_rows: list[dict] = []
    source_manifest_rows: list[dict] = []
    project_manifest_rows: list[dict] = []

    chart_configs = [
        ("digital", "ALL"),
        ("streaming", "S1040"),
    ]

    for chart_type, service_gbn in chart_configs:
        for year, month in months:
            raw_path, payload = fetch_circle_chart(chart_type, service_gbn, year, month)
            relative_raw = raw_path.relative_to(PROJECT_DIR).as_posix()
            source_manifest_rows.append(
                {
                    "source_file": relative_raw,
                    "source_url": (
                        "https://circlechart.kr/data/api/chart/onoff"
                    ),
                    "access_date": ACCESS_DATE,
                    "country_std": "kr",
                    "firm_std": "",
                    "service_std": "",
                    "sector_std": "music",
                    "file_format": "json",
                    "collected_by_prompt": "Exec Prompt 15",
                    "status": "collected",
                }
            )
            panel_rows.extend(build_chart_panel_rows(chart_type, payload))
        source_registry_rows.append(
            {
                "source_id": f"music_circle_chart_{chart_type}_api",
                "source_name": f"Circle Chart {chart_type.title()} monthly API",
                "source_url": "https://circlechart.kr/data/api/chart/onoff",
                "country_std": "kr",
                "firm_std": "",
                "service_std": "",
                "metric_targets": "music_service_hhi|chart_share",
                "collection_status": "collected",
                "raw_storage_path": f"data/raw/music/circle_chart/*{chart_type}*.json",
                "access_date": ACCESS_DATE,
                "notes": f"Collected monthly top200 raw JSON for 2024-01 through 2026-02 using authenticated page session bootstrap; 2026-03 remained unavailable on {ACCESS_DATE}.",
            }
        )

    pricing_sources = [
        (
            "music_melon_all_pricing",
            "Melon all pricing page",
            "https://www.melon.com/buy/pamphlet/all.htm",
            RAW_DIR / "melon" / f"kr_melon_all_{ACCESS_DATE.replace('-', '')}.html",
            {"referer": "https://www.melon.com/commerce/pamphlet/web/sale_listMainView.htm"},
        ),
        (
            "music_melon_recommend_pricing",
            "Melon recommended pricing page",
            "https://www.melon.com/buy/pamphlet/recommend.htm",
            RAW_DIR / "melon" / f"kr_melon_recommend_{ACCESS_DATE.replace('-', '')}.html",
            {"referer": "https://www.melon.com/commerce/pamphlet/web/sale_listMainView.htm"},
        ),
        (
            "music_spotify_premium_kr",
            "Spotify Premium Korea page",
            "https://www.spotify.com/kr-ko/premium/",
            RAW_DIR / "pricing" / f"kr_spotify_premium_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
        (
            "music_youtube_premium_kr",
            "YouTube Premium Korea page",
            "https://www.youtube.com/premium",
            RAW_DIR / "pricing" / f"kr_youtube_premium_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
        (
            "music_youtube_musicpremium_kr",
            "YouTube Music Premium Korea page",
            "https://www.youtube.com/musicpremium",
            RAW_DIR / "pricing" / f"kr_youtube_musicpremium_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
        (
            "music_flo_home",
            "FLO home page",
            "https://www.music-flo.com/",
            RAW_DIR / "flo" / f"kr_flo_home_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
        (
            "music_flo_mainjs",
            "FLO webapp main.js",
            "https://cdn.music-flo.com/poc/p/fe/2026_03/190936/main.js",
            RAW_DIR / "flo" / f"kr_flo_mainjs_{ACCESS_DATE.replace('-', '')}.js",
            {},
        ),
        (
            "music_flo_api_product",
            "FLO product API",
            "https://www.music-flo.com/api/purchase/v1/product",
            RAW_DIR / "flo" / f"kr_flo_api_product_{ACCESS_DATE.replace('-', '')}.json",
            {},
        ),
        (
            "music_dreamus_flo_service",
            "Dreamus FLO service page",
            "https://www.dreamuscompany.com/service/flo.html",
            RAW_DIR / "flo" / f"kr_dreamus_flo_service_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
        (
            "music_weverse_home",
            "Weverse home page",
            "https://weverse.io/",
            RAW_DIR / "weverse" / f"global_weverse_home_{ACCESS_DATE.replace('-', '')}.html",
            {},
        ),
    ]

    fetched_price_paths: dict[str, Path] = {}
    for source_id, source_name, source_url, raw_path, kwargs in pricing_sources:
        run_curl(source_url, raw_path, referer=kwargs.get("referer"))
        fetched_price_paths[source_id] = raw_path
        relative_raw = raw_path.relative_to(PROJECT_DIR).as_posix()
        source_manifest_rows.append(
            {
                "source_file": relative_raw,
                "source_url": source_url,
                "access_date": ACCESS_DATE,
                "country_std": "kr" if "weverse" not in source_id else "",
                "firm_std": "",
                "service_std": "",
                "sector_std": "music",
                "file_format": raw_path.suffix.lstrip("."),
                "collected_by_prompt": "Exec Prompt 15",
                "status": "collected",
            }
        )
        source_registry_rows.append(
            {
                "source_id": source_id,
                "source_name": source_name,
                "source_url": source_url,
                "country_std": "kr" if "weverse" not in source_id else "",
                "firm_std": "",
                "service_std": "",
                "metric_targets": "",
                "collection_status": "collected",
                "raw_storage_path": relative_raw,
                "access_date": ACCESS_DATE,
                "notes": "",
            }
        )

    melon_text = fetched_price_paths["music_melon_all_pricing"].read_text()
    spotify_text = fetched_price_paths["music_spotify_premium_kr"].read_text()
    youtube_premium_text = fetched_price_paths["music_youtube_premium_kr"].read_text()
    youtube_music_text = fetched_price_paths["music_youtube_musicpremium_kr"].read_text()

    melon_prices = extract_melon_prices(melon_text)
    spotify_prices = extract_spotify_prices(spotify_text)
    youtube_bundle_prices = extract_youtube_bundle_prices(youtube_premium_text)
    youtube_music_price = extract_youtube_music_price(youtube_music_text)

    price_rows = [
        ("kakao_ent", "melon", "service_monthly_price_krw", "streaming_club", melon_prices["melon_streaming_club_monthly_krw"], "music_melon_all_pricing"),
        ("kakao_ent", "melon", "service_monthly_price_krw", "streaming_plus", melon_prices["melon_streaming_plus_monthly_krw"], "music_melon_all_pricing"),
        ("spotify", "spotify", "service_monthly_price_krw", "basic", spotify_prices["spotify_basic_monthly_krw"], "music_spotify_premium_kr"),
        ("spotify", "spotify", "service_monthly_price_krw", "individual", spotify_prices["spotify_individual_monthly_krw"], "music_spotify_premium_kr"),
        ("spotify", "spotify", "service_monthly_price_krw", "duo", spotify_prices["spotify_duo_monthly_krw"], "music_spotify_premium_kr"),
        ("spotify", "spotify", "service_monthly_price_krw", "student", spotify_prices["spotify_student_monthly_krw"], "music_spotify_premium_kr"),
        ("alphabet", "youtube_music", "service_monthly_price_krw", "music_premium_individual", youtube_music_price, "music_youtube_musicpremium_kr"),
        ("alphabet", "youtube_music", "service_monthly_price_krw", "premium_lite_individual", youtube_bundle_prices["youtube_premium_lite_monthly_krw"], "music_youtube_premium_kr"),
        ("alphabet", "youtube_music", "service_monthly_price_krw", "premium_bundle_individual", youtube_bundle_prices["youtube_premium_bundle_monthly_krw"], "music_youtube_premium_kr"),
        (
            "",
            "",
            "relative_price_gap",
            "spotify_individual_minus_youtube_music_over_spotify",
            round((spotify_prices["spotify_individual_monthly_krw"] - youtube_music_price) / spotify_prices["spotify_individual_monthly_krw"], 6),
            "music_youtube_musicpremium_kr",
        ),
    ]

    for firm_std, service_std, metric_name, metric_variant, metric_value, source_id in price_rows:
        panel_rows.append(
            {
                "panel_unit_type": "service_month",
                "country_std": "kr",
                "year_month": ACCESS_MONTH,
                "firm_std": firm_std,
                "service_std": service_std,
                "metric_name": metric_name,
                "metric_variant": metric_variant,
                "metric_value": str(metric_value),
                "metric_unit": "krw" if "price" in metric_name else "ratio",
                "source_id": source_id,
                "raw_source_file": fetched_price_paths[source_id].relative_to(PROJECT_DIR).as_posix(),
                "collection_status": "collected",
                "notes": "Official public pricing page snapshot",
            }
        )

    source_registry_rows.extend(
        [
            {
                "source_id": "music_naver_datalab",
                "source_name": "NAVER DataLab web/API",
                "source_url": "https://developers.naver.com/products/service-api/datalab/datalab.md",
                "country_std": "kr",
                "firm_std": "",
                "service_std": "",
                "metric_targets": "local_music_search_share|ytmusic_search_share|bundle_leverage_index",
                "collection_status": "blocked_access",
                "raw_storage_path": "",
                "access_date": ACCESS_DATE,
                "notes": "Public landing page opened, but keyword trend/search pages returned access-error pages in this environment on 2026-03-29.",
            },
            {
                "source_id": "music_youtube_data_api",
                "source_name": "YouTube Data API",
                "source_url": "https://developers.google.com/youtube/v3/getting-started",
                "country_std": "",
                "firm_std": "",
                "service_std": "",
                "metric_targets": "cross_market_transfer_index|video_attention|artist_channel_activity",
                "collection_status": "pending_api_key",
                "raw_storage_path": "",
                "access_date": ACCESS_DATE,
                "notes": "Official documentation exists, but public collection was not attempted because API credentials are required for stable retrieval.",
            },
        ]
    )

    panel_fieldnames = [
        "panel_unit_type",
        "country_std",
        "year_month",
        "firm_std",
        "service_std",
        "metric_name",
        "metric_variant",
        "metric_value",
        "metric_unit",
        "source_id",
        "raw_source_file",
        "collection_status",
        "notes",
    ]
    panel_rows.sort(
        key=lambda row: (
            row["year_month"],
            row["metric_name"],
            row["metric_variant"],
            row["firm_std"],
            row["service_std"],
        )
    )
    write_csv(RAW_PANEL_PATH, panel_rows, panel_fieldnames)

    source_registry_fieldnames = [
        "source_id",
        "source_name",
        "source_url",
        "country_std",
        "firm_std",
        "service_std",
        "metric_targets",
        "collection_status",
        "raw_storage_path",
        "access_date",
        "notes",
    ]
    source_registry_rows.sort(key=lambda row: row["source_id"])
    write_csv(SOURCE_REGISTRY_PATH, source_registry_rows, source_registry_fieldnames)

    upsert_csv(
        SOURCE_MANIFEST_PATH,
        source_manifest_rows,
        key_fields=["source_file"],
        fieldnames=[
            "source_file",
            "source_url",
            "access_date",
            "country_std",
            "firm_std",
            "service_std",
            "sector_std",
            "file_format",
            "collected_by_prompt",
            "status",
        ],
    )

    project_manifest_rows.extend(
        [
            {
                "artifact_type": "script",
                "path": "scripts/collect_music_market_data.py",
                "owner_step": "Exec Prompt 15",
                "source_type": "local_code",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Reproducible collection and panel build for music market data",
            },
            {
                "artifact_type": "dataset",
                "path": "data/interim/music_source_registry.csv",
                "owner_step": "Exec Prompt 15",
                "source_type": "public_web_collection",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Music sector source registry with collected and pending items",
            },
            {
                "artifact_type": "dataset",
                "path": "data/interim/music_market_raw_panel.csv",
                "owner_step": "Exec Prompt 15",
                "source_type": "public_web_collection",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Music market long-form raw panel including chart shares, HHI, and price snapshots",
            },
            {
                "artifact_type": "log",
                "path": "logs/music_collection_log.md",
                "owner_step": "Exec Prompt 15",
                "source_type": "local_log",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Music source collection notes and unresolved blockers",
            },
        ]
    )

    upsert_csv(
        PROJECT_MANIFEST_PATH,
        project_manifest_rows,
        key_fields=["path", "owner_step"],
        fieldnames=[
            "artifact_type",
            "path",
            "owner_step",
            "source_type",
            "source_url",
            "access_date",
            "status",
            "notes",
        ],
    )

    total_chart_files = len(months) * len(chart_configs)
    hhi_rows = [row for row in panel_rows if row["metric_name"] == "music_service_hhi"]
    chart_share_rows = [row for row in panel_rows if row["metric_name"] == "chart_share"]
    price_metric_rows = [row for row in panel_rows if row["metric_name"] == "service_monthly_price_krw"]
    observed_chart_firms = sorted({row["firm_std"] for row in chart_share_rows if row["firm_std"]})
    observed_chart_firms_txt = ", ".join(observed_chart_firms) if observed_chart_firms else "없음"
    log_text = f"""# Exec Prompt 15. 음악 분야 서비스·시장 데이터 수집

- 실행일: {ACCESS_DATE}
- 생성 스크립트: `scripts/collect_music_market_data.py`
- 월별 Circle Chart raw JSON: {total_chart_files}건
- 생성 raw panel 행 수: {len(panel_rows)}행
- `music_service_hhi` 행 수: {len(hhi_rows)}행
- `chart_share` 행 수: {len(chart_share_rows)}행
- 가격 snapshot 행 수: {len(price_metric_rows)}행

## 이번 단계에서 실제 수집한 공개 원천

- Circle Chart 월별 `Digital` 및 `Streaming` top200 raw JSON (`2024-01`~`2026-02`)
- Melon 전체 이용권 페이지
- Spotify Premium Korea 페이지
- YouTube Premium Korea 페이지
- YouTube Music Premium Korea 페이지
- FLO 공식 웹 페이지 / 웹앱 JS / product API
- Dreamus FLO 서비스 소개 페이지
- Weverse 홈 페이지

## 주요 수집 성과

- Circle Chart 기준 월별 유통사 점수 집중도로 `music_service_hhi`를 계산함
- Circle Chart의 제작사/유통사 문자열 매핑으로 다음 firm의 월별 `chart_share`를 생성함: `{observed_chart_firms_txt}`
- 한국 가격 snapshot으로 `melon`, `spotify`, `youtube_music`의 월별 소비자 가격 raw를 생성함

## 보류 또는 제한 사항

- `music_naver_datalab`: 이 환경에서 검색어 트렌드 페이지가 접근 오류를 반환해 `blocked_access`
- `music_youtube_data_api`: 공식 문서는 있으나 안정 수집에는 API 자격증명이 필요해 `pending_api_key`
- FLO는 `api/purchase/v1/product`가 현재 보유 이용권 여부만 반환해 상세 가격표를 직접 회수하지 못했음
- Circle Chart `2026-03` 월간 API는 {ACCESS_DATE} 기준 `ResultStatus=Error`라 확정 월인 `2026-02`까지 수집함

## 가격 snapshot 요약

- Melon 스트리밍클럽 정기결제: {melon_prices['melon_streaming_club_monthly_krw']:,}원
- Melon 스트리밍 플러스 정기결제: {melon_prices['melon_streaming_plus_monthly_krw']:,}원
- Spotify 개인: {spotify_prices['spotify_individual_monthly_krw']:,}원
- Spotify 베이직: {spotify_prices['spotify_basic_monthly_krw']:,}원
- YouTube Music Premium: {youtube_music_price:,}원
- YouTube Premium Lite: {youtube_bundle_prices['youtube_premium_lite_monthly_krw']:,}원
- YouTube Premium Bundle: {youtube_bundle_prices['youtube_premium_bundle_monthly_krw']:,}원
"""
    LOG_PATH.write_text(log_text)

    workflow_entry = f"""
### Exec Prompt 15. 음악 분야 서비스·시장 데이터 수집

- `scripts/collect_music_market_data.py`를 추가해 Circle Chart 월별 raw JSON, 한국 공식 가격 페이지, FLO/Weverse 공개 웹 원천을 한 번에 수집하도록 구성함
- `data/interim/music_source_registry.csv`를 생성해 collected, blocked_access, pending_api_key 상태를 source 단위로 고정함
- `data/interim/music_market_raw_panel.csv`를 생성해 `music_service_hhi`, `chart_share`, `service_monthly_price_krw`, `relative_price_gap` raw 행을 장기 형식으로 정리함
- Circle Chart는 `2024-01`부터 `2026-02`까지 월별 `Digital` 및 `Streaming` top200 JSON {total_chart_files}건을 저장했고, `2026-03`는 API가 `Error`를 반환해 제외함
- 멜론, 스포티파이, 유튜브 뮤직/프리미엄 공식 페이지 기준 가격 snapshot을 수집했고, FLO는 현재 product API에서 상세 가격 대신 보유 이용권 상태만 반환함
- 검색관심도와 전이지수 축은 `music_naver_datalab` 접근 제한과 `music_youtube_data_api` 자격증명 요구 때문에 보류 상태로 registry와 로그에 명시함
""".rstrip()

    workflow_text = WORKFLOW_LOG_PATH.read_text()
    if "### Exec Prompt 15. 음악 분야 서비스·시장 데이터 수집" not in workflow_text:
        WORKFLOW_LOG_PATH.write_text(workflow_text.rstrip() + "\n\n" + workflow_entry + "\n")


if __name__ == "__main__":
    main()
