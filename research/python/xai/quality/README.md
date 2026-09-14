# XAI quality

Đánh giá top-k coverage, concept aggregation, comprehensiveness, sufficiency, stability và runtime từ XAI evidence. Module chỉ đo chất lượng evidence hiện có, không tính lại narrative hoặc claims.

Chạy bằng `npm run research -- ml:xai-quality --mode evaluation`; `--skip-model-metrics` bỏ các phép cần model khi chỉ audit artifact. Output mặc định ở `data/reports/xai_quality/` và `data/manifests/`. Thiếu case/feature mapping hoặc metric không finite làm stage fail.
