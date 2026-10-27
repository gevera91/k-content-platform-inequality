# 데이터 안내

이 자료는 **2026년 10월 27일 한국어 최종보고서**의 분석에 사용한 고정 데이터와 결과표를 공개한 재현 패키지다. 공개자료에서 추출·정리한 수치, 변수 정의, 비교 기준, 출처 연결기록을 함께 제공한다. 보고서 개정일과 각 관측의 기준시점은 다르므로 `year_quarter`, `month`, `access_date`를 확인한다.

## 먼저 볼 파일

| 목적 | 파일 | 내용 |
|---|---|---|
| 전체 파일·변수 확인 | [`publication/data_catalog.csv`](../publication/data_catalog.csv) | 실제 배포 파일별 행 수, 열 이름, 크기, SHA-256 |
| 지수의 원입력 | [`variable_panel_sector_quarter.csv`](../data/processed/variable_panel_sector_quarter.csv) | 분야·국가·분기별 159행. 결측·자료 구축 상태와 원변수를 함께 보존 |
| 분야별 CPII | [`cpii_panel_sector_quarter.csv`](../data/processed/cpii_panel_sector_quarter.csv) | 전체 19행 중 CPII가 산출된 14개 분야·분기 관측 |
| 국가·기업 비교 | `data/processed/cpii_panel_*country_quarter*.csv` | 기준 사양과 Alt A/B의 점수·관측범위·결측 정보 |
| 한국시장 비교사례 | [`signed_reverse_discrimination_extended.csv`](../data/processed/claim_strengthening/signed_rebuild/signed_reverse_discrimination_extended.csv) | 11개 서비스 비교사례의 핵심·확장 방향점수와 관측축 수 |
| 음악 상품 가격 | [`platform_product_price_panel.csv`](../data/processed/claim_strengthening/music_econ_extension/platform_product_price_panel.csv) | 상품·시장·관측월별 16개 가격 기록과 공식 출처 |
| 정책 시나리오 | `data/processed/policy_simulator_*.csv`, `outputs/tables/policy_*.csv` | 고정 기준 입력, 전달계수와 기존 시나리오 출력 |
| 기준값을 맞춘 정책 비교 | [`outputs/tables/review_20260915/`](../outputs/tables/review_20260915/) | 기준값 분해, 공통 셀 비교, 불리한 민감도 조합, 사례 방향의 강건성 |
| 결과에서 입력으로 추적 | [`row_level_lineage_table.csv`](../data/processed/row_level_lineage_table.csv) | 결과행·계산 단계·입력행을 연결한 10,211개 기록 |
| 변수 정의·단위 | [`cpii_simulator_variable_dictionary.csv`](../data/registry/cpii_simulator_variable_dictionary.csv) | 변수별 정의, 변환, 방향, 단위, 비교기준 요건 |
| 원천 확인 | [`source_manifest.csv`](../data/registry/source_manifest.csv) | 원천 URL, 접근일, 출처 식별자와 수집 상태 |

실행 순서와 검증 범위는 [재현 안내](REPRODUCING.md)를 따른다. `outputs/`는 보고서에 사용한 고정 결과이며, 새 실행 결과와 비교하는 기준으로 사용한다.

## 자료 구조와 연결키

- `data/interim/`: 공개 원천에서 추출·표준화한 수치, 공시·시장자료 인덱스, 병합 전 패널. 이름에 `raw_panel`이 있어도 원문 전체가 아니라 추출된 표형 자료다.
- `data/processed/`: 분석 패널, CPII, 정책 입력, 한국시장 비교사례, 강건성 분석과 출처 연결기록.
- `data/registry/`: 국가·기업·서비스 코드표, 변수 사전, 사건·비교기준·원천 목록.
- `outputs/tables/`, `outputs/figures/`: 보고서의 표·그림과 시뮬레이터 기대 출력.

주요 차원은 `sector_std`(분야), `country_std`(시장·국가), `firm_std`(기업), `service_std`(서비스), `year_quarter`(분기)다. 분야 코드는 `music`, `webtoon_story`, `digital_infra`다. 표의 집계 수준에 맞춰 연결키를 선택한다. 예를 들어 국가별 분야 패널은 분야·국가·분기로, 기업 패널은 기업·국가·분기로 비교한다. 기업 코드와 서비스 코드는 서로 다른 단위다. 코드 대응은 `entity_dictionary_*.csv`와 `firm_country_service_matrix.csv`에서 확인한다.

원자료가 없는 칸은 빈 값으로 남아 있다. 빈 값을 0으로 바꾸면 비용·위험과 점수의 의미가 달라진다. `observed_any_flag`, `construction_status`, `cpii_status`, `available_variable_count`와 관련 결측 열을 함께 읽는다. 159행은 관측 가능한 분기·국가 조합을 포함한 패널 행 수이며, 완전 관측 159개를 뜻하지 않는다.

## 실행 사양의 10개 변수

현재 실행 사양은 제도 3개, 위험 4개, 시장 3개 변수다. 아래 방향은 **부담점수에 반영되는 방향**이며, 단위 변환과 고정 기준분포를 적용하기 전의 입력 정의는 변수 사전에 명시되어 있다.

| 하위지수 | 변수 | 입력 단위 | 부담 방향 |
|---|---|---|---|
| 제도 `I_reg` | `effective_tax_rate_gap` 유효세율 격차 | 소수 비율 | 높을수록 증가 |
| 제도 `I_reg` | `network_cost_ratio` 네트워크 비용률 | 소수 비율 | 높을수록 증가 |
| 제도 `I_reg` | `infra_dependency_ratio` 인프라 비용·해외의존 결합비율 | 소수 비율 | 높을수록 증가 |
| 위험 `I_risk` | `funding_cost_spread` 자금조달비용 스프레드 | 소수 비율 | 높을수록 증가 |
| 위험 `I_risk` | `ip_assetization_gap` IP 자산화 결손 | 소수 비율 | 높을수록 증가 |
| 위험 `I_risk` | `investment_recovery_ratio` 투자 회수율 | 배수 | 높을수록 감소 |
| 위험 `I_risk` | `cashflow_recovery_ratio` 세전이익 기반 회수 대리값 | 배수 | 높을수록 감소 |
| 시장 `I_market` | `cross_market_transfer_index` 시장간 전이 대리지수 | 0–1 지수 | 높을수록 증가 |
| 시장 `I_market` | `foreign_dependency_ratio` 해외의존비율 | 소수 비율 | 높을수록 증가 |
| 시장 `I_market` | `outflow_to_capex_ratio` 비용 대비 설비투자 압박률 | 배수 | 높을수록 증가 |

소수 비율에서 1%는 `0.01`이다. 격차 변수의 음수는 유효한 값이며 자동으로 0 처리하지 않는다. `creator_share_ratio`와 `bundle_leverage_index`는 사전에 포함된 비활성 후보로, 현재 10개 변수 점수에는 들어가지 않는다. 보고서의 광의 설계와 실제 실행 변수 목록을 구분한다.

## 숫자의 척도와 비교 기준

1. **CPII(0–100):** 고정 기준분포에서 정규화한 부담 관련 변수의 집계값. 기준 사양·가용 하위지수·비교기간을 함께 확인한다.
2. **한국시장 방향점수(−1–1):** 서비스 비교사례에서 부담이 어느 쪽에 귀착되는지를 축별 코딩으로 정리한 값. CPII와 별도의 척도다.
3. **정책 시나리오 차이:** 지정된 입력과 전달계수에서 계산한 변화. 원래 시나리오 표와 기준값을 맞춘 비교표는 각각의 파일명과 계산 기준에 따라 읽는다.

시뮬레이터의 `data/processed/cpii_simulator/examples/`는 사용법과 계산 검증을 위한 **합성 기업·합성 노출액**이다. 등록된 `BM-DIGITAL-CONTENT-2025Q4` 역시 `synthetic_only` 비교기준이다. 실제 멜론·스포티파이의 기업 데이터로 해석하지 않는다. 실제 기업을 입력할 때에는 공통 시장·기간·변수 산식과 비교군 출처를 등록해야 한다. 입력·출처·경제적 노출액 스키마는 `data/registry/cpii_*.csv`를 따른다.

## 원천 접근과 재현 범위

공개 패키지는 **고정된 분석 입력에서 지수·비교표·민감도를 다시 계산하는 오프라인 재현**을 지원한다. 외부 기관의 PDF·웹페이지·공시 원문 전체와 다운로드 시도 로그는 포함하지 않는다. 원문을 확인하거나 새 시점 자료를 수집할 때에는 `source_manifest.csv`의 URL과 접근일, 해당 기관의 이용조건을 따른다. 인증이 필요한 API의 키는 배포 자료에 없다.

`source_manifest.csv`, `project_manifest.csv`와 일부 출처 연결 열의 `data/raw/...`, `logs/...` 경로는 당시 원천·처리 기록을 식별하는 **역사적 경로**다. 이 경로가 공개 저장소에 모두 존재한다는 뜻은 아니다. 실제 배포 파일의 목록은 `publication/data_catalog.csv`가 기준이다. 원천 재수집은 원문 변경·삭제와 서비스 접근조건의 영향을 받으므로, 현재 웹사이트를 다시 수집한 결과와 이 보고서의 고정 자료를 구분해 보관한다.

표·패널의 수치와 결측 표시는 원본을 유지했다. 공개 패키지 선정 및 무결성 검토 기록은 [`publication/data_audit.json`](../publication/data_audit.json)에 있다. 계약서, 고객 제안서의 상세 요구사항, 문장 편집표와 작업자별 내부 진행표는 연구 결과 재현에 필요하지 않아 배포 대상에서 제외했다. 출처·코딩·관측범위·음수 사례와 강건성에 관한 분석 기록은 보존했다.

자료를 인용할 때에는 보고서와 저장소의 고정 릴리스 또는 커밋을 함께 명시한다. 원천 수치의 출처 표기는 해당 기관·공시·상품 안내에 대한 인용을 대체하지 않는다.
