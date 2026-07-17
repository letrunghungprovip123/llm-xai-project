# LLM validation commands

Source được chia theo chức năng thay vì theo số phase:

```text
src/server/llmValidation/
├── canonicalization/
├── contractValidation/
├── claimExtraction/
└── selection/
```

## Canonicalization

Hai command giữ raw official artifacts bất biến:

```bash
npm run canonicalize:filter-deepseek -- \
  --generations /path/to/generated_explanations.jsonl \
  --prompts /path/to/prompt_instances.jsonl \
  --evidence /path/to/evidence_packages_36.jsonl \
  --out-dir data/reports/llm_validation/validation_v1/canonicalization/deepseek_evaluation_36
```

```bash
npm run canonicalize:build-index -- \
  --evidence /path/to/evidence_packages_36.jsonl \
  --selected-cases /path/to/selected_case_ids_36.csv \
  --selection-manifest /path/to/selection_manifest.json \
  --feature-registry ml/registry/feature_registry.csv \
  --qwen-generations /path/to/qwen/generations.jsonl \
  --qwen-prompts /path/to/qwen/prompt_instances.jsonl \
  --qwen-manifest /path/to/qwen/shard_manifest.json \
  --deepseek-generations /path/to/deepseek_36/generations.jsonl \
  --deepseek-prompts /path/to/deepseek_36/prompt_instances.jsonl \
  --deepseek-manifest /path/to/deepseek_36/filter_manifest.json \
  --phi-generations /path/to/phi/generations.jsonl \
  --phi-prompts /path/to/phi/prompt_instances.jsonl \
  --phi-manifest /path/to/phi/shard_manifest.json \
  --template-generations /path/to/template/generations.jsonl \
  --template-prompts /path/to/template/prompt_instances.jsonl \
  --template-manifest /path/to/template/shard_manifest.json \
  --out-dir data/reports/llm_validation/validation_v1/canonicalization
```

Main index phải có 648 rows. Template nằm ở index riêng 216 rows và không eligible cho selection.

## Generation contract

```bash
npm run validate:generation-contract -- \
  --generation-index /path/to/generation_index.jsonl \
  --evidence /path/to/evidence_packages_36.jsonl \
  --output /path/to/generation_contract_metrics.jsonl
```

## Atomic claim extraction

Thiết lập provider giống luồng đã tạo 720 generations:

```bash
export DEEPSEEK_API_KEY='YOUR_KEY'
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_CLAIM_EXTRACTOR_MODEL_ID=deepseek-v4-flash
```

```bash
npm run validate:extract-claims -- \
  --generation-index /path/to/generation_index.jsonl \
  --claims-output /path/to/claims.jsonl \
  --failures-output /path/to/claim_extraction_failures.jsonl \
  --attempts-output /path/to/claim_extraction_attempts.jsonl \
  --limit 3 \
  --checkpoint-every 1
```

Xóa `--limit` sau smoke test. Runner resume theo source hash + provider/model +
extractor/prompt version, retry failure cũ và ghi explicit failure cho generation
unusable. Attempt log lưu token usage, request/model ID, HTTP status, retry count,
stop reason và SHA-256 của raw response; raw body mặc định không được lưu.

Prompt đang hoạt động là `config/llm-validation/claim_extraction_prompt_v3.json`.
DeepSeek chỉ tách claim ngữ nghĩa. Code tự neo exact quote, gán index/span, bổ
sung feature/concept presence từ declared metadata, tách numeric claim, tạo
semantic signature, dedup và tính source-slot coverage.

## Threshold engine

Command chỉ chạy sau khi các phase aggregation/statistics đã tạo input đúng schema:

```bash
npm run validate:run-selection -- \
  --candidates /path/to/selection_candidates.jsonl \
  --observations /path/to/paired_quality_observations.jsonl \
  --output /path/to/selection_result.json
```

Chi tiết copy/run nằm ở `docs/llm-validation/COPY_AND_RUN.md`; phân tích thuật toán nằm ở `docs/llm-validation/threshold-selection-v1.md`.
