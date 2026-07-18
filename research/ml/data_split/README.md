# Data split

Tạo train/validation/test từ feature matrix và audit leakage. Luồng xử lý: load matrix/target/registry → xác định model columns → split có stratification → kiểm tra disjoint IDs và distribution → ghi split artifacts.

Chạy bằng `npm run research -- ml:split`. Primary key là `SK_ID_CURR`; output mặc định ở `data/processed/splits/`. Golden rows là 215,257 / 46,127 / 46,127. Overlap customer, target/ID trong X hoặc row-count mismatch làm stage fail.
