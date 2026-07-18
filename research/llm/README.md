# TypeScript research pipeline

TypeScript bắt đầu từ Evidence Package JSONL do Python tạo. Các module active chạy tuần tự: `narrative` → `canonicalization` → `contract_validation` → partial `claim_extraction`. `selection` chỉ chứa policy/engine cho nghiên cứu tương lai; current workflow chưa có upstream artifacts đủ để chạy selection thật.

Mọi stage active được gọi qua `npm run research -- <stage> [arguments]`. `main.ts` chỉ parse CLI, `index.ts` là public API cho tests và core files chứa logic. Artifact fields giữ snake_case; I/O side effects nằm ở rìa module.

Official generations, canonical index, contract metrics và claims không được rewrite khi regression. Dùng `.refactor-validation/` làm output tạm và xem README của từng module cho input, key, invariant và failure behavior.
