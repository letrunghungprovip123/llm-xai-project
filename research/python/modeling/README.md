# Modeling

Train các candidate hiện hành, đánh giá validation, chọn winner theo policy sẵn có rồi đánh giá test. Luồng xử lý: build candidates → train → validation metrics → select → test metrics → ghi bundle/manifest. Không đổi algorithm hoặc hyperparameters trong refactor.

Chạy bằng `npm run research -- ml:train`. Input là model-ready tree/linear artifacts; output ở `artifacts/models/`, `data/reports/` và `data/manifests/`. Winner golden là HistGradientBoosting. Thiếu feature mapping, metric không hợp lệ hoặc bundle/manifest không nhất quán làm stage fail.
