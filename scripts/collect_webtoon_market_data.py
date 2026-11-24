from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import defaultdict
from datetime import date
from html import unescape
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
ACCESS_DATE_TAG = ACCESS_DATE.replace("-", "")
YEAR_QUARTER = f"{ACCESS_DATE[:4]}Q{((int(ACCESS_DATE[5:7]) - 1) // 3) + 1}"

RAW_DIR = PROJECT_DIR / "data" / "raw" / "webtoon"
INTERIM_DIR = PROJECT_DIR / "data" / "interim"
LOG_DIR = PROJECT_DIR / "logs"
REGISTRY_DIR = PROJECT_DIR / "data" / "registry"

SOURCE_MANIFEST_PATH = REGISTRY_DIR / "source_manifest.csv"
PROJECT_MANIFEST_PATH = REGISTRY_DIR / "project_manifest.csv"
WORKFLOW_LOG_PATH = LOG_DIR / "workflow_log.md"

SOURCE_REGISTRY_PATH = INTERIM_DIR / "webtoon_source_registry.csv"
TITLE_PANEL_PATH = INTERIM_DIR / "webtoon_title_raw_panel.csv"
PLATFORM_PANEL_PATH = INTERIM_DIR / "webtoon_platform_raw_panel.csv"
LOG_PATH = LOG_DIR / "webtoon_collection_log.md"

PROMPT_LABEL = "Exec Prompt 16"

HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
HIRAGANA_RE = re.compile(r"[\u3040-\u309f]")
KATAKANA_RE = re.compile(r"[\u30a0-\u30ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MULTISPACE_RE = re.compile(r"\s+")

SERVICE_FIRM_MAP = {
    "bookwalker": "kadokawa",
    "kakao_page": "kakao_ent",
    "lezhin_comics": "kidari_studio",
    "naver_webtoon": "naver",
    "piccoma": "kakao_piccoma",
    "ridi": "ridi",
    "webtoon": "webtoon_ent",
}


def clean_text(value: str) -> str:
    text = HTML_TAG_RE.sub(" ", unescape(value or ""))
    return MULTISPACE_RE.sub(" ", text).strip()


def run_curl(url: str, output_path: Path, *, referer: str | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-s",
        "-L",
        "-k",
        "-A",
        "Mozilla/5.0",
        url,
        "-o",
        str(output_path),
    ]
    if referer:
        cmd.extend(["-e", referer])
    subprocess.run(cmd, check=True)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def upsert_csv(path: Path, rows: list[dict], key_fields: list[str], fieldnames: list[str]) -> None:
    existing: dict[tuple[str, ...], dict[str, str]] = {}
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


def extract_series_id_from_scheme(scheme: str) -> str:
    match = re.search(r"series_id=(\d+)", scheme or "")
    return match.group(1) if match else ""


def infer_origin_proxy(country_std: str, title_name: str, author_name: str, *, allow_proxy: bool) -> tuple[str, str, str]:
    if not allow_proxy:
        return "", "", "proxy_not_used_for_this_storefront"
    combined = f"{title_name} {author_name}".strip()
    has_hangul = bool(HANGUL_RE.search(combined))
    has_japanese = bool(HIRAGANA_RE.search(combined) or KATAKANA_RE.search(combined))
    has_latin = bool(LATIN_RE.search(combined))
    has_cjk = bool(CJK_RE.search(combined))

    if country_std == "kr":
        if has_hangul:
            return "1", "0", "hangul_title_or_author"
        if has_japanese or has_cjk:
            return "0", "1", "non_korean_cjk_script"
        if has_latin:
            return "0", "1", "latin_only_non_kr_proxy"
        return "", "", "insufficient_script_signal"

    if country_std == "jp":
        if has_hangul:
            return "0", "1", "hangul_detected_on_jp_store"
        if has_japanese:
            return "1", "0", "japanese_script_detected"
        if has_cjk and not has_latin:
            return "1", "0", "cjk_title_without_hangul"
        if has_latin:
            return "", "1", "latin_only_jp_store_proxy"
        return "", "", "insufficient_script_signal"

    return "", "", "proxy_not_defined_for_country"


def make_title_row(
    *,
    title_std: str,
    title_id_raw: str,
    title_name: str,
    title_url: str,
    author_name: str,
    genre_text: str,
    format_type: str,
    service_std: str,
    country_std: str,
    source_id: str,
    source_page_type: str,
    section_name: str,
    position: int | str,
    raw_source_file: str,
    notes: str,
    allow_proxy: bool,
) -> dict:
    local_proxy, translated_proxy, proxy_basis = infer_origin_proxy(
        country_std,
        title_name,
        author_name,
        allow_proxy=allow_proxy,
    )
    return {
        "title_std": title_std,
        "title_id_raw": title_id_raw,
        "title_name": clean_text(title_name),
        "title_url": title_url,
        "author_name": clean_text(author_name),
        "genre_text": clean_text(genre_text),
        "format_type": format_type,
        "firm_std": SERVICE_FIRM_MAP.get(service_std, ""),
        "service_std": service_std,
        "country_std": country_std,
        "year_quarter": YEAR_QUARTER,
        "access_date": ACCESS_DATE,
        "source_id": source_id,
        "source_page_type": source_page_type,
        "section_name": clean_text(section_name),
        "position": str(position),
        "local_ip_proxy": local_proxy,
        "translated_proxy": translated_proxy,
        "proxy_basis": proxy_basis,
        "raw_source_file": raw_source_file,
        "collection_status": "collected",
        "notes": notes,
    }


def parse_webtoon_titles(html: str, raw_source_file: str, *, source_id: str, section_name: str) -> list[dict]:
    pattern = re.compile(
        r'<a href="([^"]+)"[^>]*data-title-no="(\d+)"[^>]*?(?:data-genre="([^"]*)")?[^>]*>'
        r".*?<strong class=\"title\">(.*?)</strong>"
        r"(?:.*?<div class=\"view_count\">(.*?)</div>)?",
        re.S,
    )
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for position, match in enumerate(pattern.finditer(html), start=1):
        href, title_no, genre_text, title_name, view_count = match.groups()
        key = ("webtoon", title_no)
        if key in seen:
            continue
        seen.add(key)
        notes = "WEBTOON EN ranking/originals HTML card"
        if view_count:
            notes += f"; view_count={clean_text(view_count)}"
        rows.append(
            make_title_row(
                title_std=f"webtoon_{title_no}",
                title_id_raw=title_no,
                title_name=title_name,
                title_url=href if href.startswith("http") else f"https://www.webtoons.com{href}",
                author_name="",
                genre_text=genre_text or "",
                format_type="webtoon",
                service_std="webtoon",
                country_std="us",
                source_id=source_id,
                source_page_type="html_ranking_card",
                section_name=section_name,
                position=position,
                raw_source_file=raw_source_file,
                notes=notes,
                allow_proxy=False,
            )
        )
    return rows


def parse_kakaopage_titles(html: str, raw_source_file: str) -> list[dict]:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not match:
        return []
    data = json.loads(match.group(1))
    card_views: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "CardView" and node.get("title") and node.get("scheme"):
                card_views.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    rows: list[dict] = []
    seen: set[str] = set()
    position = 0
    for card in card_views:
        category = card.get("categoryType") or ""
        if category not in {"Webtoon", "Webnovel"}:
            continue
        series_id = extract_series_id_from_scheme(card.get("scheme", ""))
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)
        position += 1
        event_meta = ((card.get("eventLog") or {}).get("eventMeta") or {})
        subtype = event_meta.get("subcategory", "")
        rows.append(
            make_title_row(
                title_std=f"kakaopage_{series_id}",
                title_id_raw=series_id,
                title_name=card.get("title", ""),
                title_url=f"https://page.kakao.com/content/{series_id}",
                author_name="",
                genre_text=subtype,
                format_type=category.lower(),
                service_std="kakao_page",
                country_std="kr",
                source_id="webtoon_kakaopage_public",
                source_page_type="next_data_card",
                section_name="kakaopage_home",
                position=position,
                raw_source_file=raw_source_file,
                notes="KakaoPage __NEXT_DATA__ CardView item",
                allow_proxy=True,
            )
        )
    return rows


def parse_piccoma_titles(html: str, raw_source_file: str) -> list[dict]:
    pattern = re.compile(
        r'<li class="PCM-rankingListProduct">.*?<a href="(/web/product/(\d+)[^"]*)"[^>]*data-gtm-param1="([^"]+)".*?'
        r'<div class="PCOM-prdList_rankNum">(\d+)</div>.*?'
        r'<div class="PCOM-prdList_title">(.*?)</div>.*?'
        r'<div class="PCOM-prdList_author">(.*?)</div>',
        re.S,
    )
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(html):
        href, product_id, section_name, rank_num, title_name, author_name = match.groups()
        key = (section_name, product_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            make_title_row(
                title_std=f"piccoma_{product_id}",
                title_id_raw=product_id,
                title_name=title_name,
                title_url=f"https://piccoma.com{href}",
                author_name=author_name,
                genre_text=section_name,
                format_type="comic_or_story",
                service_std="piccoma",
                country_std="jp",
                source_id="webtoon_piccoma_public",
                source_page_type="html_ranking_card",
                section_name=section_name,
                position=int(rank_num),
                raw_source_file=raw_source_file,
                notes="Piccoma ranking block on home page",
                allow_proxy=True,
            )
        )
    return rows


def parse_naver_weekday_titles(html: str, raw_source_file: str, week_code: str) -> list[dict]:
    pattern = re.compile(
        r'<a href="(/webtoon/list\?titleId=(\d+)[^"]*)" class="link_thumbnail".*?'
        r'<img [^>]*alt="([^"]+)".*?'
        r'<span class="author">\s*(.*?)\s*</span>',
        re.S,
    )
    rows: list[dict] = []
    seen: set[str] = set()
    position = 0
    for match in pattern.finditer(html):
        href, title_id, title_name, author_name = match.groups()
        if title_id in seen:
            continue
        seen.add(title_id)
        position += 1
        rows.append(
            make_title_row(
                title_std=f"naver_webtoon_{title_id}",
                title_id_raw=title_id,
                title_name=title_name,
                title_url=f"https://m.comic.naver.com{href}",
                author_name=author_name,
                genre_text=week_code,
                format_type="webtoon",
                service_std="naver_webtoon",
                country_std="kr",
                source_id="webtoon_naver_weekday_pages",
                source_page_type="weekday_list",
                section_name=week_code,
                position=position,
                raw_source_file=raw_source_file,
                notes="NAVER Webtoon mobile weekday listing",
                allow_proxy=True,
            )
        )
    return rows


def parse_bookwalker_titles(html: str, raw_source_file: str) -> list[dict]:
    pattern = re.compile(
        r'href="(/series/([A-Z0-9]+)/[^"]+)".{0,1500}?>(MANGA|NOVEL)<.{0,1200}?aria-label="([^"]+)" href="/series/\2/[^"]+"',
        re.S,
    )
    rows: list[dict] = []
    seen: set[str] = set()
    position = 0
    for match in pattern.finditer(html):
        href, series_id, format_type, title_name = match.groups()
        if series_id in seen:
            continue
        seen.add(series_id)
        position += 1
        rows.append(
            make_title_row(
                title_std=f"bookwalker_{series_id}",
                title_id_raw=series_id,
                title_name=title_name,
                title_url=f"https://global.bookwalker.jp{href}",
                author_name="",
                genre_text="",
                format_type=format_type.lower(),
                service_std="bookwalker",
                country_std="jp",
                source_id="webtoon_bookwalker_public",
                source_page_type="homepage_card",
                section_name="bookwalker_global_home",
                position=position,
                raw_source_file=raw_source_file,
                notes="BookWalker global storefront card; used only for entry-count style metrics",
                allow_proxy=False,
            )
        )
    return rows


def aggregate_platform_rows(title_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in title_rows:
        grouped[(row["service_std"], row["country_std"], row["year_quarter"])].append(row)

    platform_rows: list[dict] = []
    for (service_std, country_std, year_quarter), rows in sorted(grouped.items()):
        deduped: dict[str, dict] = {}
        source_ids: set[str] = set()
        source_files: set[str] = set()
        for row in rows:
            source_ids.add(row["source_id"])
            source_files.add(row["raw_source_file"])
            position = int(row["position"]) if row["position"].isdigit() else 999999
            existing = deduped.get(row["title_std"])
            if not existing or position < existing["position"]:
                deduped[row["title_std"]] = {
                    "position": position,
                    "local_ip_proxy": row["local_ip_proxy"],
                    "translated_proxy": row["translated_proxy"],
                    "format_type": row["format_type"],
                }

        distinct_titles = len(deduped)
        if distinct_titles == 0:
            continue

        base_row = {
            "panel_unit_type": "service_quarter",
            "country_std": country_std,
            "year_quarter": year_quarter,
            "firm_std": SERVICE_FIRM_MAP.get(service_std, ""),
            "service_std": service_std,
            "source_id": "|".join(sorted(source_ids)),
            "raw_source_file": "|".join(sorted(source_files)),
            "collection_status": "collected",
        }

        platform_rows.append(
            {
                **base_row,
                "metric_name": "platform_entry_count",
                "metric_variant": "distinct_title_count_snapshot",
                "metric_value": str(distinct_titles),
                "metric_unit": "count",
                "notes": "Distinct titles observed across collected public raw pages within the current quarter snapshot",
            }
        )

        proxy_rows = [value for value in deduped.values() if value["local_ip_proxy"] in {"0", "1"}]
        if proxy_rows:
            proxy_rows.sort(key=lambda item: item["position"])
            top_n = proxy_rows[:10]
            if top_n:
                local_top_share = sum(int(item["local_ip_proxy"]) for item in top_n) / len(top_n)
                platform_rows.append(
                    {
                        **base_row,
                        "metric_name": "local_ip_topN_share",
                        "metric_variant": "top10_script_proxy",
                        "metric_value": f"{local_top_share:.6f}",
                        "metric_unit": "share",
                        "notes": "Local-IP proxy share among top 10 titles using service-country script heuristics",
                    }
                )

            weighted_numerator = 0.0
            weighted_denominator = 0.0
            for item in proxy_rows:
                if item["position"] <= 0 or item["position"] == 999999:
                    continue
                weight = 1.0 / item["position"]
                weighted_numerator += int(item["local_ip_proxy"]) * weight
                weighted_denominator += weight
            if weighted_denominator > 0:
                platform_rows.append(
                    {
                        **base_row,
                        "metric_name": "weighted_local_exposure",
                        "metric_variant": "inverse_rank_script_proxy",
                        "metric_value": f"{weighted_numerator / weighted_denominator:.6f}",
                        "metric_unit": "share",
                        "notes": "Inverse-rank weighted local exposure using script-based local proxy",
                    }
                )

        translated_rows = [value for value in deduped.values() if value["translated_proxy"] in {"0", "1"}]
        if translated_rows:
            translated_share = sum(int(item["translated_proxy"]) for item in translated_rows) / len(translated_rows)
            platform_rows.append(
                {
                    **base_row,
                    "metric_name": "translated_title_share",
                    "metric_variant": "script_proxy",
                    "metric_value": f"{translated_share:.6f}",
                    "metric_unit": "share",
                    "notes": "Translated-title proxy share using service-country script heuristics",
                }
            )

    return platform_rows


def main() -> None:
    source_manifest_rows: list[dict] = []
    source_registry_rows: list[dict] = []
    title_rows: list[dict] = []
    project_manifest_rows: list[dict] = []

    source_specs = [
        {
            "source_id": "webtoon_webtoons_public",
            "source_name": "WEBTOON EN ranking page",
            "source_url": "https://www.webtoons.com/en/ranking",
            "country_std": "us",
            "service_std": "webtoon",
            "raw_path": RAW_DIR / "webtoon" / f"us_webtoon_en_ranking_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count",
            "status_on_collect": "collected",
            "notes": "WEBTOON EN ranking HTML with title cards and title IDs",
        },
        {
            "source_id": "webtoon_webtoons_originals",
            "source_name": "WEBTOON EN originals page",
            "source_url": "https://www.webtoons.com/en/originals",
            "country_std": "us",
            "service_std": "webtoon",
            "raw_path": RAW_DIR / "webtoon" / f"us_webtoon_en_originals_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count",
            "status_on_collect": "collected",
            "notes": "WEBTOON EN originals HTML with visible title cards",
        },
        {
            "source_id": "webtoon_kakaopage_public",
            "source_name": "KakaoPage home page",
            "source_url": "https://page.kakao.com/",
            "country_std": "kr",
            "service_std": "kakao_page",
            "raw_path": RAW_DIR / "kakaopage" / f"kr_kakaopage_home_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count|local_ip_topN_share|weighted_local_exposure|translated_title_share",
            "status_on_collect": "collected",
            "notes": "KakaoPage __NEXT_DATA__ includes CardView series items",
        },
        {
            "source_id": "webtoon_piccoma_public",
            "source_name": "Piccoma home page",
            "source_url": "https://piccoma.com/web/",
            "country_std": "jp",
            "service_std": "piccoma",
            "raw_path": RAW_DIR / "piccoma" / f"jp_piccoma_home_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count|local_ip_topN_share|weighted_local_exposure|translated_title_share",
            "status_on_collect": "collected",
            "notes": "Piccoma home page ranking blocks expose product IDs, rank numbers, titles, and authors",
        },
        {
            "source_id": "webtoon_naver_weekday_pages",
            "source_name": "NAVER Webtoon weekday pages",
            "source_url": "https://m.comic.naver.com/webtoon/weekday",
            "country_std": "kr",
            "service_std": "naver_webtoon",
            "raw_path": RAW_DIR / "naver_webtoon" / f"kr_naver_weekday_MON_TEMPLATE_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count|local_ip_topN_share|weighted_local_exposure|translated_title_share",
            "status_on_collect": "collected",
            "notes": "Collected Monday-Sunday mobile weekday pages to stabilize KR title snapshot coverage",
        },
        {
            "source_id": "webtoon_bookwalker_public",
            "source_name": "BookWalker global home page",
            "source_url": "https://global.bookwalker.jp/",
            "country_std": "jp",
            "service_std": "bookwalker",
            "raw_path": RAW_DIR / "bookwalker" / f"jp_bookwalker_global_home_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count",
            "status_on_collect": "collected_partial",
            "notes": "Global storefront raw was collected, but stable same-card title extraction remained incomplete in this step",
        },
        {
            "source_id": "webtoon_lezhin_public",
            "source_name": "Lezhin Comics home page",
            "source_url": "https://www.lezhinus.com/ko",
            "country_std": "kr",
            "service_std": "lezhin_comics",
            "raw_path": RAW_DIR / "lezhin" / f"kr_lezhin_home_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count|weighted_local_exposure",
            "status_on_collect": "collected_partial",
            "notes": "Raw HTML collected, but title extraction was deferred because the useful payload is embedded in streamed app state",
        },
        {
            "source_id": "webtoon_ridi_public",
            "source_name": "RIDI recommendation page",
            "source_url": "https://ridibooks.com/comics/webtoon/recommendation",
            "country_std": "kr",
            "service_std": "ridi",
            "raw_path": RAW_DIR / "ridi" / f"kr_ridi_recommendation_{ACCESS_DATE_TAG}.html",
            "metric_targets": "platform_entry_count|translated_title_share",
            "status_on_collect": "collected_partial",
            "notes": "Raw HTML collected, but the recommendation payload was not directly reconstructible from the storefront snapshot",
        },
        {
            "source_id": "webtoon_kocca_survey",
            "source_name": "KOCCA webtoon industry survey page",
            "source_url": "https://www.kocca.kr/kocca/bbs/view/B0000147/2007553.do",
            "country_std": "kr",
            "service_std": "",
            "raw_path": RAW_DIR / "reference" / f"kr_kocca_webtoon_survey_{ACCESS_DATE_TAG}.html",
            "metric_targets": "creator_share_ratio",
            "status_on_collect": "collected_reference_only",
            "notes": "Reference-only raw page collected for later creator-share verification; attachment URL was not automatically resolved in this step",
        },
    ]

    for spec in source_specs:
        if spec["source_id"] == "webtoon_naver_weekday_pages":
            week_files: list[str] = []
            for week_code in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                raw_path = RAW_DIR / "naver_webtoon" / f"kr_naver_weekday_{week_code}_{ACCESS_DATE_TAG}.html"
                url = f"https://m.comic.naver.com/webtoon/weekday?week={week_code}"
                run_curl(url, raw_path)
                relative_raw = raw_path.relative_to(PROJECT_DIR).as_posix()
                week_files.append(relative_raw)
                source_manifest_rows.append(
                    {
                        "source_file": relative_raw,
                        "source_url": url,
                        "access_date": ACCESS_DATE,
                        "country_std": "kr",
                        "firm_std": SERVICE_FIRM_MAP["naver_webtoon"],
                        "service_std": "naver_webtoon",
                        "sector_std": "webtoon_story",
                        "file_format": "html",
                        "collected_by_prompt": PROMPT_LABEL,
                        "status": "collected",
                    }
                )
                html = raw_path.read_text(errors="replace")
                title_rows.extend(parse_naver_weekday_titles(html, relative_raw, week_code))

            source_registry_rows.append(
                {
                    "source_id": spec["source_id"],
                    "source_name": spec["source_name"],
                    "source_url": spec["source_url"],
                    "country_std": spec["country_std"],
                    "firm_std": SERVICE_FIRM_MAP["naver_webtoon"],
                    "service_std": spec["service_std"],
                    "metric_targets": spec["metric_targets"],
                    "collection_status": spec["status_on_collect"],
                    "raw_storage_path": "data/raw/webtoon/naver_webtoon/*.html",
                    "access_date": ACCESS_DATE,
                    "notes": spec["notes"],
                }
            )
            continue

        raw_path = spec["raw_path"]
        run_curl(spec["source_url"], raw_path)
        relative_raw = raw_path.relative_to(PROJECT_DIR).as_posix()
        source_manifest_rows.append(
            {
                "source_file": relative_raw,
                "source_url": spec["source_url"],
                "access_date": ACCESS_DATE,
                "country_std": spec["country_std"],
                "firm_std": SERVICE_FIRM_MAP.get(spec["service_std"], ""),
                "service_std": spec["service_std"],
                "sector_std": "webtoon_story",
                "file_format": raw_path.suffix.lstrip("."),
                "collected_by_prompt": PROMPT_LABEL,
                "status": spec["status_on_collect"],
            }
        )

        html = raw_path.read_text(errors="replace")
        if spec["source_id"] in {"webtoon_webtoons_public", "webtoon_webtoons_originals"}:
            title_rows.extend(
                parse_webtoon_titles(
                    html,
                    relative_raw,
                    source_id=spec["source_id"],
                    section_name="ranking" if "public" in spec["source_id"] else "originals",
                )
            )
        elif spec["source_id"] == "webtoon_kakaopage_public":
            title_rows.extend(parse_kakaopage_titles(html, relative_raw))
        elif spec["source_id"] == "webtoon_piccoma_public":
            title_rows.extend(parse_piccoma_titles(html, relative_raw))
        elif spec["source_id"] == "webtoon_bookwalker_public":
            title_rows.extend(parse_bookwalker_titles(html, relative_raw))

        source_registry_rows.append(
            {
                "source_id": spec["source_id"],
                "source_name": spec["source_name"],
                "source_url": spec["source_url"],
                "country_std": spec["country_std"],
                "firm_std": SERVICE_FIRM_MAP.get(spec["service_std"], ""),
                "service_std": spec["service_std"],
                "metric_targets": spec["metric_targets"],
                "collection_status": spec["status_on_collect"],
                "raw_storage_path": relative_raw,
                "access_date": ACCESS_DATE,
                "notes": spec["notes"],
            }
        )

    title_fieldnames = [
        "title_std",
        "title_id_raw",
        "title_name",
        "title_url",
        "author_name",
        "genre_text",
        "format_type",
        "firm_std",
        "service_std",
        "country_std",
        "year_quarter",
        "access_date",
        "source_id",
        "source_page_type",
        "section_name",
        "position",
        "local_ip_proxy",
        "translated_proxy",
        "proxy_basis",
        "raw_source_file",
        "collection_status",
        "notes",
    ]
    title_rows.sort(
        key=lambda row: (
            row["service_std"],
            row["country_std"],
            row["title_std"],
            row["source_id"],
            int(row["position"]) if row["position"].isdigit() else 999999,
        )
    )
    write_csv(TITLE_PANEL_PATH, title_rows, title_fieldnames)

    platform_rows = aggregate_platform_rows(title_rows)
    platform_fieldnames = [
        "panel_unit_type",
        "country_std",
        "year_quarter",
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
    platform_rows.sort(
        key=lambda row: (
            row["country_std"],
            row["service_std"],
            row["metric_name"],
            row["metric_variant"],
        )
    )
    write_csv(PLATFORM_PANEL_PATH, platform_rows, platform_fieldnames)

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
                "path": "scripts/collect_webtoon_market_data.py",
                "owner_step": PROMPT_LABEL,
                "source_type": "local_code",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Reproducible public-web collection and panel build for webtoon/story title and platform data",
            },
            {
                "artifact_type": "dataset",
                "path": "data/interim/webtoon_source_registry.csv",
                "owner_step": PROMPT_LABEL,
                "source_type": "public_web_collection",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Webtoon/story source registry with collected, partial, and reference-only statuses",
            },
            {
                "artifact_type": "dataset",
                "path": "data/interim/webtoon_title_raw_panel.csv",
                "owner_step": PROMPT_LABEL,
                "source_type": "public_web_collection",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Title-quarter raw panel with service, country, title IDs, positions, and origin proxies",
            },
            {
                "artifact_type": "dataset",
                "path": "data/interim/webtoon_platform_raw_panel.csv",
                "owner_step": PROMPT_LABEL,
                "source_type": "derived_public_panel",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Service-quarter platform panel with entry count and proxy-based exposure metrics",
            },
            {
                "artifact_type": "log",
                "path": "logs/webtoon_collection_log.md",
                "owner_step": PROMPT_LABEL,
                "source_type": "local_log",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Webtoon/story collection notes and unresolved extraction gaps",
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

    status_counts: dict[str, int] = defaultdict(int)
    for row in source_registry_rows:
        status_counts[row["collection_status"]] += 1

    extracted_services = sorted({row["service_std"] for row in title_rows if row["service_std"]})
    title_counts_by_service: dict[str, int] = defaultdict(int)
    for row in title_rows:
        title_counts_by_service[row["service_std"]] += 1

    log_text = f"""# Exec Prompt 16. 웹툰 및 스토리 분야 서비스·작품 데이터 수집

- 실행일: {ACCESS_DATE}
- 생성 스크립트: `scripts/collect_webtoon_market_data.py`
- 저장 raw 파일 수: {len(source_manifest_rows)}건
- 생성 title raw panel 행 수: {len(title_rows)}행
- 생성 platform raw panel 행 수: {len(platform_rows)}행

## 이번 단계에서 실제 수집한 공개 원천

- WEBTOON EN `ranking`, `originals` HTML
- 카카오페이지 공개 홈 HTML
- 픽코마 공개 홈 HTML
- 네이버웹툰 모바일 요일별 페이지 7건
- BOOK WALKER 글로벌 공개 홈 HTML
- 레진코믹스, RIDI 공개 홈 raw HTML
- KOCCA 웹툰 산업조사 페이지 raw HTML

## 실제 추출이 완료된 서비스

- {", ".join(extracted_services) if extracted_services else "없음"}

## 서비스별 추출 title 행 수

""" + "\n".join(
        f"- `{service_std}`: {count}행" for service_std, count in sorted(title_counts_by_service.items())
    ) + f"""

## source registry 상태 분포

- `collected`: {status_counts.get('collected', 0)}
- `collected_partial`: {status_counts.get('collected_partial', 0)}
- `collected_reference_only`: {status_counts.get('collected_reference_only', 0)}

## 이번 단계에서 만든 지표

- `platform_entry_count`
- `local_ip_topN_share`
- `weighted_local_exposure`
- `translated_title_share`

## 보류 또는 제한 사항

- `title_survival_ratio`: 단일 분기 snapshot만 확보된 상태라 시계열 생존율은 아직 계산하지 않음
- `creator_share_ratio`: KOCCA reference raw는 저장했지만 첨부 원문 자동 회수는 이번 단계에서 확정하지 못함
- `lezhin_comics`, `ridi`: storefront raw는 확보했으나 즉시 사용 가능한 title payload는 후속 구조 복원 단계가 필요함
- `bookwalker`, `webtoon` EN storefront는 영문 글로벌 노출면이라 현지 원산지 판정 proxy는 적용하지 않고 entry-count 성격으로만 사용함
"""
    LOG_PATH.write_text(log_text)

    workflow_entry = f"""
### Exec Prompt 16. 웹툰 및 스토리 분야 서비스·작품 데이터 수집

- `scripts/collect_webtoon_market_data.py`를 추가해 WEBTOON, 카카오페이지, 픽코마, 네이버웹툰, BOOK WALKER, 레진, RIDI, KOCCA raw 원천을 한 번에 수집하도록 구성함
- `data/interim/webtoon_source_registry.csv`를 생성해 collected, collected_partial, collected_reference_only 상태를 source 단위로 고정함
- `data/interim/webtoon_title_raw_panel.csv`를 생성해 `title_std`, `service_std`, `country_std`, `year_quarter`를 유지한 title-quarter 장기 형식 raw를 정리함
- `data/interim/webtoon_platform_raw_panel.csv`를 생성해 `platform_entry_count`, `local_ip_topN_share`, `weighted_local_exposure`, `translated_title_share`를 서비스-분기 단위로 집계함
- 네이버웹툰은 월~일 모바일 요일별 페이지 7건을 저장해 한국 title snapshot 범위를 넓혔고, 카카오페이지와 픽코마는 공개 HTML/Next 데이터에서 title ID와 노출 순서를 직접 추출함
- `title_survival_ratio`와 `creator_share_ratio`는 공개 원천을 확보했지만 시계열 또는 첨부 원문 해석이 더 필요해 이번 단계에서는 보류함
""".rstrip()

    workflow_text = WORKFLOW_LOG_PATH.read_text()
    if "### Exec Prompt 16. 웹툰 및 스토리 분야 서비스·작품 데이터 수집" not in workflow_text:
        WORKFLOW_LOG_PATH.write_text(workflow_text.rstrip() + "\n\n" + workflow_entry + "\n")


if __name__ == "__main__":
    main()
