# CPII Company Comparator v1 - Design Decisions

Status: frozen methodology with v1.0.1 validation hardening  
Decision date: 2026-09-03  
Product specification: `CPII_FIRM_INPUT_EQW_V1`  
Reference empirical specification: `CPII_FCQ_EXPANDED_EQW_V1`  
Anchor specification: `POOL_SCQ_P01_P99_EMP_RANK_V1`  
Workbook specification: `CPII_COMPARATOR_XLSX_V1.0.1`

## 1. Product purpose

The client enters feature values for company observations. A company name is an identifier only and is never used to fetch, infer, or impute data. The product calculates a reproducible structural-burden score for each eligible observation and compares two or n observations under one frozen methodology.

The tool is a research and strategic-analysis aid. It does not determine legal discrimination, unlawfulness, damages, or a causal effect.

## 2. Primary score object

The primary company-level output is `CPII`, a 0--100 structural-burden score in which a larger value means a higher relative burden position under the frozen reference distribution. The executable v1 baseline uses the current reduced empirical component set:

- `I_reg`: `effective_tax_rate_gap`, `network_cost_ratio`, `infra_dependency_ratio`.
- `I_risk`: `funding_cost_spread`, `ip_assetization_gap`, `investment_recovery_ratio`, `cashflow_recovery_ratio`.
- `I_market`: `cross_market_transfer_index`, `foreign_dependency_ratio`, `outflow_to_capex_ratio`.

`creator_share_ratio` and `bundle_leverage_index` remain inactive shadow variables until a future anchor has adequate observations and variation. The report's broader theoretical variable set is not silently substituted into v1.

The v1 transformation order is direction alignment, configured transformation, 1/99 percent winsorization against the frozen pooled reference, empirical-rank percentile normalization with average ties, equal weighting within each subindex, equal weighting across the three subindices, and 0--100 display.

## 3. Difference and sign convention

For selected observations A and B:

```text
delta_cpii_points(A,B) = CPII(A) - CPII(B)
pairwise_burden_gap(A,B) = delta_cpii_points(A,B) / 100
```

A positive value means A has the higher measured structural burden; a negative value means B has the higher measured structural burden; zero means no measured difference under the displayed precision and specification. `delta_cpii_points` ranges from -100 to 100, while `pairwise_burden_gap` ranges from -1 to 1.

The normalized pairwise quantity is named `feature-derived pairwise burden gap`. It is not the project's separate judgment- and evidence-coded `signed evidence score`, and the two must never share a label, axis, legend, or interpretation rule.

## 4. When the term reverse-discrimination gap is permitted

The user-facing label `reverse-discrimination gap` is permitted only when all of the following hold:

1. A is explicitly tagged `domestic` and B `foreign` for the same focal market, or the displayed orientation is transparently reversed.
2. Both observations share sector, comparable service scope, focal market, reporting period, input units, and benchmark identifier.
3. Both pass the strict common-support rule and all blocking input checks.
4. Both use exactly one of quality `A`, `B`, or `SYNTHETIC` and construction mode `direct` or `derived`; quality `C`, `proxy`, `mixed`, unknown, or blank values never pass the terminology gate.

If these conditions do not hold, the neutral label `structural-burden gap` is used. Domestic-domestic and foreign-foreign comparisons are never automatically labeled reverse discrimination.

## 5. Input and comparability contract

One input row represents one `company x service_scope x focal_market x reporting_period` observation. Required comparison metadata are `observation_id`, `company_name`, `company_group`, `sector`, `service_scope`, `focal_market`, `reporting_period`, `benchmark_id`, `currency`, `price_year`, and `input_quality`.

`observation_id` is a cross-file and pair-output key, not free display text. It must be no more than 64 characters, nonblank and unique, must equal its trimmed form, and may not contain ASCII lowercase letters, Excel wildcard characters (`*`, `?`, `~`), or the reserved pair separator `__vs__`. These restrictions make Excel lookup semantics and Python pair identifiers unambiguous. Company, exposure, and provenance files use the same exact ID.

Raw company-level values are preferred. A comparator-relative feature may be supplied only when its `benchmark_id`, definition, period, market, and unit are identical across the compared observations. The application must block a headline comparison when comparator-relative features use different benchmarks.

The strict headline score requires all ten active v1 features. A legacy-compatible partial score may be calculated for diagnostics using the existing missingness rule, but it is visibly labeled `partial diagnostic`, reports its effective feature set, and cannot be mixed into the strict n-company ranking.

A blank feature is missing and is never coerced to numeric zero; a literal numeric zero remains valid when allowed by the feature definition. A company row is headline-ineligible if it has a duplicate or unsafe ID, missing/invalid metadata, a nonnumeric or nonfinite active feature, an unregistered or inapplicable synthetic-only benchmark, inconsistent synthetic flags, or an unadjusted market-common exposure. Review-envelope breaches, winsorization, low-support anchors, weak quality, proxy/mixed construction, long carry and dependency-identity discrepancies are explicit warnings rather than silent edits.

## 6. Two-company and n-company modes

Two-company mode is a detailed view of the same n-company engine with n=2. It shows both scores, the signed difference, subindex and feature contributions, raw-unit gaps, eligible economic-equivalent amounts, uncertainty or sensitivity ranges, and comparability warnings.

The selected pair is invalid when either ID is blank, unknown, duplicated, unsafe, self-selected, headline-ineligible, or in a different cohort. Invalidity gates the entire downstream chain: score difference, decomposition, economic interpretation, and sensitivity are all unavailable rather than being calculated with blanks as zero. Reverse-discrimination-related wording uses an exact allowlist for group, quality, and construction mode.

n-company mode provides a strict common-support ranking and an antisymmetric pairwise difference matrix. Missing or ineligible scores produce `N/A`, not a numeric zero. Exact ties receive their average descending rank. A selected pair can open the same detailed view used in two-company mode. Pair-specific partial-support results may be exported as diagnostics, but they are not aggregated into one overall ranking when their feature sets differ.

The frozen anchor is independent of the entered company set. Reordering rows, selecting a subset, or adding a third company must not change an existing observation's score.

## 7. Economic-interpretation contract

There is no universal `one CPII point = currency amount` coefficient. A score difference is first decomposed exactly into feature contributions, then each raw-unit difference is interpreted using a registered economic bridge when one exists.

Every monetary output identifies its exposure base, time basis, currency, price year, assumptions, low/base/high values, monetization class, and overlap family. Direct accounting equivalents, stakeholder transfers, counterfactual opportunity or risk scenarios, and non-monetizable indicators are displayed separately. Values that share an economic object or may be downstream of one another are not automatically summed.

An exposure row is usable only when its ID is unique and matches one company, its currency and price year match that company, its time basis is comparable across the pair, all supplied values are finite, every low/base/high triplet is complete and ordered, and period/conversion fractions lie in their declared interval. Failure disables only monetary interpretation unless the company score itself is ineligible. If a feature's CPII contribution is numerically zero, an otherwise computable amount is labeled `context only`; it is not evidence that the feature explains the score gap.

## 8. Sensitivity contract

Workbook sheet `06_SENSITIVITY` varies method specifications only: axis weights, exclusion of low-support features, and overlapping-channel weight reduction. It must not be described as a complete propagation of company-input uncertainty.

Feature-specific low/base/high inputs defined by `cpii_feature_range_schema.csv` are evaluated through Python `compare.py --feature-ranges`. Input-range corners and method variants answer different questions and remain separately labeled. Neither range is a confidence interval, posterior interval, probability, or causal uncertainty estimate. A pair that fails the comparison contract has no sensitivity result.

## 9. Delivery scope

The v1 client bundle contains:

- a macro-free, external-link-free `.xlsx` comparator;
- a Python reference engine and versioned frozen anchor;
- input and economic-exposure templates;
- fictional golden test cases used by both workbook and appendix;
- a Korean quick-start guide and data dictionary;
- the report with an economic-interpretation appendix;
- parity, formula, visual, and release-verification evidence.

The Excel workbook is the primary client interface. The Python module is the calculation source of truth and audit reference; the workbook must reproduce its golden outputs. The bundled currency list, shown on `92_REF_VARIABLES`, is an explicit supported subset and must not be represented as universal ISO 4217 coverage. A hosted web application, live company-data lookup, concurrent account management, central database, API integration, and automated data acquisition are deferred from v1.

## 10. Versioning, packaging, and change control

Every result carries `product_spec_version`, `anchor_version`, and `generated_at`. A changed active-feature set, direction, transformation, tie rule, winsor limit, weight, missingness rule, or reference sample requires a new methodology or anchor version. Existing release files are not overwritten.

Low-resolution anchors, out-of-range clipping, proxy or estimated inputs, and missing economic exposure bases produce explicit warnings. Such warnings do not alter the user's raw entry.

The release bundle is immutable once its SHA-256 manifest is written. Reproduction outputs therefore go outside the bundle, for example `../CPII_reproduction_check`. Exact frozen-output reproduction targets Python 3.12. When Poppler commands `pdfinfo` and `pdftotext` are available the PDF gate rechecks pages and text; otherwise it permits only the exact frozen PDF SHA-256. The verifier binds the workbook audit to the actual workbook hash, checks critical-formula semantics and formula length, rejects symlinks and undeclared files, and requires customer-readable packaged file permissions.

## 11. Reconciled implementation items

- The report's theoretical full set and the executable reduced empirical set differ; v1 adopts the latter and labels the former future or shadow scope.
- The signed-evidence discussion was corrected to a zero-centered signed score and remains separate from CPII.
- `investment_recovery_ratio` and `cashflow_recovery_ratio` are classified as conditional performance equivalents. `cross_market_transfer_index` uses `eligible_market_revenue` only as an explicit scenario base; it is not a direct accounting amount.
- New modules resolve paths from an explicit project root or command-line argument. Release artifacts must not embed a user home or temporary staging path.

## 12. Acceptance invariants

- Same input and same versions produce the same score.
- Adding, removing, or reordering comparison rows does not change an existing strict score.
- `gap(A,B) = -gap(B,A)` and `gap(A,A) = 0`.
- Feature contributions sum to the displayed gap within the declared tolerance.
- Strict ranking never mixes different effective feature sets.
- Blank features never become zero, invalid pairs never emit downstream numeric outputs, and duplicate keys never select an arbitrary first row.
- Monetary output is unavailable when the exposure contract fails; a zero-contribution amount is labeled context only.
- Formula presence alone is insufficient: critical workbook cells must satisfy the versioned semantic formula contract and the audit must match the delivered workbook hash.
- A score gap is never presented as a percentage cost, legal finding, causal effect, or unqualified total loss.
