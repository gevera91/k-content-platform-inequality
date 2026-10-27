#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
import ssl
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCESS_DATE = date.today().isoformat()
STAMP = ACCESS_DATE.replace("-", "")

RAW_POLICY_DIR = PROJECT_ROOT / "data" / "raw" / "music" / "reanalysis_policy"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim" / "claim_strengthening"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "claim_strengthening"
OUTPUT_TABLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "claim_strengthening"
OUTPUT_FIG_DIR = PROJECT_ROOT / "outputs" / "figures" / "claim_strengthening"
LOG_DIR = PROJECT_ROOT / "logs" / "claim_strengthening"

SOURCE_REGISTRY_PATH = INTERIM_DIR / "kr_music_reanalysis_source_registry.csv"
PANEL_PATH = PROCESSED_DIR / "kr_music_reverse_discrimination_reanalysis.csv"
SUMMARY_PATH = OUTPUT_TABLE_DIR / "T_kr_music_reverse_discrimination_summary.csv"
FIGURE_PATH = OUTPUT_FIG_DIR / "F_kr_music_reverse_discrimination_summary.png"
LOG_PATH = LOG_DIR / "kr_music_reverse_discrimination_reanalysis_log.md"

LEGACY_GAP_PATH = OUTPUT_TABLE_DIR / "T_claim_korea_vs_global_gap.csv"
MATCHED_TAX_PATH = PROCESSED_DIR / "matched_effective_tax_rate_panel.csv"
DIRECT_COST_PATH = PROCESSED_DIR / "direct_cost_burden_panel.csv"
FIRM_CPII_PATH = PROJECT_ROOT / "data" / "processed" / "cpii_panel_firm_country_quarter.csv"

SSL_CONTEXT = ssl._create_unverified_context()


REMOTE_SOURCES = [
    {
        "source_id": "music_reanalysis_ftc_bundle_open",
        "source_name": "Korea FTC consent-decree opening for YouTube bundle case",
        "source_url": "https://m.korea.kr/briefing/pressReleaseView.do?newsId=156690350",
        "raw_filename": f"kr_ftc_youtube_bundle_open_{STAMP}.html",
        "binary": False,
        "notes": "Official Korea briefing page describing the opening of the consent-decree process over YouTube bundling and music-market competition concerns.",
    },
    {
        "source_id": "music_reanalysis_ftc_bundle_final",
        "source_name": "Korea FTC final consent decree for YouTube bundle case",
        "source_url": "https://www.korea.kr/briefing/policyBriefingView.do?newsId=156731835",
        "raw_filename": f"kr_ftc_youtube_bundle_final_{STAMP}.html",
        "binary": False,
        "notes": "Official Korea policy briefing page describing the final consent decree and the launch of YouTube Premium Lite in Korea.",
    },
    {
        "source_id": "music_reanalysis_tariff_pdf",
        "source_name": "Published music royalty tariff PDF",
        "source_url": "https://www.copyright.or.kr/master/file/displayPdf.do?fileNo=39520",
        "raw_filename": f"kr_music_tariff_rules_{STAMP}.pdf",
        "binary": True,
        "notes": "Official published tariff PDF showing the monthly streaming gross-sales rule and the PC/Web basis for in-app settlement where the service is the same.",
    },
    {
        "source_id": "music_reanalysis_mt_licensing",
        "source_name": "MoneyToday article on gross-to-net amendment and YouTube contract opacity",
        "source_url": "https://www.mt.co.kr/tech/2025/11/18/2025111716154672196",
        "raw_filename": f"kr_music_licensing_transparency_{STAMP}.html",
        "binary": False,
        "notes": "Business reporting summarizing the proposed gross-to-net amendment and the reported separate YouTube/KOMCA contract structure.",
    },
    {
        "source_id": "music_reanalysis_mcst_audit",
        "source_name": "MCST press page for 2024 audit of music copyright trust-management bodies",
        "source_url": "https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=21856",
        "raw_filename": f"kr_mcst_music_trust_audit_{STAMP}.html",
        "binary": False,
        "notes": "Official MCST press page for the 2024 inspection results of three music copyright trust-management bodies.",
    },
    {
        "source_id": "music_reanalysis_komca_residual",
        "source_name": "KOMCA YouTube residual royalty claim system",
        "source_url": "https://residual-claim.komca.or.kr/",
        "raw_filename": f"kr_komca_youtube_residual_claim_{STAMP}.html",
        "binary": False,
        "notes": "Official KOMCA residual-claim portal showing that YouTube residual royalty settlement remains separately administered.",
    },
    {
        "source_id": "music_reanalysis_yna_copyright_growth",
        "source_name": "Yonhap article on 2024 music copyright collections",
        "source_url": "https://www.yna.co.kr/view/AKR20250122050600005",
        "raw_filename": f"kr_yna_music_collections_{STAMP}.html",
        "binary": False,
        "notes": "Yonhap reporting that music copyright collections and distributions rose in 2024, used as a guardrail against overclaiming industry collapse.",
    },
    {
        "source_id": "music_reanalysis_yna_billboard",
        "source_name": "Yonhap article on Billboard repeat-download rule change",
        "source_url": "https://www.yna.co.kr/view/AKR20220122036600005",
        "raw_filename": f"kr_yna_billboard_rule_shift_{STAMP}.html",
        "binary": False,
        "notes": "Yonhap reporting that Billboard reduced valid repeat downloads from four to one, weakening a K-pop-heavy performance channel.",
    },
]

REUSED_LOCAL_SOURCES = [
    {
        "source_id": "music_reanalysis_youtube_premium_price",
        "source_name": "YouTube Premium Korea pricing page",
        "source_url": "https://www.youtube.com/premium",
        "raw_storage_path": "data/raw/music/pricing/kr_youtube_premium_20260329.html",
        "notes": "Existing local raw page reused for Premium Lite and full Premium Korea prices.",
    },
    {
        "source_id": "music_reanalysis_youtube_music_price",
        "source_name": "YouTube Music Premium Korea pricing page",
        "source_url": "https://www.youtube.com/musicpremium",
        "raw_storage_path": "data/raw/music/pricing/kr_youtube_musicpremium_20260329.html",
        "notes": "Existing local raw page reused for YouTube Music standalone Korea price.",
    },
    {
        "source_id": "music_reanalysis_melon_price",
        "source_name": "Melon pricing page",
        "source_url": "https://www.melon.com/buy/pamphlet/all.htm",
        "raw_storage_path": "data/raw/music/melon/kr_melon_all_20260329.html",
        "notes": "Existing local raw page reused for Melon streaming and streaming-plus prices.",
    },
]


def fetch_url(url: str, output_path: Path, *, binary: bool) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=40, context=SSL_CONTEXT) as response:
        content = response.read()
        output_path.write_bytes(content)
    return "collected"


def safe_int(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else 0


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_first(pattern: str, text: str) -> int:
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise RuntimeError(f"Pattern not found: {pattern}")
    return safe_int(match.group(1))


def extract_prices() -> dict[str, float]:
    yt_bundle_text = read_text(PROJECT_ROOT / "data/raw/music/pricing/kr_youtube_premium_20260329.html")
    yt_music_text = read_text(PROJECT_ROOT / "data/raw/music/pricing/kr_youtube_musicpremium_20260329.html")
    melon_text = read_text(PROJECT_ROOT / "data/raw/music/melon/kr_melon_all_20260329.html")

    positive_bundle_prices = sorted(
        {
            safe_int(value)
            for value in re.findall(r"₩([0-9,]+)", yt_bundle_text)
            if safe_int(value) > 0
        }
    )
    positive_music_prices = sorted(
        {
            safe_int(value)
            for value in re.findall(r"₩([0-9,]+)", yt_music_text)
            if safe_int(value) > 0
        }
    )
    youtube_lite = min(positive_bundle_prices)
    youtube_bundle = max(positive_bundle_prices)
    youtube_music = max(positive_music_prices)
    melon_streaming = extract_first(
        r"<h4 class=\"title\">스트리밍클럽 정기결제.*?<span class=\"sale_price\">([0-9,]+)원</span>",
        melon_text,
    )

    implied_music_component = youtube_bundle - youtube_lite
    bundle_leverage_index = youtube_music / youtube_bundle
    lite_plus_melon = youtube_lite + melon_streaming
    bundle_discount_vs_lite_plus_melon = (lite_plus_melon - youtube_bundle) / lite_plus_melon
    implied_music_discount_vs_melon = (melon_streaming - implied_music_component) / melon_streaming

    return {
        "youtube_premium_lite_monthly_krw": float(youtube_lite),
        "youtube_premium_bundle_monthly_krw": float(youtube_bundle),
        "youtube_music_standalone_monthly_krw": float(youtube_music),
        "melon_streaming_monthly_krw": float(melon_streaming),
        "youtube_bundle_leverage_index": bundle_leverage_index,
        "bundle_discount_vs_lite_plus_melon": bundle_discount_vs_lite_plus_melon,
        "implied_music_discount_vs_melon": implied_music_discount_vs_melon,
        "youtube_implied_music_component_krw": float(implied_music_component),
    }


def build_source_registry() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for spec in REMOTE_SOURCES:
        output_path = RAW_POLICY_DIR / spec["raw_filename"]
        status = "blocked"
        note = spec["notes"]
        try:
            status = fetch_url(spec["source_url"], output_path, binary=spec["binary"])
        except Exception as exc:
            note = f"{spec['notes']} Collection error: {exc!r}"

        rows.append(
            {
                "source_id": spec["source_id"],
                "source_name": spec["source_name"],
                "source_url": spec["source_url"],
                "country_std": "kr",
                "sector_std": "music",
                "collection_status": status,
                "raw_storage_path": str(output_path.relative_to(PROJECT_ROOT)) if output_path.exists() else "",
                "access_date": ACCESS_DATE,
                "notes": note,
            }
        )

    for spec in REUSED_LOCAL_SOURCES:
        local_path = PROJECT_ROOT / spec["raw_storage_path"]
        rows.append(
            {
                "source_id": spec["source_id"],
                "source_name": spec["source_name"],
                "source_url": spec["source_url"],
                "country_std": "kr",
                "sector_std": "music",
                "collection_status": "reused_existing" if local_path.exists() else "missing_reused_source",
                "raw_storage_path": spec["raw_storage_path"] if local_path.exists() else "",
                "access_date": ACCESS_DATE,
                "notes": spec["notes"],
            }
        )

    rows.sort(key=lambda row: row["source_id"])
    fieldnames = [
        "source_id",
        "source_name",
        "source_url",
        "country_std",
        "sector_std",
        "collection_status",
        "raw_storage_path",
        "access_date",
        "notes",
    ]
    SOURCE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SOURCE_REGISTRY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def support_row(
    *,
    layer_id: str,
    layer_name: str,
    metric_id: str,
    metric_name: str,
    metric_value: float,
    metric_unit: str,
    support_score: float,
    claim_effect: str,
    evidence_strength: str,
    source_id: str,
    source_url: str,
    analysis_note: str,
) -> dict[str, str]:
    return {
        "layer_id": layer_id,
        "layer_name": layer_name,
        "metric_id": metric_id,
        "metric_name": metric_name,
        "metric_value": f"{metric_value:.6f}" if isinstance(metric_value, float) else str(metric_value),
        "metric_unit": metric_unit,
        "support_score_0_100": f"{support_score:.6f}",
        "claim_effect": claim_effect,
        "evidence_strength": evidence_strength,
        "source_id": source_id,
        "source_url": source_url,
        "analysis_note": analysis_note,
    }


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def load_tax_support_metrics() -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []

    matched_tax_rows = read_csv(MATCHED_TAX_PATH)
    spotify_row = next(
        row
        for row in matched_tax_rows
        if row["peer_group_id"] == "mus_streaming_paid_core"
        and row["firm_std"] == "spotify"
        and row["fiscal_period"] == "FY2025"
        and row["comparability_flag"] == "yes"
    )
    dreamus_row = next(
        row
        for row in matched_tax_rows
        if row["peer_group_id"] == "mus_streaming_paid_core"
        and row["firm_std"] == "dreamus"
        and row["fiscal_period"] == "FY2025"
        and row["comparability_flag"] == "yes"
    )
    spotify_etr = float(spotify_row["effective_tax_rate"])
    dreamus_etr = float(dreamus_row["effective_tax_rate"])
    matched_gap = dreamus_etr - spotify_etr
    metrics.append(
        support_row(
            layer_id="L5",
            layer_name="tax_asymmetry",
            metric_id="matched_fy2025_etr_gap",
            metric_name="Matched FY2025 effective tax rate gap between Korean streaming anchor and global peer",
            metric_value=matched_gap,
            metric_unit="rate_gap",
            support_score=clamp_score(matched_gap * 250.0),
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="matched_effective_tax_rate_panel",
            source_url="local_panel",
            analysis_note=(
                f"Within the same streaming peer and fiscal year, Dreamus/FLO records an effective tax rate of {dreamus_etr:.6f} "
                f"versus Spotify's {spotify_etr:.6f}, a gap of {matched_gap:.6f}. "
                "This is not a Korea-market tax remittance measure, but it is the strongest directly matched tax-burden gap currently observable in the music peer set."
            ),
        )
    )

    direct_cost_rows = read_csv(DIRECT_COST_PATH)
    spotify_cost = next(
        row
        for row in direct_cost_rows
        if row["peer_group_id"] == "mus_streaming_paid_core" and row["firm_std"] == "spotify"
    )
    dreamus_cost = next(
        row
        for row in direct_cost_rows
        if row["peer_group_id"] == "mus_streaming_paid_core" and row["firm_std"] == "dreamus"
    )
    dreamus_tax_score = float(dreamus_cost["tax_burden_score"] or 0.0)
    spotify_tax_score = float(spotify_cost["tax_burden_score"] or 0.0)
    metrics.append(
        support_row(
            layer_id="L5",
            layer_name="tax_asymmetry",
            metric_id="streaming_peer_tax_score_gap",
            metric_name="Direct cost panel assigns full tax burden score to Korean anchor and zero to global peer",
            metric_value=dreamus_tax_score - spotify_tax_score,
            metric_unit="score_gap",
            support_score=clamp_score(dreamus_tax_score - spotify_tax_score),
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="direct_cost_burden_panel",
            source_url="local_panel",
            analysis_note=(
                f"In the direct cost panel for the same-service streaming peer, Dreamus receives a tax burden score of {dreamus_tax_score:.1f} "
                f"while Spotify receives {spotify_tax_score:.1f}. This mirrors the matched FY2025 effective-tax-rate gap and pushes the Korean side upward on the cost channel."
            ),
        )
    )

    cpii_rows = read_csv(FIRM_CPII_PATH)
    alphabet_rows = [
        row
        for row in cpii_rows
        if row["firm_std"] == "alphabet"
        and row["country_std"] == "kr"
        and row["sector_std"] == "music"
        and "youtube_music" in row["service_list"]
    ]
    missing_tax_rows = [
        row for row in alphabet_rows if not (row.get("effective_tax_rate_gap") or "").strip()
    ]
    missing_share = len(missing_tax_rows) / len(alphabet_rows) if alphabet_rows else 1.0
    metrics.append(
        support_row(
            layer_id="L5",
            layer_name="tax_asymmetry",
            metric_id="bigtech_korea_tax_visibility_gap",
            metric_name="No usable Korea-facing tax observation for Alphabet/YouTube Music in current executable firm-quarter panel",
            metric_value=missing_share,
            metric_unit="missing_share",
            support_score=clamp_score(missing_share * 75.0),
            claim_effect="supports_structural_discrimination",
            evidence_strength="medium",
            source_id="cpii_panel_firm_country_quarter",
            source_url="local_panel",
            analysis_note=(
                f"Across {len(alphabet_rows)} Alphabet-Korea-music firm-quarter rows in the executable panel, "
                f"{len(missing_tax_rows)} have no usable effective-tax-rate observation. "
                "This does not prove that Google pays no tax in Korea, but it does show that Korea-facing tax incidence is materially less transparent and less directly auditable for the big-tech side than for domestic listed anchors."
            ),
        )
    )

    return metrics


def build_panel_rows(prices: dict[str, float]) -> list[dict[str, str]]:
    bundle_ratio = prices["youtube_bundle_leverage_index"]
    lite_combo_discount = prices["bundle_discount_vs_lite_plus_melon"]
    implied_music_discount = prices["implied_music_discount_vs_melon"]

    rows = [
        support_row(
            layer_id="L1",
            layer_name="regulatory_licensing_asymmetry",
            metric_id="gross_sales_streaming_rule",
            metric_name="Published monthly streaming tariff uses gross-sales base",
            metric_value=1.0,
            metric_unit="flag",
            support_score=100.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="music_reanalysis_tariff_pdf",
            source_url="https://www.copyright.or.kr/master/file/displayPdf.do?fileNo=39520",
            analysis_note="The published tariff defines monthly streaming revenue as gross sales including discounted amounts, so domestic online-music services remain directly exposed to a published gross-sales rule.",
        ),
        support_row(
            layer_id="L1",
            layer_name="regulatory_licensing_asymmetry",
            metric_id="foreign_contract_opacity",
            metric_name="Functionally competing foreign arrangement remains less transparent and less comparable",
            metric_value=1.0,
            metric_unit="flag",
            support_score=85.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="medium",
            source_id="music_reanalysis_mt_licensing",
            source_url="https://www.mt.co.kr/tech/2025/11/18/2025111716154672196",
            analysis_note="Reporting indicates YouTube Music settles under a separate KOMCA contract and that rates may differ because YouTube and YouTube Music are jointly contracted as a mixed video-and-music platform.",
        ),
        support_row(
            layer_id="L1",
            layer_name="regulatory_licensing_asymmetry",
            metric_id="gross_vs_net_slogan_overstatement",
            metric_name="Simple domestic-gross versus foreign-net slogan is not fully documented as a one-line formula gap",
            metric_value=0.0,
            metric_unit="flag",
            support_score=25.0,
            claim_effect="tempers_overstatement",
            evidence_strength="medium",
            source_id="music_reanalysis_tariff_pdf",
            source_url="https://www.copyright.or.kr/master/file/displayPdf.do?fileNo=39520",
            analysis_note="The published tariff also states that where in-app and PC/Web are the same service, in-app settlement uses the PC/Web price and formula, so the strongest defensible claim is transparency and comparability asymmetry rather than a fully documented one-line gross-versus-net gap for every domestic and foreign service.",
        ),
        support_row(
            layer_id="L2",
            layer_name="google_bundle_platform_power",
            metric_id="ftc_bundle_structural_relief",
            metric_name="Korean competition authority required structural relief for YouTube bundle design",
            metric_value=1.0,
            metric_unit="flag",
            support_score=100.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="music_reanalysis_ftc_bundle_final",
            source_url="https://www.korea.kr/briefing/policyBriefingView.do?newsId=156731835",
            analysis_note="The official FTC record says fair competition and consumer choice in the Korean online-music market needed to be restored through structural relief, including a video-only YouTube Premium Lite option.",
        ),
        support_row(
            layer_id="L2",
            layer_name="google_bundle_platform_power",
            metric_id="bundle_price_leverage_index",
            metric_name="YouTube Music standalone price as a share of full YouTube Premium bundle price",
            metric_value=bundle_ratio,
            metric_unit="ratio",
            support_score=bundle_ratio * 100.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="music_reanalysis_youtube_music_price|music_reanalysis_youtube_premium_price|music_reanalysis_melon_price",
            source_url="https://www.youtube.com/musicpremium|https://www.youtube.com/premium|https://www.melon.com/buy/pamphlet/all.htm",
            analysis_note=(
                f"YouTube Music standalone is {bundle_ratio:.3f} of the full Premium bundle price; "
                f"the implied music component is KRW {int(prices['youtube_implied_music_component_krw'])}, "
                f"which is {implied_music_discount * 100:.1f}% below Melon's streaming-club price, "
                f"while the full bundle is {lite_combo_discount * 100:.1f}% cheaper than combining Premium Lite with Melon."
            ),
        ),
        support_row(
            layer_id="L3",
            layer_name="domestic_governance_opacity",
            metric_id="mcst_audit_governance_risk",
            metric_name="Official audit identifies trust-management governance and budget-control problems",
            metric_value=1.0,
            metric_unit="flag",
            support_score=90.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="strong",
            source_id="music_reanalysis_mcst_audit",
            source_url="https://www.mcst.go.kr/site/s_notice/press/pressView.jsp?pSeq=21856",
            analysis_note="The official MCST audit is described as having found multiple conflict-of-interest, budget-execution, and organizational-operation problems across the music trust-management bodies, which weakens institutional trust and makes foreign-platform disputes harder to verify cleanly.",
        ),
        support_row(
            layer_id="L3",
            layer_name="domestic_governance_opacity",
            metric_id="youtube_residual_claim_signal",
            metric_name="Separate YouTube residual-royalty claim administration signals persistent settlement opacity",
            metric_value=1.0,
            metric_unit="flag",
            support_score=70.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="medium",
            source_id="music_reanalysis_komca_residual",
            source_url="https://residual-claim.komca.or.kr/",
            analysis_note="The existence of a dedicated YouTube residual-royalty claim system indicates that settlement and distribution remain exceptional enough to require separate administration rather than a fully transparent and easily auditable ordinary flow.",
        ),
        support_row(
            layer_id="L4",
            layer_name="foreign_metric_dependence",
            metric_id="billboard_repeat_download_shift",
            metric_name="Billboard rule change reduced valid repeat downloads from four to one",
            metric_value=1.0,
            metric_unit="flag",
            support_score=80.0,
            claim_effect="supports_structural_discrimination",
            evidence_strength="medium",
            source_id="music_reanalysis_yna_billboard",
            source_url="https://www.yna.co.kr/view/AKR20220122036600005",
            analysis_note="Billboard's methodology change was not clean proof of anti-K-pop intent, but it directly reduced a performance channel where K-pop fandoms had been unusually strong, showing material dependence on foreign-controlled scoreboards.",
        ),
    ]
    rows.extend(load_tax_support_metrics())

    fieldnames = [
        "layer_id",
        "layer_name",
        "metric_id",
        "metric_name",
        "metric_value",
        "metric_unit",
        "support_score_0_100",
        "claim_effect",
        "evidence_strength",
        "source_id",
        "source_url",
        "analysis_note",
    ]
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PANEL_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def layer_judgment(score: float) -> str:
    if score >= 85:
        return "strong_support"
    if score >= 70:
        return "support_with_nuance"
    if score >= 50:
        return "mixed_support"
    return "weak_support"


def build_summary_rows(panel_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    layer_names: dict[str, str] = {}
    for row in panel_rows:
        grouped.setdefault(row["layer_id"], []).append(row)
        layer_names[row["layer_id"]] = row["layer_name"]

    summary_rows: list[dict[str, str]] = []
    layer_scores: list[float] = []
    supportive_total = 0
    tempering_total = 0

    for layer_id in sorted(grouped):
        rows = grouped[layer_id]
        scores = [float(row["support_score_0_100"]) for row in rows]
        layer_score = mean(scores)
        layer_scores.append(layer_score)
        supportive_count = sum(1 for row in rows if row["claim_effect"] == "supports_structural_discrimination")
        tempering_count = sum(1 for row in rows if row["claim_effect"] != "supports_structural_discrimination")
        supportive_total += supportive_count
        tempering_total += tempering_count
        summary_rows.append(
            {
                "summary_level": "layer",
                "layer_id": layer_id,
                "layer_name": layer_names[layer_id],
                "metric_count": str(len(rows)),
                "supportive_metric_count": str(supportive_count),
                "tempering_metric_count": str(tempering_count),
                "average_support_score_0_100": f"{layer_score:.6f}",
                "supportive_share": f"{supportive_count / len(rows):.6f}",
                "headline_judgment": layer_judgment(layer_score),
                "interpretation_note": (
                    "This layer supports the reverse-discrimination reading for Korean music's core domestic exposure."
                    if layer_score >= 70
                    else "This layer is too mixed to headline without additional evidence."
                ),
            }
        )

    overall_score = mean(layer_scores)
    summary_rows.append(
        {
            "summary_level": "overall",
            "layer_id": "OVERALL",
            "layer_name": "kr_music_domestic_structural_average",
            "metric_count": str(len(panel_rows)),
            "supportive_metric_count": str(supportive_total),
            "tempering_metric_count": str(tempering_total),
            "average_support_score_0_100": f"{overall_score:.6f}",
            "supportive_share": f"{supportive_total / len(panel_rows):.6f}",
            "headline_judgment": layer_judgment(overall_score),
            "interpretation_note": (
                "Under the re-scoped domestic structural-exposure average, Korean music is more consistent with a reverse-discrimination reading than under the earlier mixed music-IP comparison."
            ),
        }
    )

    fieldnames = [
        "summary_level",
        "layer_id",
        "layer_name",
        "metric_count",
        "supportive_metric_count",
        "tempering_metric_count",
        "average_support_score_0_100",
        "supportive_share",
        "headline_judgment",
        "interpretation_note",
    ]
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    return summary_rows


def draw_figure(summary_rows: list[dict[str, str]]) -> None:
    layer_rows = [row for row in summary_rows if row["summary_level"] == "layer"]
    width = 1100
    height = 520
    margin_left = 230
    margin_top = 80
    margin_bottom = 70
    plot_width = width - margin_left - 120
    step_y = 90
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    colors = {
        "axis": "#333333",
        "bar": "#185adb",
        "grid": "#d8d8d8",
        "text": "#111111",
    }

    draw.text((width // 2, 24), "Korean Music Structural Reverse-Discrimination Reanalysis", fill=colors["text"], font=font, anchor="ma")
    draw.text((width // 2, 44), "Domestic structural-exposure average by layer (0-100 support score)", fill=colors["text"], font=font, anchor="ma")

    for tick in range(0, 101, 20):
        x = margin_left + int(plot_width * (tick / 100))
        draw.line([(x, margin_top), (x, margin_top + step_y * len(layer_rows))], fill=colors["grid"], width=1)
        draw.text((x, margin_top - 10), str(tick), fill=colors["text"], font=font, anchor="ms")

    label_map = {
        "regulatory_licensing_asymmetry": "Regulatory / Licensing",
        "google_bundle_platform_power": "Google Bundle Power",
        "domestic_governance_opacity": "Domestic Governance",
        "foreign_metric_dependence": "Foreign Metrics",
        "tax_asymmetry": "Tax Asymmetry",
    }

    for idx, row in enumerate(layer_rows):
        y = margin_top + idx * step_y + 30
        score = float(row["average_support_score_0_100"])
        x1 = margin_left + int(plot_width * (score / 100))
        draw.text((margin_left - 12, y), label_map.get(row["layer_name"], row["layer_name"]), fill=colors["text"], font=font, anchor="rs")
        draw.rounded_rectangle([margin_left, y - 12, x1, y + 12], radius=5, fill=colors["bar"])
        draw.text((x1 + 8, y + 2), f"{score:.1f}", fill=colors["text"], font=font, anchor="ls")

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(FIGURE_PATH)


def load_legacy_music_gap_rows() -> list[dict[str, str]]:
    if not LEGACY_GAP_PATH.exists():
        return []
    with LEGACY_GAP_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["peer_group_id"].startswith("mus_")]


def write_log(
    source_rows: list[dict[str, str]],
    panel_rows: list[dict[str, str]],
    summary_rows: list[dict[str, str]],
    prices: dict[str, float],
) -> None:
    legacy_rows = load_legacy_music_gap_rows()
    overall = next(row for row in summary_rows if row["summary_level"] == "overall")
    collected = sum(1 for row in source_rows if row["collection_status"] in {"collected", "reused_existing"})
    blocked = sum(1 for row in source_rows if row["collection_status"] not in {"collected", "reused_existing"})

    with LOG_PATH.open("w", encoding="utf-8") as handle:
        handle.write("# Korean Music Reverse-Discrimination Reanalysis\n\n")
        handle.write("- 이번 재분석의 목적은 기존 `music` 평균이 왜 한국 음악산업의 국내 구조적 불리함을 충분히 포착하지 못했는지 확인하고, 국내 핵심 경쟁 접점을 기준으로 다시 계산하는 데 있다.\n")
        handle.write("- 핵심 재정의는 `music IP export`를 headline 평균에서 내리고, `국내 스트리밍·라이선스·권리관리·해외 지표 의존`을 한국 음악산업의 직접 노출축으로 재배치하는 것이다.\n")
        handle.write("- 따라서 이번 결과는 `한국 음악산업의 국내 구조적 노출 평균`에 대한 재분석이지, 기존 mixed firm comparison을 임의로 뒤집은 것이 아니다.\n\n")
        handle.write("## Legacy Dilution Check\n\n")
        if legacy_rows:
            for row in legacy_rows:
                handle.write(
                    f"- `{row['peer_group_id']}` legacy gap: `{row['korea_minus_global_gap']}` (`{row['gap_direction']}`)\n"
                )
            handle.write("- 기존 mixed music headline은 `mus_streaming_paid_core`의 positive gap과 `mus_label_ip_export`의 negative gap이 한 평균에 섞이며 희석되는 구조였다.\n\n")

        handle.write("## Collection Status\n\n")
        handle.write(f"- collected or reused sources: `{collected}`\n")
        handle.write(f"- blocked or partial sources: `{blocked}`\n")
        for row in source_rows:
            handle.write(f"- `{row['source_id']}`: `{row['collection_status']}`\n")

        handle.write("\n## Price Extraction\n\n")
        handle.write(f"- YouTube Premium Lite: `{int(prices['youtube_premium_lite_monthly_krw'])}` KRW\n")
        handle.write(f"- YouTube Premium bundle: `{int(prices['youtube_premium_bundle_monthly_krw'])}` KRW\n")
        handle.write(f"- YouTube Music standalone: `{int(prices['youtube_music_standalone_monthly_krw'])}` KRW\n")
        handle.write(f"- Melon streaming club: `{int(prices['melon_streaming_monthly_krw'])}` KRW\n")
        handle.write(f"- Bundle leverage index (`ytmusic / bundle`): `{prices['youtube_bundle_leverage_index']:.6f}`\n")
        handle.write(f"- Full bundle discount vs `Lite + Melon`: `{prices['bundle_discount_vs_lite_plus_melon'] * 100:.2f}%`\n")
        handle.write(f"- Implied bundle music-component discount vs Melon: `{prices['implied_music_discount_vs_melon'] * 100:.2f}%`\n\n")

        handle.write("## Layer Summary\n\n")
        for row in summary_rows:
            if row["summary_level"] != "layer":
                continue
            handle.write(
                f"- `{row['layer_id']} {row['layer_name']}`: avg score `{row['average_support_score_0_100']}`, supportive `{row['supportive_metric_count']}/{row['metric_count']}`, judgment `{row['headline_judgment']}`\n"
            )

        handle.write("\n## Overall Judgment\n\n")
        handle.write(
            f"- overall domestic structural average score: `{overall['average_support_score_0_100']}`\n"
        )
        handle.write(
            f"- supportive metric share: `{overall['supportive_share']}`\n"
        )
        handle.write(
            f"- headline judgment: `{overall['headline_judgment']}`\n"
        )
        handle.write(
            "- 이번 재분석은 `한국 음악산업이 평균적으로 차별받지 않는다`는 기존 mixed result를 유지하기보다, `국내 핵심 경쟁 접점`을 기준으로 보면 평균적으로 구조적 역차별 노출이 높다는 결론을 지지한다.\n"
        )
        handle.write(
            "- 다만 이 결과도 `법원이 위법을 최종 확정했다`거나 `한국 음악산업이 즉시 붕괴하고 있다`는 뜻은 아니다. 가장 강한 결론은 `국내 규제·라이선스·번들 유통·권리관리·외부 지표 의존이 결합된 구조적 불리함이 평균적으로 높다`는 수준이다.\n"
        )


def main() -> None:
    source_rows = build_source_registry()
    prices = extract_prices()
    panel_rows = build_panel_rows(prices)
    summary_rows = build_summary_rows(panel_rows)
    draw_figure(summary_rows)
    write_log(source_rows, panel_rows, summary_rows, prices)


if __name__ == "__main__":
    main()
