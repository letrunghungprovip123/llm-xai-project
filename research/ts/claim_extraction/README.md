# Atomic claim extraction v2.1

Input là canonical generation index. Luồng xử lý chính thức: build stable generation document → reuse cache đúng lineage → canonicalize provider payload bằng rule deterministic → strict schema/exact-source validation → deterministic metadata claims → numeric split → semantic dedup → checkpoint attempts/claims/failures.

Chạy bằng `npm run research -- llm:claims -- --generation-index <jsonl> --claims-output <jsonl> --failures-output <jsonl> --attempts-output <jsonl> --provider-policy <policy>`.

Provider policy:

- `stored-only`: chỉ replay complete validation-failed raw responses cùng lineage; cấm provider call.
- `stored-first`: replay stored response trước, chỉ gọi provider khi không có stored response hợp lệ. Đây là mặc định.
- `provider-only`: bỏ stored replay và gọi provider cho generation chưa có cache success.

`--limit` chỉ giới hạn provider calls. `--force false` giữ cache success đúng lineage. Command có thể gọi provider ở `stored-first` và `provider-only`; không chạy các mode đó trong regression.

Primary keys là `claim_id` và `attempt_id`; mọi record join bằng `generation_id`. Lineage hiện hành: extractor `atomic_claim_extractor_v2.1.0`, prompt v3, claims/attempts/failures v2. Exact source span, taxonomy, certainty, subject type và nested numeric overlap là invariant. Canonicalization là một phần của provider boundary chung cho cả response mới và stored replay; không có dataset-specific repair module.

## Reprocess stored successful responses

Khi chỉ thay đổi canonicalization/postprocessor, có thể tái xử lý một tập success đã lưu raw response mà không gọi provider:

```bash
npm run research -- llm:claims -- \
  --generation-index <generation_index.jsonl> \
  --claims-output <claims.jsonl> \
  --failures-output <failures.jsonl> \
  --attempts-output <attempts.jsonl> \
  --provider-policy stored-only \
  --reprocess-stored-success-ids <generation_ids.txt> \
  --force false
```

File ID chứa đúng một `generation_id` trên mỗi dòng. Luồng này preflight toàn bộ ID/raw response trước khi ghi, thay claims của đúng các generation được chọn, giữ nguyên attempt history và tạo 0 provider call.
