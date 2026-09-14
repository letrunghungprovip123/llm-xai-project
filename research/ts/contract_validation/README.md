# Deterministic contract validation

Input là canonical generation index và evidence packages cùng cohort. Luồng xử lý: map evidence bằng `package_id` → đọc output observations → áp dụng structural/allowlist/S5/language rules → ghi đúng một metrics record mỗi canonical row.

Chạy bằng `npm run research -- llm:contract -- --generation-index <jsonl> --evidence <jsonl> --output <jsonl>`. Identity chính là `generation_id`/`canonical_key`; evidence join bằng `package_id`.

Validator giữ unusable rows để audit và không triển khai `direction_surface_match`, nên field này phải là `null`. Golden là 648 records, 602 pass và 46 fail. Duplicate package, missing join hoặc malformed canonical identity làm stage fail; rule failure nằm trong `issue_codes`. Tests ở `tests/llmValidation/contractValidation.test.ts` qua public `index.ts`.
