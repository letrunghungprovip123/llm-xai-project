# Target audit

Audit `TARGET`, missing values và anomaly trên raw Home Credit. Luồng xử lý: load application data → profile target/missing → kiểm tra anomaly → ghi report/manifest. `SK_ID_CURR` là entity key; `TARGET` chỉ là nhãn và không được trở thành model feature.

Chạy bằng `npm run research -- ml:target-audit`. Module fail khi raw input hoặc invariant target không hợp lệ; không tự sửa dữ liệu. Regression nằm trong `tests/research/ml/`.
