# LLM-XAI Next

Repository này chứa một ứng dụng Next.js và pipeline nghiên cứu giải thích dự đoán rủi ro tín dụng. Mục tiêu hiện tại là giữ được chuỗi provenance từ dữ liệu Home Credit đến narrative và atomic claims, không tuyên bố các stage validation/selection chưa có producer hoàn chỉnh.

## Kiến trúc

```text
src/                 Next.js và adapter chỉ đọc kết quả nghiên cứu
research/ml/         Python: dữ liệu, model, SHAP, IR và evidence S0–S5
research/llm/        TypeScript: narrative, canonical, contract và claims
contracts/           Artifact contracts giữa Python và TypeScript
config/research/     Policy/prompt/config được version hóa
tests/research/      Regression tests của active pipeline
legacy/              Source lịch sử, không thuộc active import graph
infra/aws-batch/     Hạ tầng batch có provenance, không tự được thực thi
data/, artifacts/    Official/local artifacts; phần lớn file lớn bị Git ignore
```

Python kết thúc tại Evidence Package JSONL. TypeScript bắt đầu từ artifact đó; hai ngôn ngữ không import implementation của nhau. `src/` không chứa research logic và chỉ đọc artifact đã hoàn tất.

## Active pipeline và điểm dừng

```text
Home Credit
→ feature engineering
→ preprocessing
→ HistGradientBoosting
→ SHAP/XAI
→ Explanation IR v2
→ evidence exposure 2.1, S0–S5
→ LLM narrative
→ canonical generation index
→ deterministic contract validation
→ partial atomic claim extraction v2.1 smoke
```

Pipeline hiện dừng tại partial claim extraction v2.1. Claim validation hiện hành, semantic validation, generation-level aggregation, paired observations, bootstrap, human calibration và final configuration selection chưa hoàn chỉnh. Repository không có command active để chạy selection thật.

## Giao diện chạy chính thức

Chỉ dùng một command family ở repository root:

```bash
npm run research -- <stage> [arguments]
```

Các stage active:

```text
ml:data-audit       ml:target-audit    ml:features
ml:matrix           ml:split           ml:preprocess
ml:train            ml:xai             ml:xai-quality
ml:ir               ml:evidence

llm:generate        llm:aggregate      llm:filter-deepseek
llm:canonicalize    llm:contract       llm:claims
```

Xem danh sách từ dispatcher:

```bash
npm run research -- --help
```

Mỗi module README mô tả input/output, key, invariant và cách truyền arguments. Không có `run-all`: các stage đắt tiền hoặc có provider phải được chạy có chủ đích và output phải trỏ tới vị trí mới.

## Golden invariants hiện tại

| Boundary | Invariant |
| --- | ---: |
| Application rows | 307,511 |
| Engineered features | 166 |
| Split train / validation / test | 215,257 / 46,127 / 46,127 |
| Model-ready columns | 213 |
| Selected model | HistGradientBoosting |
| XAI / Explanation IR v2 | 120 / 120 |
| Evidence packages / evaluation subset | 720 / 216 |
| Qwen total / usable | 216 / 216 |
| DeepSeek total / usable / unusable | 216 / 213 / 3 |
| Phi total / usable / unusable | 216 / 209 / 7 |
| Template total / usable | 216 / 216 |
| Canonical main usable / unusable | 638 / 10 trong 648 |
| Contract pass / fail | 602 / 46 |
| Claim attempts / successful generations / claims | 21 / 19 / 383 |

Mười canonical generation unusable vẫn được giữ để audit. `direction_surface_match` hiện là `null` cho đủ 648 contract records; không diễn giải field này như metric đã implement.

## Artifact và provenance

Không rewrite official artifacts trong `data/manifests/`, `data/reports/` hoặc `artifacts/`. Regression output của phiên refactor nằm trong `.refactor-validation/` và bị Git ignore. Manifest mới nên dùng project-relative path, SHA-256, record count, tool version, source commit và `created_at`; absolute path chỉ là metadata phụ.

Secrets nằm trong environment và không được commit. Không tự chạy DeepSeek, Bedrock, Qwen/Phi generation, AWS Batch, full claim extraction, retraining hoặc selection khi chỉ kiểm tra code.

## Legacy boundary

`legacy/` giữ Python explanation v1, TypeScript Batch I cũ, J1/J2/J3, K finalization, integrated I–J flow và web mock lịch sử. Active research không import từ thư mục này. Các wrapper trong `batch/` và `ml/scripts/` chỉ duy trì command cũ trong thời gian chuyển tiếp; source-of-truth nằm trong `research/`.
