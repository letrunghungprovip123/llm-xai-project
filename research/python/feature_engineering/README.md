# Feature engineering

Xây các feature group ở mức một dòng mỗi `SK_ID_CURR`. Mỗi group theo thứ tự load cột cần thiết → aggregate → validate unique customer → trả DataFrame; `pipeline.py` join các group và ghi interim artifacts/reports.

Chạy bằng `npm run research -- ml:features`. Input là raw tables; output mặc định ở `data/interim/`, `data/reports/` và `data/manifests/`. Golden hiện tại là 307,511 application rows và 166 engineered features. Duplicate customer sau aggregate hoặc thiếu cột bắt buộc làm stage fail.
