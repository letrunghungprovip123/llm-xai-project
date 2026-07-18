# Preprocessing

Fit preprocessors chỉ trên train rồi transform train/validation/test. Luồng xử lý: load splits → determine feature columns → fit train → transform ba split → validate aligned columns/finite values → ghi model-ready data, mappings và preprocessor artifacts.

Chạy bằng `npm run research -- ml:preprocess`. Input mặc định là `data/processed/splits/`; output ở `data/processed/model_ready/`, `artifacts/preprocessing/`, `ml/registry/` và manifests. Golden tree matrix có 213 columns. Leakage, lệch column order, NaN/inf hoặc TARGET/ID làm stage fail.
