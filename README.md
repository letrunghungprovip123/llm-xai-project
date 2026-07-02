# LLM-XAI Thesis Project

## 1. Tổng quan dự án

Đề tài: **Ứng dụng Large Language Model cho hệ thống Explainable AI (XAI)**.

Mục tiêu của dự án là xây dựng một hệ thống giải thích dự đoán rủi ro tín dụng theo hướng **faithful explanation**. Hệ thống không chỉ dùng LLM để sinh explanation dễ hiểu bằng tiếng Việt, mà còn kiểm tra explanation đó có bám đúng bằng chứng XAI hay không.

Pipeline tổng quan:

```text id="vuauwa"
Raw Data
→ Feature Engineering
→ ML Model
→ Prediction
→ XAI Evidence
→ Explanation IR
→ LLM Explanation
→ Claim Extraction
→ Faithfulness Validation
→ UI Demo
```

## 2. Mục tiêu chính

Dự án tập trung vào câu hỏi:

> Làm thế nào để dùng LLM tạo explanation dễ hiểu cho prediction của Machine Learning model, nhưng vẫn kiểm soát được việc LLM có hallucinate, nói sai evidence, hoặc diễn giải vượt quá bằng chứng XAI hay không?

Các thành phần chính của hệ thống:

* **ML Model**: dự đoán rủi ro tín dụng của khách hàng.
* **XAI Evidence Layer**: tạo evidence giải thích từ model, ví dụ SHAP local evidence.
* **Explanation IR Layer**: chuẩn hóa XAI evidence thành dữ liệu có cấu trúc, dễ kiểm tra và dễ đưa vào LLM.
* **LLM Explanation Layer**: dùng LLM để diễn đạt prediction và XAI evidence thành explanation tiếng Việt.
* **Claim Extraction Layer**: extract các claim chính từ LLM explanation.
* **Faithfulness Validation Layer**: kiểm tra các claim có đúng với Explanation IR và XAI evidence hay không.
* **UI Demo**: hiển thị prediction, explanation và validation result.

## 3. Tiến độ hiện tại

| Batch   | Layer                      | Status             |
| ------- | -------------------------- | ------------------ |
| Batch A | Raw Data Audit             | Done               |
| Batch B | Feature Engineering        | Done               |
| Batch C | Feature Matrix / Registry  | Done               |
| Batch D | Leakage Audit & Data Split | Done               |
| Batch E | Preprocessing              | Done               |
| Batch F | Model Layer                | Done               |
| Batch G | XAI Evidence Layer         | Done               |
| Batch H | Explanation IR Layer       | Done / In Progress |
| Batch I | LLM Explanation Layer      | In Progress        |
| Batch J | Claim Extraction           | Planned            |
| Batch K | Faithfulness Validation    | Planned            |
| UI      | Explanation Dashboard      | Planned            |

## 4. Cấu trúc thư mục

```text id="ptg1f7"
llm-xai-next/
├── src/                     # Next.js application và server-side code
├── ml/                      # Python ML/XAI pipeline
│   ├── scripts/             # Batch scripts cho Data, Model, XAI và IR layers
│   └── registry/            # Feature registry, concept registry và mappings
├── data/                    # Local data folders, large files ignored by Git
├── artifacts/               # Local model/XAI artifacts, large files ignored by Git
├── docs/                    # Project documentation và progress notes
├── README.md                # Project overview và progress tracking
└── .gitignore               # Ignore generated data, model artifacts và secrets
```

## 5. Artifact Policy

Repository này **không lưu trực tiếp các large generated artifacts trên GitHub**.

GitHub chỉ lưu:

* source code
* schema files
* registry files
* prompt builders
* validation logic
* documentation
* small manifests hoặc summary reports

Các file lớn không được push lên GitHub, bao gồm:

* raw CSV datasets
* processed Parquet files
* trained model artifacts dạng `.joblib`
* full JSONL outputs
* full prediction CSV files
* large XAI evidence files

Large artifacts được lưu bên ngoài GitHub, ví dụ trong Amazon S3 private bucket. Khi cần gửi cho giảng viên hướng dẫn, các artifact này có thể được chia sẻ bằng pre-signed URL có thời hạn truy cập.

## 6. Development Setup

Cài đặt dependencies cho phần Next.js:

```bash id="0v1bsv"
npm install
```

Chạy development server:

```bash id="pu40pz"
npm run dev
```

Mở trình duyệt tại:

```text id="yazwql"
http://localhost:3000
```

Các Python scripts cho ML/XAI pipeline nằm trong:

```text id="22yboo"
ml/scripts/
```

Python environment và cách chạy từng batch có thể được mô tả riêng trong tài liệu hoặc báo cáo tương ứng.

## 7. Git Tracking Policy

Repository đã được cấu hình để ignore generated files, large artifacts và sensitive files, bao gồm:

```text id="4j6phf"
.env
.env.local
node_modules/
.next/
data/raw/
data/interim/
data/processed/
artifacts/models/
artifacts/preprocessing/
*.parquet
*.joblib
*.jsonl
```

Chỉ nên commit các file nhẹ và cần thiết, ví dụ:

* source code
* documentation
* registry
* schema
* prompt
* validation logic
* small summary reports

## 8. Progress Tracking

Tiến độ dự án được theo dõi thông qua:

* Git commit history
* GitHub Issues checklist theo từng batch
* progress table trong README
* báo cáo PDF riêng gửi cho giảng viên hướng dẫn

Báo cáo chi tiết theo tuần được nộp riêng dưới dạng PDF. README này chỉ cung cấp project overview và trạng thái triển khai hiện tại.

