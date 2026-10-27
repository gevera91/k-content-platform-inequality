# 분석 재현 안내 / Reproducing the analysis

이 저장소는 한국어 최종보고서의 관측 시점에 고정한 데이터와 계산 코드를 제공합니다. 아래 명령은 공개 웹사이트를 다시 호출하지 않고 보존된 분석 패널에서 결과를 재계산합니다. API 키는 필요하지 않습니다.

## 1. 실행 환경

Python 3.12를 권장합니다. 저장소를 내려받은 뒤 루트에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/replicate.py --profile full --output-dir replication_runs/full
```

Windows에서는 가상환경을 `.venv\Scripts\activate`로 활성화합니다. 의존성 설치에는 인터넷이 필요하지만 설치 후 분석은 오프라인으로 실행됩니다. `requirements.txt`에는 검증 환경의 NumPy와 Pillow 버전을 고정했습니다. 기업 비교기의 수치 계산은 Python 표준 라이브러리를 사용합니다.

출력 경로가 이미 있으면 덮어쓰지 않습니다. 반복 실행할 때는 다른 경로를 지정하거나 `--output-dir`을 생략해 실행시각별 폴더를 만듭니다.

## 2. 실행 결과 확인

`replication_runs/full/replication_summary.json`에서 `status: PASS`를 확인합니다. 각 명령의 종료 코드, 재생성한 표, 대조한 수치 셀 수, 보고서 핵심 수치 확인 결과가 기록됩니다. `logs/`에는 명령별 로그가, `workspace/`에는 실제 재생성된 표와 그림이 있습니다. 저장소에 보존한 입력과 기준 결과는 변경하지 않습니다.

CSV는 열 이름·행 수·행 순서를 대조하고, 문자값은 일치 여부를 확인합니다. 숫자는 절대오차 `1e-8`, 상대오차 `1e-10`으로 비교합니다. 보고서에 반올림해 제시한 평균값은 해당 소수 자릿수에 맞는 허용오차를 적용합니다. 그림은 같은 계산 결과로 재생성되지만 폰트와 렌더러에 따라 이미지 바이트가 달라질 수 있으므로 수치 표를 검증 기준으로 삼습니다.

## 3. 두 가지 실행 범위

| 명령 | 재계산 내용 |
|---|---|
| `python scripts/replicate.py --profile core` | 하위지수와 CPII, 정책 시나리오, 기준값 재구성 차이를 분리한 정책 비교, 11개 사례의 축 제외·가중치 민감도, 합성 기업 비교기 |
| `python scripts/replicate.py --profile full` | core와 함께 대체 사양 A/B, 국가·기업 비교, 시계열, 분야별 회귀·사건연구, Ofcom 대리지표 민감도, 사전추세 및 위약 검정 |

`make replicate`는 전체 범위를 실행합니다. `make test` 또는 `python -m unittest discover -s tests -v`는 수치 엔진·비교조건·분해·경제적 노출액·민감도·보고서 검토 계산의 테스트를 실행합니다. `--skip-tests`는 테스트만 생략하며 재계산과 기준 결과 대조는 계속 수행합니다.

## 4. 보고서와 계산의 연결

| 보고서 내용 | 주요 입력 | 재계산 코드 / 결과 |
|---|---|---|
| 분야별 CPII와 하위지수 | `data/processed/variable_panel_*` | `build_subindex_panels.py`, `build_cpii_panels.py`; `data/processed/cpii_panel_*` |
| 정책 시나리오와 민감도 | `policy_simulator_baseline_inputs.csv`, `policy_simulator_calibrated_parameters.csv` | `build_policy_scenarios.py`; `outputs/tables/policy_*` |
| 동일 입력에서 NET 감소 폭, 불리한 조합에서 상대 우위 | 위 정책 입력과 결과표 | `review_strengthening_20260915.py`; `outputs/tables/review_20260915/` |
| 멜론–스포티파이 및 한국시장 방향 사례 | `T_signed_korea_market_case_studies.csv`의 관측축 코딩 | 같은 검토 코드가 축 값으로 점수를 재구성하고 축 제외·가중치 범위를 계산 |
| 국가·기업·공통기간 비교와 대체 사양 | 보존된 CPII 패널 | `build_country_comparison_tables.py`, `build_firm_comparison_tables.py`, `build_alt_spec_cpii_panels.py`, `build_spec_robustness.py` |
| 회귀·사전추세·위약 검정 | 월·분기 변수 패널과 `event_study_panel.csv` | `run_sector_regressions.py`, `scripts/claim_strengthening/build_claim_*` |
| 기업 입력형 비교기 | 동봉 합성 예시, 10개 활성 변수와 고정 정규화 기준 | `scripts/cpii_simulator/`; `outputs/tables/cpii_simulator/examples/` |

공통기간 평균, 분야별 전체기간 평균, 정책 점수 변화, 멜론–스포티파이 방향점수는 실행 영수증의 `report_claims`에서 별도로 확인합니다. 서로 다른 척도와 기간을 합치지 않습니다.

## 5. 기업 비교기만 실행하기

```bash
python -m scripts.cpii_simulator.compare \
  data/processed/cpii_simulator/examples/fictional_companies.csv \
  --output-dir replication_runs/comparator \
  --feature-ranges data/processed/cpii_simulator/examples/fictional_feature_ranges.csv
```

예시 기업은 합성자료입니다. 실제 멜론·스포티파이의 기업 점수로 사용하지 않습니다. 실제 기업 적용에는 동일한 서비스·시장·기간의 변수, 출처 기록, 적합한 비교기준이 필요합니다. 계산·입력 규칙은 스프레드시트와 최종보고서의 사용 설명서 부록에 설명되어 있습니다.

배포된 XLSX에는 수식과 형식이 포함되어 있습니다. Google Sheets에서는 공개 원본을 자신의 드라이브에 복사하여 입력합니다. Python 엔진은 XLSX·Google Sheets와 독립적으로 재현할 수 있습니다. `scripts/cpii_simulator/`에 남긴 원래 `.mjs` 파일은 통합문서 제작 경위를 보존한 소스이며, 일부 파일은 제작 환경의 artifact 라이브러리를 사용합니다. 이 선택적 제작 도구는 오프라인 수치 재현 명령의 의존성이 아닙니다.

## 6. 자료 수집과 재현의 범위

기본 실행은 공개자료에서 구축해 보존한 변수 패널부터 시작합니다. 원천 PDF·웹페이지의 수기 판독이나 출처 판정까지 새로 자동 수행했다는 의미는 아닙니다. `data/registry/source_manifest.csv`와 `docs/DATA.md`에서 출처, 관측·접근 시점, 단위와 구성방식을 확인할 수 있습니다.

`collect_*`, `thicken_*` 및 다른 `build_*` 소스는 원자료 갱신과 확장 분석을 위해 함께 제공합니다. 일부 수집 경로는 원천기관의 API 자격, 현재 서비스 구조, 또는 이 저장소에 재배포하지 않은 원본 파일을 필요로 합니다. 따라서 이들 코드를 현재 날짜로 실행하는 것은 동결된 보고서의 재현과 별도의 갱신 작업입니다. 선택적 수집 의존성은 `requirements-sources.txt`에 구분했습니다.

`publication/REPLICATION_VALIDATION.json`에는 공개 전 실제 실행의 검증 결과를 보존합니다. Python 3.12의 새 가상환경에서 고정한 의존성만 설치한 뒤 전체 15단계를 실행하여 **49개 기준 CSV, 수치 셀 75,305개, 보고서 핵심 확인사항 20개, 테스트 83개**가 모두 통과했습니다. 빠른 core 실행도 29개 기준 CSV와 수치 셀 28,432개를 대조해 통과했습니다. 기대하는 기준 파일이 빠지거나 재생성되지 않으면 실행을 실패로 판정합니다.

기본 실행에서 재계산하지 않은 보조 표도 `outputs/tables/`에 남아 있으며, 해당 분석 소스를 별도로 검토·실행할 수 있습니다.

## English quick start

Use Python 3.12, install `requirements.txt`, then run `python scripts/replicate.py --profile full`. The runner copies the released inputs and source code into an isolated workspace, regenerates the numerical tables, compares them against the archived references, and runs the test suite. Check `replication_summary.json` for `PASS`. No network access or API credentials are needed after dependency installation. Frozen-input replication is distinct from collecting new observations from the original providers. The workbook examples are synthetic.
