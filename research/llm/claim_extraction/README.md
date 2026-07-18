# Atomic claim extraction v2.1

Input là canonical generation index. Luồng xử lý: build stable generation document → reuse cache đúng lineage → chọn pending usable rows → provider boundary → parse/validate exact quotes → numeric split → semantic dedup → checkpoint attempts/claims/failures.

Chạy bằng `npm run research -- llm:claims -- --generation-index <jsonl> --claims-output <jsonl> --failures-output <jsonl> --attempts-output <jsonl>`. Command này có thể gọi provider; không chạy trong regression. Dùng `--limit` cho smoke có chủ đích và không trỏ output vào official artifacts.

Primary keys là `claim_id` và `attempt_id`; mọi record join bằng `generation_id`. Lineage hiện hành: extractor `atomic_claim_extractor_v2.1.0`, prompt v3, claims/attempts/failures v2. Exact source span, taxonomy, certainty, subject type và nested numeric overlap là invariant. Golden smoke có 21 attempts, 19 successful generations, 2 attempted failures và 383 claims. Mock/cache tests không gọi provider.
