# Code lịch sử

`legacy/` giữ source của các pipeline không thuộc active research workflow. Không xóa các module này vì chúng giải thích provenance của artifact cũ.

- `python/llm_explanation_v1`: Batch I Python/template cũ, trước TypeScript narrative hiện hành.
- `typescript/batch_i_v1`: Batch I TypeScript cũ dùng schema `llm_explanations`.
- `typescript/batch_j`: J1/J2/J3 claim extraction và faithfulness validation cũ.
- `typescript/batch_k`: finalization Batch K cũ.
- `typescript/integrated_flow`: orchestration I-J lịch sử.
- `typescript/web_mock`: mock explanation pipeline từng được web route gọi nhưng thiếu validator implementation.

Active research không được import từ thư mục này.
