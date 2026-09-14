# Claim-validation foundation v1

## Phạm vi

Foundation này freeze input lock, output contract v2, reason-code taxonomy v1
và numeric policy v1 trước khi viết claim validator. Scaffold
`contracts/llm-validation/claim_validation.schema.json` được giữ nguyên để truy
vết compatibility; output mới phải dùng `claim_validation_v2`.

## Official frozen inputs

Source of truth là
`config/research/ts-validation/validation_input_lock_v1.json`.

| Artifact | Records | SHA-256 |
| --- | ---: | --- |
| Canonical evidence packages | 216 | `37c25b261d496e7c9bf50a62141f93b5544a45af43208918d0eaf589d6307117` |
| Main canonical generations | 648 | `252edae8dd920c259a1da74d7b2f09b26558b994e01b3cd29dd60c0d6f9086ec` |
| Template baseline | 216 | `4d8e2e4c5d644ab33733d5bb2251bd1d6ebbb21588f662d709a0f01ee992de15` |
| Extracted claims | 14,640 | `216410f98ed3b7f43430eb34da17bb1e3b0928d561031bc37c2b8b0aa20f371c` |
| Extraction attempts | 680 | `b877911ce8983413a9a11d8607503b9339d82bb2855f71178333f11904b5e6a0` |
| Extraction failures | 10 | `c77788d8ac5e0ab2d309487d2f5499bdf6876137fc8e46ead479642c625f5add` |
| Finalized claims | 14,680 | `9b53bae17359f3f43415b62f0c7d9f6d9cbda21f2dcac43081bea93d406763f4` |
| Finalization changes | 1,288 | `ee819a5cbc91f69d2987b4a4894b3ef817be3eed6432d26b4198b571f573d97e` |

Main denominator là 648 = 638 usable + 10 unusable. Template baseline là
denominator riêng và không được trộn vào main cohort.

## Execution status và semantic status

Mỗi input claim phải có đúng một terminal result.

- `execution_status=SUCCESS`: có đúng một trong `SUPPORTED`, `UNSUPPORTED`,
  `CONTRADICTED`, `NOT_VERIFIABLE`, `NOT_APPLICABLE`; `error=null`.
- `execution_status=ERROR`: `validation_status=null`, reason thuộc family
  `SYSTEM`, và có `error_code`, `error_message`, `failed_stage`.

`PARTIALLY_SUPPORTED` không thuộc v2. Claims hiện đã atomic và repository chưa có
deterministic rule đủ chặt để dùng nhãn này mà không che extraction defect.

## Reason taxonomy

`claim_validation_reason_codes_v1` gồm 49 code thuộc 12 family:

`MATCH`, `PREDICTION`, `EXPOSURE`, `FEATURE`, `CONCEPT`, `DIRECTION`,
`NUMERIC`, `RANKING`, `MAGNITUDE`, `UNCERTAINTY`, `POLICY`, `SYSTEM`.

Chỉ `EXACT_MATCH`, `NORMALIZED_MATCH`, `TOLERANCE_MATCH` map tới
`SUPPORTED`. SYSTEM reason chỉ map tới execution `ERROR`. Hard-safety set được
freeze đúng ba code:

- `CAUSAL_OVERCLAIM`
- `GUARANTEE_OVERCLAIM`
- `CERTAINTY_OVERCLAIM`

## Evidence boundary và S0

Validation chỉ được dùng canonical Evidence Package mà LLM đã thấy.
`hidden_IR_prohibited=true`; full Explanation IR không được dùng để cứu claim.

S0 expose prediction. Feature, concept, direction, magnitude và ranking không
được map `SUPPORTED` từ hidden data; phải dùng exposure reason phù hợp. Numeric
prediction score vẫn được xử lý theo prediction source nếu chính value đó có
trong S0 package.

## Direction normalization

Canonical comparison direction dùng enum claim dạng singular:

- `increase_risk`
- `decrease_risk`
- `mixed`
- `neutral`
- `unknown`

Evidence enums `increases_risk` và `decreases_risk` được normalize lần lượt về
singular. Near-zero SHAP epsilon giữ đúng `1e-12`.

## Numeric tolerance

Tolerance chỉ được freeze khi source formatting chứng minh được:

- prediction score/threshold dạng percent hoặc probability: normalize về
  `[0,1]`, absolute tolerance `0.00005`, bằng nửa smallest displayed unit;
- count và rank: exact integer equality;
- feature values và các `other` numeric không có display precision đáng tin:
  `NOT_VERIFIABLE`, không tự đặt tolerance;
- unknown numeric role: `NOT_VERIFIABLE`.

Source references được ghi trực tiếp trong
`numeric_tolerance_policy_v1.json`.

## Phần để dành cho validator implementation

Foundation chưa implement:

- claim routing runtime;
- type-specific deterministic validators;
- semantic validator;
- human calibration;
- generation aggregation;
- paired bootstrap hoặc non-inferiority;
- selection result.

Không claim validation nào đã được chạy. Không có winner được chọn. Không có
official upstream JSONL artifact nào bị sửa bởi foundation này.
