# Copy và chạy LLM validation v2.1

Gói bàn giao chỉ chứa code, config, test và tài liệu; không chứa output.

## 1. Copy vào root project

Giải nén gói rồi copy đè từ thư mục đã giải nén vào root `llm-xai-next`:

```bash
cp -R /path/to/llm-xai-claim-extraction-v2.1-deepseek-patch-only/. .
```

Patch đã bao gồm file tương thích tại
`src/server/llmValidation/claimExtraction/bedrockAtomicClaimExtractor.ts`.
File này chỉ re-export DeepSeek để ghi đè code Bedrock v2 cũ; không còn AWS call.

Source tiếp tục chia theo chức năng, không chia theo phase:

```text
src/server/llmValidation/
├── canonicalization/
├── contractValidation/
├── claimExtraction/
└── selection/
```

## 2. NPM scripts và dependency

Nếu scripts đã có từ bản trước thì không cần chạy lại. Nếu chưa có:

```bash
npm pkg set \
  'scripts.typecheck:llm-validation=tsc -p tsconfig.llm-validation.json --noEmit' \
  'scripts.canonicalize:filter-deepseek=tsx batch/llm-validation/filter-deepseek-eval36.ts' \
  'scripts.canonicalize:build-index=tsx batch/llm-validation/build-generation-index.ts' \
  'scripts.validate:generation-contract=tsx batch/llm-validation/run-contract-validation.ts' \
  'scripts.validate:extract-claims=tsx batch/llm-validation/run-claim-extraction.ts' \
  'scripts.validate:run-selection=tsx batch/llm-validation/run-threshold-selection.ts' \
  'scripts.test:llm-validation=node --import tsx --test tests/llmValidation/*.test.ts'
```

Claim extractor không cần AWS SDK. Nó dùng `fetch` có sẵn trong Node.js, cùng
`dotenv`, `tsx` và TypeScript đã có trong project.

## 3. Kiểm tra code

```bash
npm run typecheck:llm-validation
npm run test:llm-validation
```

Kỳ vọng: typecheck không lỗi và 30 tests pass.

## 4. Chọn đúng canonical index

Code không phụ thuộc tên folder output. Đoạn sau ưu tiên folder tên mới và tự
fallback về `phase0` đang có trên máy:

```bash
if test -f data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl; then
  export GEN_INDEX=data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl
else
  export GEN_INDEX=data/reports/llm_validation/validation_v1/phase0/generation_index.jsonl
fi

test -f "$GEN_INDEX"
wc -l "$GEN_INDEX"
```

`wc -l` phải trả 648.

## 5. Cấu hình DeepSeek V4 Flash

```bash
export DEEPSEEK_API_KEY='YOUR_KEY'
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_CLAIM_EXTRACTOR_MODEL_ID=deepseek-v4-flash

# Các giá trị dưới đây đã được khóa an toàn trong code; chỉ export khi cần override.
export DEEPSEEK_CLAIM_MAX_TOKENS=3000
export DEEPSEEK_CLAIM_TIMEOUT_MS=120000
export DEEPSEEK_CLAIM_MAX_RETRIES=3
export DEEPSEEK_CLAIM_RETRY_DELAY_MS=1000
```

Không commit hoặc gửi `DEEPSEEK_API_KEY` vào report.

Để CLI tính chi phí theo đúng tài khoản của bạn, điền đơn giá thực tế trên một
triệu token; bỏ qua hai biến này nếu chưa xác nhận được giá:

```bash
export DEEPSEEK_INPUT_COST_PER_MILLION='YOUR_INPUT_RATE'
export DEEPSEEK_OUTPUT_COST_PER_MILLION='YOUR_OUTPUT_RATE'
```

## 6. Smoke test 3 generations

Dùng folder mới để giữ nguyên toàn bộ output Haiku v1 làm audit history:

```bash
export CLAIM_OUT_DIR=data/reports/llm_validation/validation_v1/claim_extraction_deepseek_v2_1
mkdir -p "$CLAIM_OUT_DIR"

npm run validate:extract-claims -- \
  --generation-index "$GEN_INDEX" \
  --claims-output "$CLAIM_OUT_DIR/claims.jsonl" \
  --failures-output "$CLAIM_OUT_DIR/claim_extraction_failures.jsonl" \
  --attempts-output "$CLAIM_OUT_DIR/claim_extraction_attempts.jsonl" \
  --limit 3 \
  --checkpoint-every 1 \
  --store-raw-responses true
```

Smoke đạt khi:

- `Successful generations: 3`;
- `New DeepSeek calls: 3`;
- `Failure/unusable records: 10` nếu đúng canonical index 638 usable hiện tại;
- `Claims > 0`, có deterministic feature/concept claims nếu generation khai báo IDs;
- attempt records có provider/model/request ID, HTTP status, retry count và usage;
- exact source span, numeric split, semantic dedup và source coverage qua schema/test.

Sau khi xem ba raw response, không bật lưu raw cho full run để giảm kích thước
và tránh giữ nội dung không cần thiết. SHA-256 của response vẫn luôn được lưu.

## 7. Chạy toàn bộ và resume

```bash
npm run validate:extract-claims -- \
  --generation-index "$GEN_INDEX" \
  --claims-output "$CLAIM_OUT_DIR/claims.jsonl" \
  --failures-output "$CLAIM_OUT_DIR/claim_extraction_failures.jsonl" \
  --attempts-output "$CLAIM_OUT_DIR/claim_extraction_attempts.jsonl" \
  --checkpoint-every 5
```

Runner sẽ reuse success chỉ khi cùng source hash, DeepSeek model, extractor
version, prompt version và prompt SHA-256. Failure sẽ được retry ở lần chạy sau; 10 generation
unusable được ghi explicit failure và không gọi API. Không dùng `--force true`
trừ khi chủ động muốn gọi lại toàn bộ 638 usable generations.

## 8. Đọc metrics v2.1

Mỗi claim có thêm:

- `claim_origin`: `llm`, `deterministic_metadata` hoặc `derived_numeric`;
- `numeric_role`: phân biệt prediction score, threshold, feature value và rank;
- `model_normalized_claim_key`: key gốc từ provider;
- `semantic_signature`: key ổn định do code tạo để dedup.

CLI còn in số claim deterministic/numeric được bổ sung, causal overclaim bị
demote, semantic duplicate đã loại và source-slot coverage. `safe_summary` được xem là covered khi nó chỉ
lặp lại đúng một claim đã giữ từ section ưu tiên; nếu có ý mới nhưng không có
claim, nó vẫn nằm trong `unclaimed_source_slots` để audit.

DeepSeek ở bước này chỉ tách claim, không chấm claim đúng hay sai. Vì DeepSeek
cũng là một model trong ma trận generation, các phase validation/calibration
sau vẫn phải theo dõi self-model bias và ưu tiên validator độc lập hoặc human
calibration trước khi khóa threshold cuối.

## 9. Chưa chạy final threshold selection

`run-threshold-selection.ts` đã khóa thuật toán nhưng chỉ chạy khi đã có đủ
configuration candidates, paired quality observations, bootstrap bounds, human
calibration và cost provenance. Không tạo candidate giả để chạy sớm.
