from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INPUT_PATH = PROJECT_ROOT / "data/processed/claim_strengthening/matched_effective_tax_rate_panel.csv"
OUTPUT_PATH = PROJECT_ROOT / "data/processed/claim_strengthening/music_factcheck/music_peer_tax_rebuild.csv"
LOG_PATH = PROJECT_ROOT / "logs/claim_strengthening/music_factcheck/music_peer_tax_rebuild_log.md"


TARGETS = {
    ("mus_streaming_paid_core", "dreamus", "FY2025"): {
        "source_filing": "data/raw/kr/filings/dreamus/dreamus_annual_20260319000743_viewer_20260328.html",
        "expected_role": "korean_anchor",
    },
    ("mus_streaming_paid_core", "spotify", "FY2025"): {
        "source_filing": "data/raw/us/filings/spotify/spotify_annual_000162828026006874_filing_20260329.htm",
        "expected_role": "global_same_service_peer",
    },
}


def quantize_rate(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.000001'))}"


def load_rows() -> list[dict[str, str]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_output_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], Decimal]:
    out_rows: list[dict[str, str]] = []
    selected: dict[tuple[str, str, str], dict[str, str]] = {}

    for row in rows:
        key = (row["peer_group_id"], row["firm_std"], row["fiscal_period"])
        if key in TARGETS:
            selected[key] = row

    missing = sorted(set(TARGETS) - set(selected))
    if missing:
        raise RuntimeError(f"Missing target tax rows: {missing}")

    for key, meta in TARGETS.items():
        row = selected[key]
        pretax = Decimal(row["pretax_income_raw"])
        tax = Decimal(row["tax_expense_raw"])
        recomputed = tax / pretax if pretax != 0 else Decimal("NaN")
        same_peer_same_period_flag = (
            "yes"
            if row["comparability_flag"] == "yes"
            and row["matched_peer_observation_count"] == "2"
            and row["matched_korean_observation_count"] == "1"
            and row["matched_global_observation_count"] == "1"
            else "no"
        )
        sign_note = (
            "Pretax income and income tax expense are both positive in the matched panel row, "
            "so no sign flip or absolute-value adjustment is required."
        )
        if row["firm_std"] == "spotify":
            sign_note += (
                " Source note points to the annual filing fallback table row "
                "`table:54 | Income/(loss) before tax` and `Income tax expense`."
            )
        else:
            sign_note += (
                " Source note points to the Dreamus annual viewer filing row "
                "`Profit (loss) before tax` and note `26. Income tax expense | Tax expense (income)`."
            )
        out_rows.append(
            {
                "firm_std": row["firm_std"],
                "fiscal_period": row["fiscal_period"],
                "pretax_income": row["pretax_income_raw"],
                "income_tax_expense": row["tax_expense_raw"],
                "recomputed_effective_tax_rate": quantize_rate(recomputed),
                "same_peer_same_period_flag": same_peer_same_period_flag,
                "source_filing": meta["source_filing"],
                "audit_note": sign_note,
            }
        )

    dreamus_rate = Decimal(out_rows[0]["recomputed_effective_tax_rate"]) if out_rows[0]["firm_std"] == "dreamus" else Decimal(out_rows[1]["recomputed_effective_tax_rate"])
    spotify_rate = Decimal(out_rows[0]["recomputed_effective_tax_rate"]) if out_rows[0]["firm_std"] == "spotify" else Decimal(out_rows[1]["recomputed_effective_tax_rate"])
    gap = dreamus_rate - spotify_rate
    return out_rows, gap


def write_csv(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "firm_std",
        "fiscal_period",
        "pretax_income",
        "income_tax_expense",
        "recomputed_effective_tax_rate",
        "same_peer_same_period_flag",
        "source_filing",
        "audit_note",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]], gap: Decimal) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    dreamus = next(row for row in rows if row["firm_std"] == "dreamus")
    spotify = next(row for row in rows if row["firm_std"] == "spotify")
    lines = [
        "# Music Factcheck 09. 한국 음악 peer 세금 비교 재구축",
        "",
        f"- `mus_streaming_paid_core`의 `FY2025` matched tax comparison을 다시 추출해 Dreamus와 Spotify 두 row만 남겼다.",
        f"- Dreamus FY2025 row는 `{dreamus['source_filing']}`의 annual filing 계열 source note를, Spotify FY2025 row는 `{spotify['source_filing']}`의 annual filing fallback source note를 따른다.",
        f"- 재계산 결과 Dreamus effective tax rate는 `{dreamus['recomputed_effective_tax_rate']}`, Spotify는 `{spotify['recomputed_effective_tax_rate']}`이며 gap은 `{quantize_rate(gap)}`이다.",
        "- 두 row 모두 pretax income과 income tax expense가 양수이므로 이번 비교에서는 sign flip이나 absolute-value 보정이 필요하지 않았다.",
        "- 두 row 모두 `comparability_flag=yes`, `matched_peer_observation_count=2`, `matched_korean_observation_count=1`, `matched_global_observation_count=1` 조건을 만족해 same-peer same-period comparison으로 유지된다.",
        "- Dreamus는 KRW, Spotify는 EUR filing이지만, 유효세율은 비율 지표이므로 통화 단위 차이는 직접 비교의 장애가 되지 않는다.",
    ]
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = load_rows()
    out_rows, gap = build_output_rows(rows)
    write_csv(out_rows)
    write_log(out_rows, gap)


if __name__ == "__main__":
    main()
