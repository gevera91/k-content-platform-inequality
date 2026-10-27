# CPII 기업 비교기 v2 사용 안내

배포일: 2026-09-15. 연구용 베타.

- 통합문서: `CPII_COMPARATOR_XLSX_V2.0.0`
- 점수 방법론: `CPII_FIRM_INPUT_EQW_V1` 유지
- 고정 기준분포: `POOL_SCQ_P01_P99_EMP_RANK_V1` 유지

## 먼저 확인할 제한

동봉된 비교기준은 **합성 예시 전용 1건**이다. 실제 회사명을 입력한다고 실제 기업의 자료가 검색되지는 않는다. 실제 기업에 적용하려면 분야·분기별 비교군과 산식, 원천 해시를 등록하고 통합문서를 다시 생성해야 한다. 합성 입력 표식을 실제 기업에 붙여 이 제한을 우회하면 안 된다.

159개 기준행 중 활성 10개 변수를 모두 관측한 행은 2개다. 따라서 CPII는 변수별 주변 기준분포 위치를 합친 점수이며 기업의 경험적 백분위가 아니다. 저지원 변수인 시장간 전이와 해외의존의 유효가중치는 합계 22.22%다. 점수는 위법성·손해액·인과효과의 판정이 아니다.

## 사용 순서

1. `01_INPUT_COMPANIES`의 파란 입력 셀에 기업별 값과 비교조건을 입력한다. 예시를 수정하면 그 입력에 맞추어 다시 계산된다.
2. `07_INPUT_PROVENANCE`에 변수별 출처·기준일·산식을 기록한다. 시트 기록만으로 출처의 진위가 자동 확인되지는 않는다.
3. 금액 해석이 필요할 때만 `02_INPUT_ECON_BASES`에 경제 노출액을 입력한다.
4. `03_COMPARE_2`에서 서로 다른 두 관측 ID를 선택한다. `비교 가능` 상태에서 총점, 세 하위지수, 변수별 기여도를 차례로 확인한다.
5. `04_COMPARE_N`에서 동일 비교집단 내 순위를 확인한다. 100개 관측까지 입력 가능하며 화면의 차이 행렬은 앞의 30개 관측까지다.
6. `05_ECON_INTERPRET`에서 채널별 상당액 또는 가정 기반 시나리오 금액을 확인한다. 금액 행을 합산하지 않는다.
7. `06_SENSITIVITY`의 네 가지 방법 사양과 `99_QA_AUDIT`의 검증 상태를 확인한다.

## 입력 단위와 변수

각 관측은 기업-서비스-시장-분기 한 행이다. 모든 활성 변수 10개가 필요하며 빈 값과 0은 다르다. 비율 1%는 `0.01`, 배수 3배는 `3`이다. 경고 범위를 벗어난 유한값은 검토 대상으로 표시되며 무조건 0이나 결측값으로 대체되지 않는다.

- `effective_tax_rate_gap`: 법인세비용/양의 세전이익에서 같은 분야·분기 비한국 비교군 중앙값을 차감한 값.
- `network_cost_ratio`: 망·클라우드·CDN 비용/매출. 국내외 차감 전 비용률.
- `infra_dependency_ratio`: 망비용률과 해외의존비율의 곱.
- `funding_cost_spread`: 이자비용/이자부부채에서 공통 비한국 비교기준을 차감한 값. 연율인지 분기율인지 반드시 기록.
- `ip_assetization_gap`: 비한국 비교군 무형자산/매출 중앙값에서 기업의 같은 비율을 뺀 값. IP 담보가능성 자체의 직접 측정값은 아님.
- `investment_recovery_ratio`: 매출/콘텐츠 투자액. 웹툰 역순위 대체값 사용 시 별도 표시.
- `cashflow_recovery_ratio`: 세전이익/콘텐츠 투자액의 회수 대리값. 영업현금흐름 비율과 구별. 작품 순위 대체경로 사용 시 별도 표시.
- `cross_market_transfer_index`: 음악의 번들·해외의존·차트 점유 결합값 또는 웹툰 번역작 역순위 대리값. 서로 다른 구축방식의 기계적 혼용 금지.
- `foreign_dependency_ratio`: 해외 트래픽·인프라 의존 또는 대응 대리값. 기업 노출과 시장공통 노출의 구별 필요.
- `outflow_to_capex_ratio`: 망·클라우드 비용/설비투자. 실제 해외 지급액으로 식별된 값이라는 뜻은 아님.

`creator_share_ratio`와 `bundle_leverage_index`는 기준표본 지원 부족으로 비활성이며 10개 필수 변수에 포함되지 않는다. 자세한 단위·경고 범위·정의는 `data/registry/cpii_simulator_variable_dictionary.csv`의 `operational_definition`을 사용한다. 이 사전의 과거 보고서 불일치 표시는 v1 점검 당시의 변경 이력이며, 현재 보고서의 실행 정의는 그 점검 결과를 반영한 상태다.

## 비교조건과 검증

- `observation_id`: 영문 대문자, 숫자, 하이픈, 밑줄, 마침표만 허용한 1~64자 고유 ID. `company_name`은 한국어 등 자유 입력.
- `sector`, `service_scope`, `focal_market`, `reporting_period`, `benchmark_id`: 같은 집단에서 대소문자까지 일치할 필드. 앞뒤 공백 및 불필요한 중복 공백 금지. `reporting_period`는 `2025Q4` 형식.
- `company_group`: `domestic`, `foreign`, `other`. `input_quality`: `A`, `B`, `C`, `SYNTHETIC`. 지정값의 대소문자 유지.
- `synthetic_flag`: `yes` 또는 `no`. `yes`와 `SYNTHETIC`은 함께 사용. `construction_mode`: `direct`, `derived`, `proxy`, `mixed`.
- `source_id`, `source_date`: 출처 ID와 실제 기준일. 날짜는 2000~2100년의 `YYYY-MM-DD` 텍스트. Excel 날짜 일련번호 대신 텍스트로 입력.
- `carry_lag_q`: 자료 이월 분기의 비음수 정수. 1분기 초과는 경고.
- `market_common_exposure_adjusted`: `yes`가 필수. `company_exposure_factor`는 0~1의 이미 수행한 조정 기록이며 자동 승산 계수가 아님.
- `currency`, `price_year`: 지원 통화코드와 2000~2100년의 정수 가격연도. 통화·가격연도가 다르면 점수 비교와 달리 공통 금액 비교는 제한.

`READY`는 정상적인 새 입력, `PASS`는 원본 합성 입력과 기대점수까지 일치한 상태다. `CHECK`는 원본 예시의 수치 재현 불일치다. `ERROR` 또는 `INPUT REQUIRED`는 수정 전 결과 사용 불가다. `REVIEW RANGE`, `WINSORIZED`, `DEPENDENCY` 등은 별도 검토 경고이며 정상 입력이라는 사실과 경제적 적합성의 보장은 다르다.

원본 예시 ID와 10개 입력값을 그대로 유지한 경우에만 기대점수를 대조한다. 예시를 수정하면 `READY`로 전환될 수 있으며, 감사시트의 원본예시 대조 가능 행수도 줄어든다. `예시 변경/입력 확인`은 계산 오류라는 의미가 아니다. 실제 입력 오류 여부는 차단행 수와 각 행의 오류코드로 확인한다.

인프라 관계식의 경고 기준은 `abs(infra - network*foreign) > max(0.005, 0.05*max(abs(network*foreign), abs(infra), 1e-12))`다. 경고 허용폭은 반올림·구축 차이를 검토하기 위한 기준이지 측정오차의 확률적 추정치가 아니다.

## 점수와 부호

방향을 맞춘 입력에 고정된 1%·99% 윈저화와 평균순위를 적용한다. 규제·시장 변수는 각각 총점 가중치 1/9, 위험 변수는 각각 1/12다. 각 하위지수와 CPII의 척도는 0~100이다. 비교기업 추가·삭제는 기존 기업의 점수를 바꾸지 않지만, 입력 집단 안의 순위는 바뀔 수 있다.

`A−B = CPII(A)−CPII(B)`이므로 양수는 A의 부담지수가 더 높다는 뜻이다. 개선 전−개선 후로 정의한 정책 감소량과 차감 순서를 혼동하면 안 된다. A와 B를 교환하면 부호가 반전한다. 같은 집단의 동점에는 평균순위를 부여한다.

합성 기본값: 가온 콘텐츠 39.8956110733, 누리 미디어 32.2174492966, 차이 7.6781617767점. 차이는 규제 2.5505997681, 위험 2.7653353241, 시장 2.3622266845점 기여도의 합이다. 실제 기업이나 시장을 추정한 값은 아니다.

0.10 CPII점은 정규화된 변수 위치 차이의 가중합 0.001이다. 비용·매출 0.1%, 기업 백분위 0.1%, 위법 확률이 아니다. 순위식은 계단형이므로 원값이 바뀌어도 같은 정규화 점수가 유지될 수 있다.

## 경제적 해석과 민감도

공통규모 상당액은 부담방향을 맞춘 원단위 차이에 두 기업의 평균 노출액을 곱한 조건부 값이다. 실제규모 차이는 기업별 원값과 각자의 노출액을 결합한 값으로, 기업규모 차이도 포함한다. 점수당 보편적인 원화계수는 없다.

세금에는 양의 세전이익, 망비용에는 매출, 회수 대리값에는 콘텐츠 투자액을 적용한다. 조달비용은 입력 비율의 기간과 평균부채 노출기간을 일치시켜야 한다. 연율에만 해당 기간계수를 적용하고, 이미 분기화된 비율에 분기계수를 다시 곱하는 중복 조정을 피한다. 현재 엔진은 연율·분기율을 자동 판별하지 않으므로 이 검토가 선행되어야 한다.

IP 자산화와 시장전이의 금액은 가정 기반 시나리오다. 인프라 결합·해외의존·비용/설비투자 변수에는 독립적인 금액환산을 제공하지 않는다. 같은 경제 채널을 공유하는 모든 금액 행은 `never_auto_sum`이다. `AVAILABLE - CONTEXT ONLY`는 점수 기여도가 사실상 0인 노출규모 참고값이며, 점수차 원인이라는 뜻이 아니다.

`06_SENSITIVITY`는 동일가중 기준, 하위지수 가중치 변경, 저지원 변수 제외, 중복채널 축소의 네 사양 비교다. 입력값 범위 전체의 불확실성을 포함하지 않는다. 입력값 하한·기준·상한은 Python의 `--feature-ranges`로 별도 평가한다. 어느 범위도 신뢰구간이나 확률구간은 아니다.

## Python 재현

배포 폴더에서 다음을 실행한다. 결과는 무결성 검증 대상인 배포 폴더 밖으로 출력한다.

```bash
python3 verify_release.py --verify .
python3 scripts/cpii_simulator/build_fictional_examples.py --check
python3 scripts/cpii_simulator/validate_input.py \
  data/processed/cpii_simulator/examples/fictional_companies.csv \
  --provenance data/processed/cpii_simulator/examples/fictional_feature_provenance.csv
python3 scripts/cpii_simulator/compare.py \
  data/processed/cpii_simulator/examples/fictional_companies.csv \
  --output-dir ../CPII_v2_reproduction \
  --feature-ranges data/processed/cpii_simulator/examples/fictional_feature_ranges.csv
```

## 실제 비교기준 등록

원본 배포본을 유지한 별도 작업 사본에서 `data/registry/cpii_benchmark_registry.csv`에 실제 분야·분기·비교군·중앙값 산식·버전·원천 SHA-256·실제자료 상태를 등록한다. 세 격차변수의 실제 기준값과 산출 근거는 변수별 출처 기록에도 남긴다. 등록은 외부자료의 진위를 자동 인증하는 절차가 아니다.

`build_workbook_payload.py`로 입력 자료를 다시 구성하고, `@oai/artifact-tool`이 설치된 Node 환경에서 `build_workbook.mjs --project-root . --output ../CPII_registered.xlsx`를 실행한다. Python 입력 검증과 `verify_workbook.mjs`의 수식·화면 검증을 다시 수행한다. 비교군 등록이 고정 정규화 기준분포의 변경을 의미하지는 않는다. 기준분포·가중치·활성 변수를 바꾸는 경우에는 별도의 방법론 버전이 필요하다.
