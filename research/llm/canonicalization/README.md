# Canonicalization

Input gồm evidence subset 216, selected-case metadata, ba main model generation/prompt pairs và Template pair tùy chọn. Luồng xử lý: strict read/profile → validate cohort/hash → join bằng `source_ir_id::evidence_level` → dựng canonical rows → validate matrix → atomic-write index/reports/manifests.

Lọc DeepSeek bằng `npm run research -- llm:filter-deepseek -- --generations <raw720> --prompts <raw720> --evidence <eval36> --out-dir <dir>`. Dựng index bằng `npm run research -- llm:canonicalize -- <source arguments> --out-dir <dir>`; main CLI yêu cầu Qwen, DeepSeek và Phi đúng thứ tự.

`canonical_key = model_id::repeat_id::source_ir_id::evidence_level`; `cohort_key = source_ir_id::evidence_level`. Raw generation được nhúng nguyên trong `generation_record`; source path/line/file SHA được giữ. Strict official counts fail-fast, data-contract observations có thể tạo warning. Golden main là 648/638/10, Template 216 và không eligible cho selection. Tests dùng public `index.ts`; reproduction phải ghi vào `.refactor-validation/`.
