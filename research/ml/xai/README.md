# SHAP/XAI

Đọc model winner và model-ready test data, chọn 120 cases rồi tạo local SHAP evidence. Luồng xử lý: load bundle/data/registry → select cases → explain → check additivity/direction → ghi evidence, summary và manifest.

Chạy bằng `npm run research -- ml:xai --mode evaluation` (hoặc run mode được CLI liệt kê). Join key là `SK_ID_CURR`; downstream identity nằm trong XAI record ID. Golden là 120 cases × 213 features. Additivity, feature order hoặc registry mismatch làm stage fail.
