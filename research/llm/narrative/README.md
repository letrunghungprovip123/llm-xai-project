# Narrative generation

Input là Evidence Package JSONL schema 2.1. Luồng xử lý: load/validate packages → select cases/levels → build prompt → runner → parse output → metrics → checkpoint shard; `aggregate` deduplicate và tạo reports. `package_id` join prompt/generation với evidence; `generation_id` có format run/model/repeat/package hiện hành; `prompt_id` khóa prompt content.

Chạy generation bằng `npm run research -- llm:generate -- --input <jsonl> --output-dir <dir> --run-id <id> --models <ids>`. Chạy aggregation bằng `npm run research -- llm:aggregate -- <arguments>`. Xem `--help` của entrypoint khi chuẩn bị run cụ thể.

Invariant: prompt `prompt_v1`, output schema `1.0`, S0 không có factors, S5 theo backend skeleton, resume chỉ reuse generation usable. Missing/unsafe payload, duplicate state hoặc schema/runtime failure được ghi explicit. Tests ở `tests/research/llm/narrative/`; Template fixture không gọi provider. Official Qwen/Phi/DeepSeek generations không được tạo lại trong regression.
