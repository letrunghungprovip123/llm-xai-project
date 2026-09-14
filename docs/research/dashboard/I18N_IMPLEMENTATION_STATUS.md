# Dashboard i18n Certification Status

## Certified objective

The complete LLM-XAI Dash presentation supports Vietnamese and English.
Vietnamese (`vi`) is the first-visit default. An explicit user selection is
persisted in browser local storage and survives route changes and reloads.

Certified analytical CSV/JSON artifacts remain immutable. Locale changes affect
presentation copy, locale-aware number formatting, Plotly labels, AG Grid text,
accessibility labels and export documentation only. They do not alter stable
IDs, selected controls, URL state, analytical arrays, denominators, source
hashes or inference results.

## Final patch sequence

| Patch | Scope | Status |
|---|---|---|
| 0030 | Strict locale core, catalogs, formatters and domain labels | Complete |
| 0031–0033a | Persistent locale state, app shell, shared components and DMC compatibility | Complete |
| 0034–0036c | Overview, Effectiveness, Mechanisms and Plotly representation safeguards | Complete |
| 0037–0039a | Decision, Robustness, Case Explorer and leaf-control test correction | Complete |
| 0040 | Reproducibility & Methods | Complete |
| 0041 | Cross-page export localization certification | Complete |
| 0042 | Global page/export certification, cleanup and live-browser coverage | Complete |

## Frozen contracts

- Supported locales: `vi`, `en`.
- Default locale: `vi`.
- Missing translation keys fail closed; there is no silent English fallback.
- EN and VI catalogs have identical keys and interpolation placeholders.
- Stable control values and analytical identities are never translated.
- Plotly `customdata`, figure metadata and numeric arrays are locale-neutral.
- Embedded technical identifiers such as `visualization-data-v2`, CSV names,
  hashes and commands remain unchanged inside localized sentences.
- AG Grid receives explicit locale dictionaries for both languages.
- Every export archive records `display_locale`, includes a localized README,
  and preserves machine-readable schemas and stable identities.
- The Methods archive contains immutable technical CSV files plus separate
  locale-aware `display/` copies.

## Certification commands

Catalog parity:

```bash
python3 -m research.python.dashboard.i18n
```

Complete runtime page and export certification:

```bash
python3 -m research.python.dashboard.i18n.certify \
  --output-dir release/thesis_dashboard_v1/tests/i18n_certification
```

Dashboard regression:

```bash
python3 -m pytest -q tests/research/python/dashboard
```

Live browser verification:

```bash
python3 -m research.python.dashboard.app
```

In another terminal:

```bash
DASH_E2E_BASE_URL="http://127.0.0.1:8050" \
python3 -m pytest -q tests/research/python/dashboard/e2e
```

## Generated certification artifacts

The certification CLI writes:

- `i18n_catalog_parity.json`
- `i18n_page_coverage.json`
- `i18n_export_coverage.json`
- `i18n_untranslated_strings.csv`
- `i18n_certification_summary.json`

A release is acceptable only when catalog, all fourteen page-locale renders and
all fourteen export-locale archives report `passed: true`, and the untranslated
strings CSV contains only its header.
