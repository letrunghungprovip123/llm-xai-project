# Data Flow

## Phase 1: Python ML Research

```text
data/raw/bank-additional-full.csv
→ data/processed/
→ train models
→ generate predictions
→ generate SHAP/LIME/counterfactuals
→ export artifacts/xai-evidence/


artifacts/xai-evidence/customer_id.json
→ ir-assembler.ts
→ ir-validator.ts
→ Explanation IR
→ LLM explanation
→ faithfulness validator
→ self-refinement
→ dashboard


artifacts/xai-evidence/customer_id.json
→ ir-assembler.ts
→ ir-validator.ts
→ Explanation IR
→ LLM explanation
→ faithfulness validator
→ self-refinement
→ dashboard