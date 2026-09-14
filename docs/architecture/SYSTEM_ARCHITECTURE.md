# LLM-XAI system architecture

## Current certified path

```text
Home Credit data
→ feature engineering and preprocessing
→ credit-risk model
→ SHAP/XAI
→ Explanation IR
→ controlled evidence S0-S5
→ LLM narratives
→ canonical generations
→ atomic claims
→ claim validation
→ analytical marts, statistics and diagnostics
→ thesis-report-v1
→ visualization-data-v2
→ seven-page bilingual Dash application
```

Python owns data, ML, XAI, analytical engineering, releases and Dash. TypeScript
owns LLM generation, canonicalization, claim extraction/finalization and claim
validation. The language boundary is artifact-oriented: neither runtime imports
the other runtime's implementation.

## ResearchOps target boundary

- Git stores code, contracts and stage definitions.
- MinIO/S3 stores immutable artifact bytes and certified bundles.
- PostgreSQL stores mutable operational state and lineage indexes.
- Prefect will consume the Stage Registry; it will not redefine stages.
- MLflow will track experiments and models; it will not replace certified manifests.
- FastAPI will enforce application rules.
- Next.js will become an operations and review portal, not a second analytical dashboard.
- Dash remains the certified aggregate research-analytics surface.

## Fail-closed rule

A missing contract, failed blocking gate, unsupported schema, invalid hash or
incomplete parent lineage must block promotion or certified presentation.
