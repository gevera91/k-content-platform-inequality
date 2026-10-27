# K-콘텐츠 플랫폼 생태계: 보고서와 공개 재현 패키지

**전성민(가천대학교) · 강형구(한양대학교)**  
한국어 최종보고서 개정일: **2026년 10월 27일** · 공개 패키지: **v1.0.0**

음악, 웹툰·스토리, 디지털 인프라에서 플랫폼의 구조적 부담을 측정한 연구의 보고서·데이터·코드·스프레드시트를 함께 제공한다. 멜론–스포티파이 비교, CPII, 한국시장 비교사례, 정책 시나리오와 강건성 분석을 포함한다.

| 바로 이용하기 | 링크 |
|---|---|
| **최종 한국어 보고서 — 168쪽** | [PDF 열기](reports/kakao_enter.pdf) |
| **전체 재현 패키지 다운로드** | [고정 릴리스 v1.0.0](https://github.com/gevera91/k-content-platform-inequality/releases/tag/v1.0.0) |
| **Google Sheets 비교기** | [공개 스프레드시트 열기](https://docs.google.com/spreadsheets/d/1qrbtViewFJKwZeBRDOmfXA8kzCt3vyrlDmGcW93DgTY/edit) |
| **Excel 비교기와 입력 템플릿** | [spreadsheet/](spreadsheet/) |
| **재현 실행 방법** | [REPRODUCING.md](docs/REPRODUCING.md) |
| **데이터·변수·출처 안내** | [DATA.md](docs/DATA.md) · [파일별 데이터 카탈로그](publication/data_catalog.csv) |

**공개 전 검증:** 새 Python 3.12 가상환경에서 전체 15개 계산 단계를 실행했다. 보존 결과표 49개와 수치 셀 75,305개가 일치했고, 테스트 83개를 통과했다. [실행 검증 기록](publication/REPLICATION_VALIDATION.json)에서 단계별 결과와 보고서 핵심 수치 대조를 확인할 수 있다.

## 연구자가 시작하는 순서

1. 보고서의 요약과 관심 분야를 읽는다. 보고서 부록 F에는 스프레드시트 사용 설명서가 있다.
2. Google Sheets를 열고 **파일 → 사본 만들기**로 개인 작업본을 만든다. 공개 원본은 열람용이다. 사용법과 Google Sheets 검증 기록은 [여기](docs/GOOGLE_SHEETS.md)에 있다.
3. 아래 명령으로 저장소를 내려받고 고정 데이터에서 분석을 재실행한다. 새 결과는 별도 작업 폴더에 기록되며 공개 기준 결과를 덮어쓰지 않는다.

```bash
git clone https://github.com/gevera91/k-content-platform-inequality.git
cd k-content-platform-inequality
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/verify_publication.py
python scripts/replicate.py --profile full --output-dir replication_runs/full
```

Windows에서는 가상환경 활성화에 `.venv\Scripts\activate`를 사용한다. 출력 폴더는 새 경로를 지정한다. 빠른 확인은 `--profile core`, 전체 검증은 `--profile full`을 사용한다. 실행 결과, 보존 값과의 비교, 검사는 출력 폴더의 `replication_summary.json`에서 확인한다. 정확한 실행 범위와 기대 결과는 [재현 안내](docs/REPRODUCING.md)에 정리했다.

## 무엇을 재현하는가

고정된 분석 입력에서 지수와 하위지수, 정책 시나리오, 한국시장 사례 비교 및 합성 기업 비교기의 계산을 다시 수행한다. 보존된 결과표와 새 계산을 비교하여 검증하며, 전체 프로필은 추가 분석과 기존 수치 검사를 함께 실행한다. 원천기관 웹사이트의 현재 상태에 의존하지 않고 계산을 점검할 수 있다.

보고서 개정일은 관측자료의 기준일과 다르다. 패널의 관측기간, 가격표의 관측월, 원천 접근일은 데이터에 함께 기록되어 있다. 원천 재수집용 코드와 출처 레지스트리도 제공하되, 외부기관의 원문 PDF·웹페이지 전체는 패키지에 포함하지 않는다. 원문 확인과 신규 수집은 기록된 공식 출처를 이용한다.

## 스프레드시트와 실제 기업 분석

Google Sheets와 XLSX는 같은 CPII 기업 비교기 v2를 제공한다. 14개 시트에 입력, 기업 비교, 경제적 노출액, 민감도, 출처 및 검증 기능이 들어 있다. 동봉 기업과 등록 비교기준은 **계산 재현을 위한 합성 예시**다. 멜론·스포티파이의 실제 기업 점수를 자동으로 조회하는 기능은 없다. 실제 기업 분석에는 시장·기간을 맞춘 자료와 비교기준을 등록한다.

보고서의 CPII(0–100), 사례 방향점수(−1–1), 정책 시나리오 점수 차이는 각각의 계산 정의를 따른다. 파일별 정의·단위·결측 처리와 출처는 [데이터 안내](docs/DATA.md), 계산과 입력 절차는 [비교기 안내](spreadsheet/CPII_Comparator_User_Guide.md)를 참고한다.

## 저장소 구조

```text
reports/                  확정 한국어 보고서 PDF
kakao_enter.tex           메인 TeX; 스타일·부록 소스는 같은 위치
data/interim/             공개자료에서 추출·표준화한 중간 패널
data/processed/           고정 분석 입력과 분석 패널
data/registry/            변수 사전·사건·비교기준·원천 목록
scripts/                  분석 코드와 재현 실행 도구
tests/                    계산·분해·민감도·워크북 검사
outputs/tables/           보고서와 비교기의 보존 결과표
outputs/figures/          보고서 그림
spreadsheet/              XLSX·입력 템플릿·사용 설명서
docs/                     재현·데이터·Google Sheets·TeX 안내
publication/              카탈로그·체크섬·공개 검증 기록
```

TeX 입력 파일과 글꼴 확인, PDF 재빌드는 [BUILD_REPORT.md](docs/BUILD_REPORT.md)를 따른다. `reports/`의 확정 PDF와 재빌드 결과는 별도로 보관한다.

## 인용과 재사용

> 전성민·강형구 (2026). *K-콘텐츠 플랫폼 생태계의 구조적 불평등 계량화 및 정책 대안 연구*. 2026년 10월 27일 개정본. 공개 재현 패키지 v1.0.0.

데이터나 코드를 사용한 연구는 보고서와 함께 릴리스 태그 또는 커밋, 변경한 분석 조건을 명시한다. [CITATION.cff](CITATION.cff)는 기계 판독용 서지이며, [REUSE.md](REUSE.md)에 연구 재현을 위한 재사용 범위를 정리했다. 오류 제보와 재현 결과는 이 저장소의 Issues를 이용한다.

## English quick start

This repository accompanies the **168-page Korean final report** on structural burdens in music, webtoon/story and digital-infrastructure platforms. It includes frozen numerical datasets, source registries, portable analysis code, archived outputs, the TeX sources, and a public Google Sheets/XLSX CPII comparator. Run the commands above for offline replication after installing the pinned Python dependencies. The spreadsheet's bundled company observations are synthetic examples. Cite the authors, report revision and exact release or commit used in your research.
