# LLM-XAI Next

LLM-XAI Next là repository nghiên cứu và triển khai một pipeline giải thích dự đoán rủi ro tín dụng bằng sự kết hợp giữa:

- Machine Learning;
- Explainable AI;
- Large Language Models;
- claim-level evaluation;
- ứng dụng web phục vụ trình diễn và phân tích kết quả.

Bài toán thực nghiệm sử dụng dữ liệu **Home Credit Default Risk**. Hệ thống bắt đầu từ dữ liệu khách hàng, xây dựng mô hình dự đoán, tạo bằng chứng XAI, sinh lời giải thích bằng LLM, sau đó phân rã và kiểm tra từng phát biểu trước khi tổng hợp metric và lựa chọn cấu hình phù hợp.

Repository được refactor theo các nguyên tắc chính:

1. Mỗi giai đoạn nghiên cứu có input, output và contract rõ ràng.
2. Python và TypeScript giao tiếp qua artifact, không phụ thuộc implementation của nhau.
3. Mọi kết quả phải truy ngược được về dữ liệu, cấu hình và producer đã tạo ra nó.
4. Stage đắt tiền hoặc sử dụng provider không được tự động kích hoạt.
5. Ứng dụng Next.js chỉ đọc kết quả nghiên cứu đã hoàn tất, không chứa research logic.
6. Source hiện hành và source lịch sử được tách biệt rõ ràng.
7. Artifact chính thức không được chỉnh sửa thủ công hoặc ghi đè ngoài ý muốn.

---

## 1. Kiến trúc tổng thể

```text
Home Credit data
        ↓
Feature engineering và preprocessing
        ↓
Machine Learning prediction
        ↓
SHAP / Explainable AI
        ↓
Explanation IR
        ↓
Evidence packages S0–S5
        ↓
LLM generation
        ↓
Canonical generation index
        ↓
Contract validation
        ↓
Atomic claim extraction
        ↓
Claim finalization
        ↓
Claim validation và semantic evaluation
        ↓
Generation-level metrics
        ↓
Model và evidence selection
        ↓
Next.js demo
```

Pipeline được chia thành bốn lớp chính:

```text
Data và Machine Learning
→ Evidence và Explainable AI
→ LLM generation và claim evaluation
→ Application và visualization
```

---

## 2. Cấu trúc repository

```text
src/                 Next.js và các adapter chỉ đọc artifact nghiên cứu
research/ml/         Python: dữ liệu, model, SHAP, IR và evidence S0–S5
research/llm/        TypeScript: generation, canonicalization, contract và claims
contracts/           Artifact contracts giữa Python và TypeScript
config/research/     Policy, prompt và cấu hình được version hóa
tests/research/      Regression tests của active pipeline
infra/aws-batch/     Hạ tầng batch có provenance, không tự động triển khai
data/                Dữ liệu, manifest và report
artifacts/           Artifact chính thức hoặc snapshot nghiên cứu
docs/                Kiến trúc, quyết định thiết kế và báo cáo
legacy/              Source lịch sử, không thuộc active import graph
```

### `src/`

Chứa ứng dụng Next.js và các adapter dùng để đọc artifact nghiên cứu.

`src/` chịu trách nhiệm:

- hiển thị prediction;
- hiển thị bằng chứng XAI;
- hiển thị lời giải thích của LLM;
- hiển thị metric và trạng thái validation;
- phục vụ giao diện demo.

`src/` không thực hiện:

- feature engineering;
- huấn luyện model;
- tính SHAP;
- gọi LLM;
- claim extraction;
- claim validation;
- model selection.

Ứng dụng chỉ đọc artifact đã được tạo và kiểm tra bởi pipeline nghiên cứu.

---

### `research/ml/`

Chứa pipeline Python từ dữ liệu thô đến Evidence Package.

Luồng chính:

```text
Data audit
→ feature engineering
→ matrix construction
→ split
→ preprocessing
→ model training
→ model evaluation
→ XAI
→ Explanation IR
→ evidence construction
```

Python chịu trách nhiệm:

- đọc và kiểm tra dữ liệu Home Credit;
- xây dựng đặc trưng;
- tạo train, validation và test split;
- huấn luyện và đánh giá model;
- sinh prediction probability;
- tính SHAP và XAI metadata;
- xây dựng Explanation IR;
- tạo Evidence Package S0–S5.

Điểm kết thúc của pipeline Python là artifact có contract rõ ràng để TypeScript sử dụng.

---

### `research/llm/`

Chứa pipeline TypeScript từ Evidence Package đến các artifact phục vụ đánh giá LLM.

Các nhóm chức năng chính:

```text
generation/
canonicalization/
contract_validation/
claim_extraction/
claim_finalization/
validation/
aggregation/
selection/
```

TypeScript có thể chịu trách nhiệm:

- xây dựng prompt từ Evidence Package;
- gọi hoặc điều phối LLM provider;
- lưu raw response và runtime metadata;
- canonicalize output của nhiều model;
- kiểm tra structured output;
- tách narrative thành atomic claims;
- chuẩn hóa claim;
- đối chiếu claim với prediction, SHAP và IR;
- tổng hợp metric;
- tạo artifact cho bước lựa chọn cấu hình.

Không phải mọi module khái niệm đều nhất thiết có producer active trong mọi phiên bản. Danh sách command từ dispatcher là nguồn chính xác để xác định stage nào có thể chạy.

---

### `contracts/`

Chứa schema và artifact contract giữa các stage.

Contract xác định:

- tên field;
- kiểu dữ liệu;
- required field;
- version;
- key;
- invariant;
- quan hệ giữa input và output.

Các boundary chính:

```text
Python model output
→ Explanation IR contract

Explanation IR
→ Evidence Package contract

Evidence Package
→ LLM generation contract

Generation record
→ Atomic claim contract

Atomic claim
→ Validation result contract
```

Python và TypeScript không import implementation của nhau. Hai bên chỉ giao tiếp bằng artifact tuân theo contract.

Cách tách này giúp:

- giảm coupling;
- kiểm thử từng boundary độc lập;
- thay implementation mà không phá toàn pipeline;
- duy trì provenance rõ ràng;
- tái sử dụng artifact mà không phụ thuộc runtime đã tạo ra nó.

---

### `config/research/`

Chứa cấu hình nghiên cứu được version hóa.

Có thể bao gồm:

- feature policy;
- split policy;
- XAI policy;
- evidence policy;
- prompt template;
- output schema;
- claim extraction policy;
- claim finalization policy;
- validation policy;
- provider configuration;
- selection criteria.

Cấu hình ảnh hưởng đến kết quả nghiên cứu phải được lưu với version hoặc hash trong manifest.

Secret không được lưu tại đây. API key và credential phải được cung cấp qua environment hoặc secret manager.

---

### `tests/research/`

Chứa regression test của active research pipeline.

Test tập trung vào:

- schema;
- deterministic transform;
- invariant;
- key uniqueness;
- source span;
- provenance;
- semantic signature;
- claim ID;
- replay;
- idempotence;
- compatibility giữa các stage.

Regression test không thay thế full experimental validation, nhưng phải phát hiện những thay đổi làm sai contract hoặc phá tính tái lập.

---

### `infra/aws-batch/`

Chứa định nghĩa hạ tầng và runtime phục vụ batch generation.

Có thể gồm:

- Docker image;
- container entrypoint;
- AWS Batch job definition;
- compute environment;
- S3 input/output layout;
- vLLM startup;
- checkpoint và resume policy;
- runtime manifest;
- deployment documentation.

Hạ tầng không được tự động triển khai chỉ vì chạy test hoặc build repository.

Mọi thao tác có thể phát sinh chi phí phải được thực hiện có chủ đích.

---

### `data/`

Chứa dữ liệu, manifest và report của pipeline.

Cấu trúc có thể bao gồm:

```text
data/raw/
data/interim/
data/processed/
data/manifests/
data/reports/
```

Các file lớn thường bị Git ignore và được lưu cục bộ hoặc trong object storage.

Không nên xem đường dẫn file là danh tính artifact. Danh tính artifact phải dựa trên:

- schema version;
- SHA-256;
- record count;
- producer version;
- source commit;
- configuration hash;
- creation timestamp.

---

### `artifacts/`

Chứa các artifact chính thức hoặc snapshot phục vụ tái lập thí nghiệm.

Artifact có thể bao gồm:

- model;
- preprocessing state;
- Explanation IR;
- Evidence Package;
- generation output;
- canonical index;
- atomic claims;
- validation result;
- aggregation result;
- selection result.

Artifact chính thức không được chỉnh sửa thủ công.

Khi cần thay đổi, phải tạo artifact mới bằng producer phù hợp và ghi provenance mới.

---

### `docs/`

Chứa tài liệu mô tả:

- kiến trúc;
- artifact contract;
- quy trình chạy;
- quyết định thiết kế;
- audit report;
- kết quả thí nghiệm;
- giới hạn của hệ thống.

Root README chỉ mô tả cấu trúc ổn định của repository. Các số liệu và kết quả của từng lần chạy nên nằm trong manifest hoặc report riêng.

---

### `legacy/`

Chứa source lịch sử được giữ lại để tham khảo hoặc tái dựng quyết định cũ.

Ví dụ:

- pipeline explanation phiên bản trước;
- batch runner cũ;
- flow tích hợp cũ;
- selection prototype;
- web mock;
- report generator cũ.

Quy tắc bắt buộc:

```text
Active source không import từ legacy/
Active CLI không dispatch vào legacy/
Application không đọc trực tiếp artifact legacy/
```

`legacy/` không phải một phần của active import graph.

---

## 3. Pipeline Machine Learning

Pipeline Machine Learning thực hiện các bước:

```text
Home Credit data
→ audit
→ feature engineering
→ matrix construction
→ split
→ preprocessing
→ model training
→ model evaluation
→ SHAP/XAI
```

### Data audit

Kiểm tra:

- schema dữ liệu;
- số lượng record;
- target;
- missing value;
- duplicate;
- kiểu dữ liệu;
- phân phối bất thường.

### Feature engineering

Tạo đặc trưng từ dữ liệu application và các bảng liên quan.

Mỗi feature cần có:

- tên ổn định;
- định nghĩa;
- source;
- transformation;
- data type;
- missing-value policy.

### Model training

Repository hỗ trợ khảo sát nhiều mô hình Machine Learning, ví dụ:

- Logistic Regression;
- Random Forest;
- HistGradientBoostingClassifier.

Model được lựa chọn dựa trên metric dự đoán và yêu cầu tích hợp XAI, không chỉ dựa trên một chỉ số đơn lẻ.

### Explainable AI

XAI xác định các đặc trưng ảnh hưởng đến prediction.

Repository có thể khảo sát hoặc kết hợp:

- KernelSHAP;
- SmartSHAP;
- feature filtering;
- concept grouping;
- evidence quality policy.

Kết quả XAI chưa được gửi trực tiếp cho LLM mà được chuẩn hóa qua Explanation IR.

---

## 4. Explanation IR

**IR – Intermediate Representation** là lớp biểu diễn trung gian giữa Machine Learning/XAI và LLM.

IR chuẩn hóa các thông tin như:

- prediction label;
- prediction probability;
- decision threshold;
- feature identifier;
- feature value;
- SHAP value;
- impact direction;
- importance;
- semantic label;
- concept group;
- source metadata;
- quality metadata.

Mục đích của IR:

1. Tách logic XAI khỏi prompt.
2. Giúp nhiều LLM nhận cùng một cấu trúc dữ liệu.
3. Tránh gửi trực tiếp tên feature kỹ thuật không có ngữ nghĩa.
4. Hỗ trợ kiểm tra lại claim sau khi LLM sinh output.
5. Duy trì provenance từ narrative về dữ liệu nguồn.

IR phải là artifact có version, schema và manifest riêng.

---

## 5. Evidence Package S0–S5

Evidence Package là đầu vào chuẩn cho LLM generation.

Các mức S0–S5 biểu diễn những chiến lược cung cấp bằng chứng khác nhau.

| Mức | Mục đích |
| --- | --- |
| S0 | Baseline với rất ít hoặc không có feature evidence |
| S1 | Feature-level evidence cơ bản |
| S2 | Feature evidence có semantic enrichment |
| S3 | Evidence được chọn lọc và rút gọn |
| S4 | Evidence giàu thông tin hơn cho case khó |
| S5 | Backend-controlled structure hoặc guidance đầy đủ hơn |

Ý nghĩa chính xác của từng mức phải được xác định bởi evidence policy được version hóa, không hard-code trong application.

Cùng một case có thể được chạy qua nhiều evidence level để đo ảnh hưởng của lượng và cấu trúc bằng chứng tới chất lượng lời giải thích.

---

## 6. Canonical cohort và paired evaluation

**Canonical cohort** là tập case đánh giá cố định được sử dụng chung giữa các model và evidence level.

Mỗi vị trí đánh giá thường được xác định bởi key dạng:

```text
model
× case
× evidence level
× repeat
```

Canonicalization có nhiệm vụ:

- xác định đúng cohort;
- hợp nhất output từ nhiều nguồn;
- phát hiện missing;
- phát hiện duplicate;
- giữ lại generation không khả dụng;
- chuẩn hóa metadata;
- tạo một index chung cho các stage sau.

Generation không khả dụng không được xóa âm thầm. Chúng phải được giữ lại với trạng thái và nguyên nhân để denominator của phép đánh giá không bị thay đổi.

**Paired evaluation** nghĩa là cùng một case và evidence level được so sánh giữa các model trên điều kiện tương đương.

---

## 7. LLM generation

Repository có thể hỗ trợ nhiều kiểu runtime:

- provider API;
- local runtime;
- vLLM;
- AWS Batch;
- containerized GPU job.

Mỗi generation phải lưu đủ metadata để tái lập và audit, bao gồm:

- model;
- provider;
- prompt version;
- prompt hash;
- schema version;
- decoding configuration;
- case ID;
- evidence level;
- attempt;
- runtime status;
- raw response hash;
- parsed output;
- error information.

Một provider call thành công không đồng nghĩa với output hợp lệ. Runtime success, JSON parsing và schema validation là các trạng thái khác nhau.

---

## 8. Contract validation

Contract validation kiểm tra output của LLM có tuân theo structured-output contract hay không.

Các kiểm tra có thể gồm:

- JSON parse;
- required field;
- data type;
- enum;
- field dependency;
- source reference;
- feature identifier;
- direction representation;
- uncertainty field;
- policy field.

Contract validation chỉ xác nhận output đúng cấu trúc.

Nó không khẳng định nội dung lời giải thích đúng với prediction hoặc SHAP.

---

## 9. Atomic claim extraction

Một narrative của LLM thường chứa nhiều phát biểu trong cùng một câu hoặc đoạn.

Atomic claim extraction tách narrative thành các phát biểu nhỏ, mỗi phát biểu chỉ chứa một nội dung chính có thể kiểm chứng độc lập.

Ví dụ:

```text
“Khách hàng có rủi ro cao vì EXT_SOURCE_3 thấp
và tỷ lệ khoản vay trên giá trị tài sản cao.”
```

có thể được tách thành:

```text
Khách hàng được dự đoán có rủi ro cao.
EXT_SOURCE_3 có giá trị thấp.
EXT_SOURCE_3 làm tăng rủi ro.
Tỷ lệ khoản vay trên giá trị tài sản cao.
Tỷ lệ này làm tăng rủi ro.
```

Claim extraction phải giữ:

- source section;
- source text;
- source span;
- claim type;
- subject;
- predicate;
- numeric value;
- provenance;
- semantic signature;
- deterministic claim ID.

Việc tách claim không được sửa nội dung hoặc tự tạo bằng chứng mới.

---

## 10. Claim finalization

Claim finalization là stage deterministic chuẩn hóa output của claim extraction trước khi validation.

Stage này có thể thực hiện:

- canonicalize field;
- sửa provenance theo rule chung;
- tách numeric fact bị gộp;
- loại duplicate semantic;
- đánh lại local index;
- tạo deterministic claim ID;
- kiểm tra source span;
- kiểm tra count completeness;
- ghi change log.

Finalization không được:

- gọi LLM để viết lại nội dung;
- sửa claim nhằm làm kết quả đẹp hơn;
- suy diễn bằng chứng không có trong source;
- thay thế semantic validation.

Mọi thay đổi phải có rule code và change record.

---

## 11. Claim validation

Claim validation đối chiếu từng atomic claim với nguồn dữ liệu phù hợp.

Nguồn kiểm tra có thể gồm:

- prediction;
- probability;
- threshold;
- SHAP;
- impact direction;
- selected feature;
- concept group;
- Explanation IR;
- Evidence Package;
- policy.

Kết quả validation có thể phân biệt:

- supported;
- contradicted;
- unsupported;
- not applicable;
- policy-related.

Ví dụ:

```text
Claim:
“EXT_SOURCE_3 làm tăng rủi ro.”

Source:
IR cho biết EXT_SOURCE_3 làm giảm rủi ro.

Result:
contradicted
```

Claim validation là cơ sở để đo faithfulness, không phải JSON/schema compliance.

---

## 12. Aggregation và metric

Sau claim validation, kết quả có thể được tổng hợp theo:

```text
claim
→ generation
→ case
→ evidence level
→ model
```

Các nhóm metric có thể gồm:

- claim support rate;
- contradiction rate;
- unsupported rate;
- direction accuracy;
- numeric accuracy;
- evidence coverage;
- causal overclaim rate;
- policy compliance;
- language quality;
- latency;
- token usage;
- compute cost.

Metric definition phải được version hóa và ghi rõ denominator.

Không được âm thầm loại generation lỗi khỏi denominator nếu protocol không cho phép.

---

## 13. Selection

Selection sử dụng kết quả aggregation để lựa chọn:

- model mặc định;
- evidence level mặc định;
- fallback configuration;
- cấu hình cho case khó;
- case đại diện cho demo;
- trade-off giữa chất lượng, độ trễ và chi phí.

Selection phải là một producer riêng, không được nhúng ngầm vào UI hoặc viết tay trong report.

Một selection artifact nên ghi:

- candidate set;
- metric version;
- constraints;
- tie-breaking rule;
- selected configuration;
- fallback;
- source artifact hashes.

---

## 14. Giao diện chạy chính thức

Mọi stage active được gọi từ repository root bằng một command family:

```bash
npm run research -- <stage> [arguments]
```

Xem danh sách command khả dụng:

```bash
npm run research -- --help
```

Ví dụ nhóm command:

```text
ml:data-audit
ml:target-audit
ml:features
ml:matrix
ml:split
ml:preprocess
ml:model-ready-audit
ml:train
ml:xai
ml:xai-quality
ml:ir
ml:evidence
ml:evidence-subset

llm:generate
llm:aggregate
llm:filter-deepseek
llm:canonicalize
llm:contract
llm:claims
llm:claims-finalize
```

Danh sách thực tế từ dispatcher là nguồn chính xác hơn README.

Repository không cung cấp `run-all` cho toàn pipeline vì:

- một số stage có chi phí lớn;
- một số stage gọi provider;
- một số stage phụ thuộc GPU hoặc AWS;
- output chính thức không được ghi đè ngoài ý muốn;
- người chạy cần kiểm tra artifact sau từng boundary.

---

## 15. Artifact và provenance

Mỗi artifact quan trọng nên có manifest chứa:

```text
artifact type
schema version
producer
producer version
source commit
configuration version
input paths
input SHA-256
output path
output SHA-256
record count
created_at
runtime metadata
```

Đường dẫn trong manifest nên là project-relative.

Absolute path có thể được lưu như metadata phụ, nhưng không được dùng làm danh tính artifact.

Provenance cần hỗ trợ chuỗi truy ngược:

```text
Claim
→ Generation
→ Evidence Package
→ Explanation IR
→ SHAP record
→ Model prediction
→ Input case
```

---

## 16. Tính tái lập

Các deterministic stage phải hỗ trợ:

- cùng input tạo cùng output;
- deterministic ordering;
- deterministic ID;
- exact source span;
- stable semantic signature;
- idempotence;
- manifest hash;
- replay từ stored response khi phù hợp.

Stage sử dụng LLM không thể đảm bảo byte-identical generation trong mọi trường hợp, vì vậy phải lưu raw response và runtime metadata để các bước sau có thể replay mà không gọi lại provider.

---

## 17. Quy tắc đối với artifact chính thức

Không chỉnh sửa thủ công artifact trong:

```text
data/manifests/
data/reports/
artifacts/
```

Không ghi đè artifact chính thức chỉ để thử code.

Regression output nên được ghi vào thư mục riêng, ví dụ:

```text
.refactor-validation/
.tmp/
data/reports/scratch/
```

Các thư mục này phải bị Git ignore.

Khi tạo artifact mới:

1. Dùng output path mới.
2. Ghi manifest.
3. Tính SHA-256.
4. Kiểm tra record count.
5. Chạy regression test.
6. Chỉ promote thành official artifact sau audit.

---

## 18. Quy tắc an toàn và chi phí

Không tự động chạy các tác vụ sau khi chỉ kiểm tra source:

- provider generation;
- DeepSeek API;
- Bedrock;
- AWS Batch;
- Qwen/Phi generation;
- full claim extraction;
- full claim validation;
- model retraining;
- selection;
- infrastructure deployment.

Secret phải được cung cấp qua environment.

Không commit:

- API key;
- AWS credential;
- provider token;
- raw secret;
- local absolute path có thông tin nhạy cảm.

---

## 19. Development workflow

### Cài dependency

```bash
npm ci
```

Cài Python environment theo tài liệu trong `research/ml/`.

### Kiểm tra command

```bash
npm run research -- --help
```

### Typecheck

```bash
npx tsc -p tsconfig.research.json --noEmit
```

### Chạy regression test

```bash
npx tsx --test tests/research/llm/<test-file>.test.ts
```

### Nguyên tắc khi thay đổi pipeline

Mọi thay đổi tại một boundary cần xem xét:

1. Contract có thay đổi không?
2. Schema version có cần tăng không?
3. Artifact cũ còn tương thích không?
4. ID hoặc key có thay đổi không?
5. Manifest có ghi đúng producer version không?
6. Test có bao phủ invariant mới không?
7. Output có còn deterministic không?
8. UI có cần adapter mới không?

---

## 20. Source of truth

Không sử dụng README để xác định kết quả mới nhất của thí nghiệm.

Nguồn chính xác theo thứ tự:

```text
Artifact manifest
→ versioned report
→ active CLI
→ module README
→ root README
```

Root README mô tả kiến trúc và nguyên tắc chung.

Các con số như:

- số record;
- số generation;
- số claim;
- pass/fail;
- metric;
- model được chọn;

phải được đọc từ manifest hoặc report tương ứng với từng lần chạy.

---

## 21. Legacy boundary

`legacy/` được giữ để:

- tham khảo quyết định cũ;
- tái dựng lịch sử;
- so sánh implementation;
- hỗ trợ migration khi cần.

Source trong `legacy/` không được xem là active chỉ vì vẫn còn trong repository.

Một module chỉ thuộc active pipeline khi:

1. được import từ active source;
2. được dispatcher expose;
3. có contract hiện hành;
4. có regression test;
5. có producer hoặc documentation rõ ràng.

---

## 22. Mục tiêu kiến trúc

Thiết kế của LLM-XAI Next hướng tới một pipeline có thể trả lời đầy đủ các câu hỏi:

```text
Dữ liệu nào đã tạo prediction này?
Model và cấu hình nào đã được sử dụng?
SHAP evidence nào được đưa cho LLM?
LLM đã nhận evidence level nào?
Lời giải thích đã sinh ra những claim nào?
Claim nào được dữ liệu hỗ trợ?
Claim nào mâu thuẫn hoặc không có căn cứ?
Metric nào dẫn đến lựa chọn cấu hình cuối?
UI đang hiển thị artifact phiên bản nào?
```

Mục tiêu cuối cùng không chỉ là tạo ra một lời giải thích dễ đọc, mà là tạo ra lời giải thích:

- có nguồn gốc rõ ràng;
- có thể kiểm chứng;
- có thể tái lập;
- có thể so sánh;
- có thể audit;
- phù hợp để tích hợp vào ứng dụng thực tế.
