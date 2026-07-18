# Data audit

Đọc các bảng CSV trong `data/raw/`, kiểm tra schema, khóa và quan hệ bảng trước mọi biến đổi. Luồng xử lý: discover files → profile rows/columns → audit primary/foreign keys → ghi report và manifest. Khóa customer chính là `SK_ID_CURR`; module không sửa raw data.

Chạy bằng `npm run research -- ml:data-audit`. Output mặc định nằm trong `data/reports/` và `data/manifests/`. Thiếu file, duplicate key hoặc quan hệ không hợp lệ làm stage fail. Unit/regression liên quan nằm trong `tests/research/ml/`.
