# Evidence exposure S0–S5

Biến Explanation IR v2 thành Evidence Package schema 2.1. Luồng xử lý: load IR → kiểm tra cohort overlap → build S0–S5 theo policy hiện hành → validate sáu package mỗi IR → ghi JSONL, reports và manifest.

Chạy bằng `npm run research -- ml:evidence --run-mode evaluation`. Có thể override `--input`, `--output-dir`, `--manifest-dir` và `--disallow-overlap-with`. `package_id` là primary key; `source_ir_id` join về IR. Golden là 720 packages và evaluation subset 216. Overlap, duplicate/missing level hoặc policy invariant làm stage fail.
