from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TABLE_INDEX_PATH = ROOT / "outputs/tables/report_ready_table_index.csv"
FIGURE_INDEX_PATH = ROOT / "outputs/figures/report_ready_figure_index.csv"
LOG_PATH = ROOT / "logs/report_asset_selection_log.md"


def path_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


TABLE_SPECS = [
    {
        "report_asset_id": "T08",
        "report_section": "실증 결과 / 기초통계",
        "tex_label": "tab:results_basic_stats",
        "planned_title_kr": "기초통계 및 분위수 요약표",
        "planned_caption_kr": "기초통계 및 분위수 요약표(T08)",
        "existing_primary_file": "outputs/tables/T08_basic_stats_summary.csv",
        "supporting_files": "",
        "candidate_source_files": "data/processed/variable_panel_platform_month.csv|data/processed/variable_panel_platform_quarter.csv|data/processed/variable_panel_title_quarter.csv|data/processed/variable_panel_sector_quarter.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "T08_basic_stats_summary.csv",
        "insertion_order": "1",
        "notes": "변수 패널 4종에서 핵심 변수의 평균, 표준편차, 분위수, 관측치 수를 재집계한 report-ready summary table.",
    },
    {
        "report_asset_id": "T09",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "tab:results_cpii_means",
        "planned_title_kr": "CPII 및 하위 지수 분야별 평균 비교표",
        "planned_caption_kr": "CPII 및 하위 지수 분야별 평균 비교표(T09)",
        "existing_primary_file": "outputs/tables/T09_cpii_sector_mean_comparison.csv",
        "supporting_files": "",
        "candidate_source_files": "data/processed/cpii_panel_sector_quarter.csv|data/processed/subindex_panel_sector_quarter.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "T09_cpii_sector_mean_comparison.csv",
        "insertion_order": "2",
        "notes": "계산 완료된 sector-quarter CPII와 하위지수에서 직접 집계한 분야별 평균 비교표.",
    },
    {
        "report_asset_id": "T10",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "tab:results_cpii_rankings",
        "planned_title_kr": "분야-분기 상위·하위 관측치 순위표",
        "planned_caption_kr": "분야-분기 상위·하위 관측치 순위표(T10)",
        "existing_primary_file": "outputs/tables/T10_cpii_extreme_observations.csv",
        "supporting_files": "",
        "candidate_source_files": "outputs/tables/timeseries_change_summary.csv|data/processed/cpii_panel_sector_quarter.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "T10_cpii_extreme_observations.csv",
        "insertion_order": "3",
        "notes": "시계열 변화 진단과 sector-quarter CPII를 결합한 상위·하위 관측치 순위표.",
    },
    {
        "report_asset_id": "T11-Music",
        "report_section": "실증 결과 / 음악 분야 결과",
        "tex_label": "tab:results_music_estimates",
        "planned_title_kr": "음악 분야 사건연구 및 강건성 추정치 요약표",
        "planned_caption_kr": "음악 분야 사건연구 및 강건성 추정치 요약표(T11-Music)",
        "existing_primary_file": "outputs/tables/regression_results_music.csv",
        "supporting_files": "",
        "candidate_source_files": "",
        "status": "matched_direct",
        "match_type": "direct",
        "proposed_report_filename": "T11_music_estimates.csv",
        "insertion_order": "4",
        "notes": "FE와 event study 결과가 이미 tidy table로 정리되어 있어 본문용 표로 직접 전환 가능.",
    },
    {
        "report_asset_id": "T11-Webtoon",
        "report_section": "실증 결과 / 웹툰 및 스토리 결과",
        "tex_label": "tab:results_webtoon_estimates",
        "planned_title_kr": "웹툰 및 스토리 분야 사건연구 및 강건성 추정치 요약표",
        "planned_caption_kr": "웹툰 및 스토리 분야 사건연구 및 강건성 추정치 요약표(T11-Webtoon)",
        "existing_primary_file": "outputs/tables/regression_results_webtoon.csv",
        "supporting_files": "",
        "candidate_source_files": "",
        "status": "matched_direct",
        "match_type": "direct",
        "proposed_report_filename": "T11_webtoon_story_estimates.csv",
        "insertion_order": "5",
        "notes": "서비스-분기 대체 사양과 stacked event study 결과가 이미 정리돼 있어 본문용 표 구성의 직접 입력으로 적합.",
    },
    {
        "report_asset_id": "T11-Infra",
        "report_section": "실증 결과 / 디지털 인프라 결과",
        "tex_label": "tab:results_infra_estimates",
        "planned_title_kr": "디지털 인프라 분야 사건연구 및 강건성 추정치 요약표",
        "planned_caption_kr": "디지털 인프라 분야 사건연구 및 강건성 추정치 요약표(T11-Infra)",
        "existing_primary_file": "outputs/tables/regression_results_infra.csv",
        "supporting_files": "outputs/tables/regression_results_cross_country.csv",
        "candidate_source_files": "",
        "status": "matched_direct_with_support",
        "match_type": "direct_with_support",
        "proposed_report_filename": "T11_digital_infra_estimates.csv",
        "insertion_order": "6",
        "notes": "국내 서비스-분기 FE 결과는 직접 매칭되고, 국제 비교 해석은 cross-country regression table을 보조 파일로 함께 참조하는 것이 적절함.",
    },
    {
        "report_asset_id": "T12",
        "report_section": "실증 결과 / 정책 시나리오 결과",
        "tex_label": "tab:results_policy_scenarios",
        "planned_title_kr": "정책 시나리오 결과 및 민감도 요약표",
        "planned_caption_kr": "정책 시나리오 결과 및 민감도 요약표(T12)",
        "existing_primary_file": "outputs/tables/policy_scenario_summary.csv",
        "supporting_files": "outputs/tables/policy_sensitivity_summary.csv",
        "candidate_source_files": "",
        "status": "matched_direct_with_support",
        "match_type": "direct_with_support",
        "proposed_report_filename": "T12_policy_scenario_summary.csv",
        "insertion_order": "7",
        "notes": "기준 시나리오 비교는 summary 파일, 민감도 상·하한은 sensitivity 파일을 함께 사용하면 설계서 T12 요구를 충족함.",
    },
]

FIGURE_SPECS = [
    {
        "report_asset_id": "F02",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "fig:results_cpii_timeseries",
        "planned_title_kr": "CPII 시계열 선그래프",
        "planned_caption_kr": "CPII 시계열 선그래프(F02)",
        "existing_primary_file": "outputs/figures/cpii_timeseries_by_sector.png",
        "supporting_files": "",
        "candidate_source_files": "",
        "status": "matched_direct",
        "match_type": "direct",
        "proposed_report_filename": "F02_cpii_timeseries_by_sector.png",
        "insertion_order": "1",
        "notes": "분야별 CPII 시계열과 이동평균을 이미 포함하고 있어 본문 F02에 직접 사용 가능.",
    },
    {
        "report_asset_id": "F03",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "fig:results_cpii_decomposition",
        "planned_title_kr": "하위 지수 분해 누적막대그래프",
        "planned_caption_kr": "하위 지수 분해 누적막대그래프(F03)",
        "existing_primary_file": "outputs/figures/F03_cpii_subindex_decomposition.png",
        "supporting_files": "",
        "candidate_source_files": "data/processed/subindex_panel_sector_quarter.csv|data/processed/cpii_panel_sector_quarter.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F03_cpii_subindex_decomposition.png",
        "insertion_order": "2",
        "notes": "하위지수 평균 기여분을 누적막대로 시각화한 report-ready figure.",
    },
    {
        "report_asset_id": "F04",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "fig:results_cpii_sector_compare",
        "planned_title_kr": "분야별 평균 비교 막대그래프",
        "planned_caption_kr": "분야별 평균 비교 막대그래프(F04)",
        "existing_primary_file": "outputs/figures/F04_cpii_sector_mean_compare.png",
        "supporting_files": "",
        "candidate_source_files": "data/processed/cpii_panel_sector_quarter.csv|data/processed/subindex_panel_sector_quarter.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F04_cpii_sector_mean_compare.png",
        "insertion_order": "3",
        "notes": "분야별 평균 CPII와 표준편차를 함께 보여주는 report-ready bar chart.",
    },
    {
        "report_asset_id": "F05",
        "report_section": "실증 결과 / 음악 분야 결과",
        "tex_label": "fig:results_music_event",
        "planned_title_kr": "음악 분야 사건 전후 변화 그래프",
        "planned_caption_kr": "음악 분야 사건 전후 변화 그래프(F05)",
        "existing_primary_file": "outputs/figures/F05_music_event_study_plot.png",
        "supporting_files": "",
        "candidate_source_files": "outputs/tables/regression_results_music.csv|data/processed/event_study_panel.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F05_music_event_study_plot.png",
        "insertion_order": "4",
        "notes": "음악 분야 event-study 계수와 신뢰구간을 그린 report-ready coefficient plot.",
    },
    {
        "report_asset_id": "F06",
        "report_section": "실증 결과 / 웹툰 및 스토리 결과",
        "tex_label": "fig:results_webtoon_event",
        "planned_title_kr": "웹툰 및 스토리 분야 사건 전후 변화 그래프",
        "planned_caption_kr": "웹툰 및 스토리 분야 사건 전후 변화 그래프(F06)",
        "existing_primary_file": "outputs/figures/F06_webtoon_story_event_study_plot.png",
        "supporting_files": "",
        "candidate_source_files": "outputs/tables/regression_results_webtoon.csv|data/processed/event_study_panel.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F06_webtoon_story_event_study_plot.png",
        "insertion_order": "5",
        "notes": "웹툰 및 스토리 event-study 계수와 신뢰구간을 그린 report-ready coefficient plot.",
    },
    {
        "report_asset_id": "F07",
        "report_section": "실증 결과 / 디지털 인프라 결과",
        "tex_label": "fig:results_infra_scatter",
        "planned_title_kr": "디지털 인프라 비용압력-불평등 관계 그래프",
        "planned_caption_kr": "디지털 인프라 비용압력-불평등 관계 그래프(F07)",
        "existing_primary_file": "outputs/figures/F07_digital_infra_pressure_scatter.png",
        "supporting_files": "",
        "candidate_source_files": "data/processed/variable_panel_sector_quarter.csv|outputs/tables/regression_results_infra.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F07_digital_infra_pressure_scatter.png",
        "insertion_order": "6",
        "notes": "디지털 인프라 sector-country-quarter 관측치를 이용한 비용압력과 CPII의 산포도.",
    },
    {
        "report_asset_id": "F08",
        "report_section": "실증 결과 / 기초통계",
        "tex_label": "fig:results_corr_heatmap",
        "planned_title_kr": "핵심 변수 상관구조 히트맵",
        "planned_caption_kr": "핵심 변수 상관구조 히트맵(F08)",
        "existing_primary_file": "outputs/figures/F08_core_variable_correlation_heatmap.png",
        "supporting_files": "",
        "candidate_source_files": "data/processed/variable_panel_sector_quarter.csv|data/processed/variable_panel_platform_quarter.csv|data/interim/standardized_numeric_panel.csv",
        "status": "matched_derived",
        "match_type": "derived",
        "proposed_report_filename": "F08_core_variable_correlation_heatmap.png",
        "insertion_order": "7",
        "notes": "핵심 raw 변수, 하위지수, CPII 간 상관구조를 시각화한 report-ready heatmap.",
    },
    {
        "report_asset_id": "F09",
        "report_section": "실증 결과 / CPII 산출 결과",
        "tex_label": "fig:results_cpii_robustness",
        "planned_title_kr": "기준 사양-대체 사양 비교 차트",
        "planned_caption_kr": "기준 사양-대체 사양 비교 차트(F09)",
        "existing_primary_file": "outputs/figures/spec_comparison_chart.png",
        "supporting_files": "outputs/tables/spec_robustness_summary.csv",
        "candidate_source_files": "",
        "status": "matched_direct_with_support",
        "match_type": "direct_with_support",
        "proposed_report_filename": "F09_spec_robustness_comparison.png",
        "insertion_order": "8",
        "notes": "시각화 파일과 수치 요약표가 모두 있어 본문 F09와 부록 설명을 동시에 지원함.",
    },
    {
        "report_asset_id": "F10",
        "report_section": "실증 결과 / 정책 시나리오 결과",
        "tex_label": "fig:results_policy_sensitivity",
        "planned_title_kr": "정책 시나리오 민감도 차트",
        "planned_caption_kr": "정책 시나리오 민감도 차트(F10)",
        "existing_primary_file": "outputs/figures/policy_tornado_chart.png",
        "supporting_files": "outputs/tables/policy_sensitivity_summary.csv",
        "candidate_source_files": "",
        "status": "matched_direct_with_support",
        "match_type": "direct_with_support",
        "proposed_report_filename": "F10_policy_scenario_tornado.png",
        "insertion_order": "9",
        "notes": "정책 민감도 토네이도 차트와 low/base/high 수치표가 함께 존재해 F10 요구를 직접 충족함.",
    },
]


def enrich_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        enriched = dict(row)
        primary_exists = path_exists(row["existing_primary_file"]) if row["existing_primary_file"] else False
        supporting_exists = all(
            path_exists(path)
            for path in row["supporting_files"].split("|")
            if path
        )
        candidate_exists = all(
            path_exists(path)
            for path in row["candidate_source_files"].split("|")
            if path
        ) if row["candidate_source_files"] else False

        if primary_exists and candidate_exists:
            enriched["status"] = "matched_derived"
            enriched["match_type"] = "derived"
        elif primary_exists and row["supporting_files"]:
            enriched["status"] = "matched_direct_with_support"
            enriched["match_type"] = "direct_with_support"
        elif primary_exists:
            enriched["status"] = "matched_direct"
            enriched["match_type"] = "direct"
        elif candidate_exists:
            enriched["status"] = "missing_but_derivable"
            enriched["match_type"] = "missing"

        enriched["existing_primary_exists"] = "yes" if primary_exists else "no"
        enriched["supporting_files_exist"] = "yes" if supporting_exists else "no"
        enriched["candidate_source_files_exist"] = "yes" if candidate_exists else "no"
        out.append(enriched)
    return out


def build_log(table_rows: list[dict[str, str]], figure_rows: list[dict[str, str]]) -> str:
    table_status = {}
    figure_status = {}
    for row in table_rows:
        table_status[row["status"]] = table_status.get(row["status"], 0) + 1
    for row in figure_rows:
        figure_status[row["status"]] = figure_status.get(row["status"], 0) + 1

    direct_tables = [row["report_asset_id"] for row in table_rows if row["status"].startswith("matched")]
    missing_tables = [row["report_asset_id"] for row in table_rows if row["status"] == "missing_but_derivable"]
    direct_figures = [row["report_asset_id"] for row in figure_rows if row["status"].startswith("matched")]
    missing_figures = [row["report_asset_id"] for row in figure_rows if row["status"] == "missing_but_derivable"]

    insertion_order_tables = [
        f"- `{row['insertion_order']}` | `{row['report_asset_id']}` | {row['planned_title_kr']} | `{row['status']}`"
        for row in sorted(table_rows, key=lambda item: int(item["insertion_order"]))
    ]
    insertion_order_figures = [
        f"- `{row['insertion_order']}` | `{row['report_asset_id']}` | {row['planned_title_kr']} | `{row['status']}`"
        for row in sorted(figure_rows, key=lambda item: int(item["insertion_order"]))
    ]

    gap_lines = []
    if missing_tables or missing_figures:
        gap_lines.extend(
            [
                "- 아직 미생성 report-ready 자산이 남아 있으며, `missing_but_derivable` 판정 파일은 source panel에서 추가 파생이 필요하다.",
                f"- 남은 table gaps: `{missing_tables}`",
                f"- 남은 figure gaps: `{missing_figures}`",
            ]
        )
    else:
        gap_lines.extend(
            [
                "- 설계된 `T08~T12`, `F02~F10` 자산이 모두 report-ready 파일로 존재한다.",
                "- `T08~T10`, `F03~F08`은 processed/result panel에서 파생 생성된 derived asset으로 분류된다.",
            ]
        )
    gap_lines.append("- `T11-Infra`는 국내 인프라 FE 결과와 cross-country 보조 회귀를 함께 봐야 해서 `regression_results_cross_country.csv`를 support file로 같이 쓰는 편이 안전하다.")

    return "\n".join(
        [
            "# Report Asset Selection Log",
            "",
            "## Summary",
            f"- Table status split: `{table_status}`",
            f"- Figure status split: `{figure_status}`",
            f"- Directly matchable tables: `{direct_tables}`",
            f"- Missing-but-derivable tables: `{missing_tables}`",
            f"- Directly matchable figures: `{direct_figures}`",
            f"- Missing-but-derivable figures: `{missing_figures}`",
            "",
            "## Naming Rule",
            "- 본문 삽입용 파일명은 설계 ID를 앞에 두고 `T08_...`, `F02_...` 형식으로 통일한다.",
            "- 제목은 `planned_title_kr`를 기준으로 통일하고, 괄호 안의 설계 ID는 caption에서만 유지한다.",
            "- 이미 생성된 실제 파일은 그대로 두고, 이번 인덱스에서는 `proposed_report_filename`만 제안한다.",
            "",
            "## Table Insertion Order",
            *insertion_order_tables,
            "",
            "## Figure Insertion Order",
            *insertion_order_figures,
            "",
            "## Main Gaps",
            *gap_lines,
        ]
    )


def main() -> None:
    table_rows = enrich_rows(TABLE_SPECS)
    figure_rows = enrich_rows(FIGURE_SPECS)

    table_fieldnames = [
        "report_asset_id",
        "report_section",
        "tex_label",
        "planned_title_kr",
        "planned_caption_kr",
        "status",
        "match_type",
        "existing_primary_file",
        "existing_primary_exists",
        "supporting_files",
        "supporting_files_exist",
        "candidate_source_files",
        "candidate_source_files_exist",
        "proposed_report_filename",
        "insertion_order",
        "notes",
    ]
    figure_fieldnames = table_fieldnames[:]

    write_csv(TABLE_INDEX_PATH, table_rows, table_fieldnames)
    write_csv(FIGURE_INDEX_PATH, figure_rows, figure_fieldnames)
    LOG_PATH.write_text(build_log(table_rows, figure_rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
