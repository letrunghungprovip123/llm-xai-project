# Report Release Runbook

Apply the three patches in numerical order. Then run the analytical chain from
the repository root:

```bash
python3 -m research.python.data_mart.main
python3 -m research.python.metric_engineering.main
python3 -m research.python.statistical_analysis.main
python3 -m research.python.diagnostics.main
python3 -m research.python.decision_support.main
python3 -m research.python.validator_sensitivity.main
pytest
```

Inspect the regenerated outputs, then freeze the source and analytical snapshot:

```bash
git add research config docs tests pyproject.toml \
  data/reports/llm_validation/validation_v1/analysis
git commit -m "freeze thesis analytical release v1"
```

The working tree must now be clean. Generate the report-writing bundle:

```bash
python3 -m research.python.report_release.main
```

The final command must print:

```text
Exit gate: REPORT_WRITING_READY
```

Use only these files when writing Chapters 3–6:

```text
data/reports/llm_validation/validation_v1/analysis/report_release/
├── report_numbers.json
├── report_source_index.csv
├── report_release_manifest.json
└── report_readiness_validation.json
```

`report_numbers.json` is the only copy source for headline numbers. Do not copy
numbers from notebooks, screenshots or older Tableau workbooks.

A dirty-tree preview is available for inspection only:

```bash
python3 -m research.python.report_release.main --allow-dirty-preview
```

A preview is not a thesis release and must not be cited as final.
