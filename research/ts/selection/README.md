# Selection policy và engine

Module này chứa frozen policy v1, generation-quality helpers và threshold engine cho phase sau. Input thiết kế gồm configuration candidates và paired observations; các producer claim validation, generation aggregation, paired statistics, human calibration hiện chưa hoàn chỉnh.

Không có `llm:selection` trong unified active dispatcher và không chạy selection thật ở trạng thái nghiên cứu hiện tại. Module không có executable CLI trong active command surface. Policy source-of-truth là `config/research/ts-validation/selection_policy_v1.json`; `generation_id`, `candidate_id` và `case_id` là các join keys chính.

Tests chỉ kiểm pure functions và policy loader. Thiếu metrics/upstream cells phải được xem là incomplete input, không được điền giả hoặc suy ra winner.
