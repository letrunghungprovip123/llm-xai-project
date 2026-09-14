# Feature matrix và registry

Ghép engineered groups với application entity/target, sau đó tạo feature matrix và registry. Luồng xử lý: load group artifacts → join bằng `SK_ID_CURR` → tách target/ID → validate registry → ghi processed matrix và metadata.

Chạy bằng `npm run research -- ml:matrix`. Output nằm trong `data/processed/`, `ml/registry/`, `data/reports/` và `data/manifests/`. `TARGET` và entity IDs không được lọt vào model feature columns; join cardinality hoặc registry mismatch làm stage fail.
