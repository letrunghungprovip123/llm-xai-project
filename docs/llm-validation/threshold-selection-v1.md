# Thiết kế threshold và chọn configuration v1

## Kết luận thiết kế

Không dùng công thức `T* = max(T_risk, T_stat, T_knee)`. Ba thành phần đó không cùng đơn vị và không trả lời cùng một câu hỏi:

- Risk gate hỏi configuration có đủ an toàn để xét triển khai hay không.
- Statistical non-inferiority hỏi một configuration nhẹ hơn có kém best quá biên cho phép hay không.
- Evidence knee chỉ mô tả điểm lợi ích giảm dần theo burden thực.

Thuật toán chính thức là quy trình tuần tự:

1. Generation hard gate.
2. Generation quality bằng weighted geometric mean.
3. Configuration hard gates.
4. Paired stratified bootstrap theo case.
5. Paired non-inferiority.
6. Pareto filtering.
7. Chọn mức evidence tối thiểu và tie-break theo thứ tự đã freeze.
8. Đánh giá S5 riêng như fallback.
9. Chỉ sau human calibration mới dùng probability threshold cho runtime.

Các con số được freeze trong `config/llm-validation/selection_policy_v1.json` trước khi xem kết quả validation cuối.

## 1. Canonical denominator

Configuration là `model_id × evidence_level`, với 36 planned cases. Mọi generation lỗi vẫn ở denominator và nhận `q=0`.

Trạng thái hiện tại có 648 planned generation, 638 usable và 10 unusable. Điều này có hai hệ quả:

- Không được báo Phi là `209/209 = 100%`; reliability đúng là `209/216` ở cấp model.
- 10 lỗi không được rerun để thay thế official result và không được xóa trước thống kê.

Khi tính từng configuration, denominator tiếp tục là 36. Một level có 35 usable chỉ đạt `35/36`, không phải `35/35`.

## 2. Generation hard gate

Generation chỉ qua hard gate khi đồng thời:

- output usable;
- schema valid;
- không có contradicted claim;
- không có causal overclaim.

Nếu bất kỳ điều kiện nào fail, `q=0`. Cost, latency hoặc narrative tốt không được bù lỗi contradiction hay causal overclaim.

## 3. Generation quality không phải xác suất

Các soft metric trong `[0,1]`:

| Metric | Weight |
|---|---:|
| Weighted faithfulness | 0.30 |
| Direction accuracy | 0.25 |
| SHAP-mass coverage | 0.20 |
| Policy compliance | 0.10 |
| Narrative synthesis | 0.10 |
| Language compliance | 0.05 |

Quality dùng weighted geometric mean. Metric không applicable được loại khỏi tích và tổng weight được renormalize. Không gán metric NA thành 0.

Geometric mean được chọn vì một metric rất thấp phải kéo quality xuống mạnh. Arithmetic mean có thể để narrative hoặc language cao che lấp faithfulness thấp.

`q=0.90` chỉ là composite quality index 0.90. Nó không có nghĩa generation có 90% xác suất acceptable.

## 4. Configuration hard gates

Một configuration chỉ được đưa sang bước thống kê khi qua toàn bộ gate đã freeze:

- observed usable rate = 100%;
- observed schema validity = 100%;
- contradicted claim rate = 0%;
- causal overclaim rate = 0%;
- direction accuracy ≥ 95%;
- unsupported claim rate ≤ 5%;
- weighted faithfulness ≥ 90%;
- SHAP-mass coverage ≥ 80%;
- policy compliance ≥ 95%;
- language compliance ≥ 98%.

Đây là deployment gate, không phải quy tắc xóa model khỏi báo cáo nghiên cứu.

Observed `36/36` vẫn có bất định. Wilson 95% interval cho `36/36` có lower bound xấp xỉ 0.904, nên báo cáo phải hiển thị cả observed rate và interval. Policy v1 gate theo observed rate; Wilson interval dùng để mô tả bất định, không được diễn giải 36/36 là population reliability chắc chắn 100%.

Nếu không configuration nào pass:

- không tự hạ threshold;
- không đổi biên non-inferiority;
- không chọn winner để deploy;
- chỉ trả lowest-risk candidate cho phân tích;
- bật human review/escalation;
- mọi sensitivity analysis sau đó phải ghi rõ là post-hoc.

## 5. Paired stratified bootstrap

Đơn vị resample là `case_id`, không phải claim và không phải generation rời rạc.

Mỗi bootstrap iteration:

1. Chia case theo selection stratum.
2. Trong từng stratum, sample có hoàn lại đúng số case ban đầu.
3. Khi một case được chọn, giữ toàn bộ candidate cells của case đó.
4. Ghép strata lại và tính mean paired difference.

Policy v1 dùng 5,000 iterations, seed cố định `20260714` và confidence 95%.

Claim không độc lập: nhiều claim cùng một generation dùng chung prompt, evidence và lỗi sinh văn bản. Resample claim sẽ làm sample size giả lớn và confidence interval quá hẹp.

## 6. Non-inferiority

Với reference best `b` và candidate `c`:

`delta_i = q_i,b - q_i,c`

Candidate non-inferior khi one-sided upper 95% bootstrap bound của mean `delta` không vượt `0.03`.

Biên 0.03 nghĩa là candidate nhẹ hơn vẫn được chấp nhận nếu biên xấu hợp lý cho thấy nó không kém best quá 3 điểm quality.

Reference best được chọn trong nhóm đã qua hard gate bằng quality LCB 95% cao nhất; point estimate chỉ là tie-break. Cách này thận trọng hơn chọn winner duy nhất bằng mean quan sát.

Không dùng điều kiện `LCB(candidate) ≥ LCB(best)`: điều kiện đó bỏ mất paired covariance giữa cùng case.

## 7. Pareto filtering

Vector Pareto:

- maximize quality LCB và reliability;
- minimize cost per faithful generation, p95 latency, mean input tokens và extractiveness.

Một candidate bị dominated khi candidate khác không tệ hơn ở mọi tiêu chí và tốt hơn ít nhất một tiêu chí.

Metric cost/latency còn thiếu phải để `NULL`. Candidate thiếu metric không được phép dominate candidate khác trên metric đó. Không điền 0 hoặc ước lượng không có provenance.

## 8. Minimum sufficient evidence và knee

Default selection chỉ xét S1–S4:

- S0 là no-evidence baseline và không eligible.
- S5 là backend-control/fallback, không nằm trên cùng đường narrative evidence.

Knee dùng `mean_input_tokens` làm trục x và quality LCB làm trục y, tính riêng từng model. Không dùng level index 1–4 như khoảng cách bằng nhau và không ghép max của nhiều model thành một đường lai.

Với chỉ bốn điểm S1–S4, knee có độ phân giải thấp. Vì vậy code chỉ trả `SUPPORTING_EVIDENCE_ONLY`; knee không phải hard gate và không được phép override non-inferiority.

Sau hard gate, non-inferiority và Pareto, tie-break lexicographic:

1. evidence level thấp nhất;
2. cost per faithful generation thấp nhất;
3. p95 latency thấp nhất;
4. extractiveness thấp nhất;
5. narrative synthesis cao nhất;
6. candidate ID để kết quả deterministic khi mọi metric bằng nhau.

## 9. S5 fallback

S5 được chọn riêng trong các S5 configuration đã qua hard gate. Nó không tranh default bằng quy tắc level thấp nhất.

S5 phải được báo riêng trên skeleton compliance, faithfulness, contradiction, extractiveness, copy ratio, narrative synthesis, cost và latency. S5 có thể là fallback tốt dù không phải default narrative configuration.

## 10. Runtime threshold sau human calibration

Cost ratio false accept:false reject bằng 9:1 dẫn đến threshold 0.90 chỉ khi đầu vào là xác suất `P(acceptable)` đã calibration.

Sau Phase 6, fit mô hình đã pre-register, ví dụ:

`p_accept = sigmoid(a + b × q)`

Runtime accept khi:

- generation hard gate pass; và
- calibrated `p_accept ≥ 0.90`.

Trước khi bật, phải báo Brier score, expected calibration error, false accept rate và false reject rate trên human-labeled data. Hàm runtime trong code chỉ áp dụng hệ số calibration được cung cấp; nó cố ý không tự fit trên validation winner.

## 11. Những dữ liệu còn thiếu trước final selection

Không được chạy kết luận Phase 9 cho tới khi có:

- claim validations đã merge deterministic + semantic;
- đủ 648 generation-level records, bao gồm 10 record zero;
- human calibration và error analysis;
- quality bootstrap CI/LCB;
- cost provenance cho DeepSeek và AWS Batch allocation cho Qwen/Phi;
- p95 latency và extractiveness cùng định nghĩa frozen.

Code threshold hiện tại là implementation đã kiểm thử của policy, chưa phải kết quả chọn model. Điều này ngăn việc thay threshold sau khi biết model nào thắng.

