# Explanation IR v2

Chuẩn hóa local XAI và quality context thành Explanation IR v2. Luồng xử lý: load XAI evidence/quality → join theo case → xây quality-aware IR → validate schema/IDs → ghi JSONL, reports và manifest.

Chạy bằng `npm run research -- ml:ir --mode evaluation`; CLI cho phép override các input quality paths và `--fail-on-warnings`. Golden là 120 IR records. `ir_id` là primary identity; case/customer IDs là provenance. Missing join, duplicate IR ID hoặc schema invalid làm stage fail.
