# Patch 0012 — M17A Freddie LLM Generation

## Boundary
Consumes the certified M16 36-case / 216-package cohort. It does not alter M11–M16 artifacts, target, model, SHAP, IR, evidence policies, or cohort selection.

## Protocol freeze
`config/research/replication/llm_replication_protocol_v1.json` freezes the historical Home Credit generation/measurement protocol before Freddie execution. Runtime assertions reject drift in model registry, decoding, prompt/output schema, retry configuration, and claim-extractor lineage.

Frozen generation matrix: 36 cases × 6 evidence conditions × 3 historical LLMs × 1 repeat = 648 planned generations.

Historical Home Credit usable=638 is reference evidence only and is never enforced for Freddie.

## Commands
1. `node --import tsx scripts/multidataset/verify_replication_protocol.ts`
2. `node --import tsx scripts/multidataset/prepare_freddie_generation_plan.ts --workspace <M16_WORKSPACE>`
3. Inspect the frozen 648 jobs/prompts before provider execution.
4. Execute each model using `run_freddie_generation_model.ts`. Keep each model run-id stable across resume attempts.
5. `node --import tsx scripts/multidataset/verify_freddie_generation.ts --workspace <M16_WORKSPACE>`

Qwen and Phi use the existing vLLM runtime and may require serving the appropriate frozen remote model one at a time. DeepSeek uses the existing API runtime/credentials. Model substitution is not permitted under this experiment ID.

## Certification
M17A PASS requires exact 648 terminal cells and exact prompt/evidence hash parity with the pre-execution plan. Provider failures/unusable outputs are recorded as observed outcomes; Freddie is not forced to reproduce Home Credit's 638 usable count.
