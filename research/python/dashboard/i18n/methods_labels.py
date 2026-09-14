"""Locale-aware labels for Page 7 registries and data dictionary.

Certified datasets retain stable English identifiers and immutable hashes.  This
module provides a presentation-only Vietnamese composer for field identifiers
that are too numerous to maintain as one catalog entry per field.  The raw
technical name remains visible in its own audit column.
"""

from __future__ import annotations

import re

from ..display_labels import display_label
from .locale import normalize_locale
from .translator import t

_EXACT_VI: dict[str, str] = {
    "executive_overview": "Tổng quan điều hành",
    "performance_reliability": "Hiệu quả và độ tin cậy",
    "statistical_evidence": "Bằng chứng thống kê",
    "mechanisms_diagnostics": "Bằng chứng, cơ chế và chẩn đoán",
    "case_explorer": "Khám phá hồ sơ",
    "decision_studio": "Không gian quyết định",
    "validator_sensitivity": "Độ nhạy bộ kiểm định",
    "template_baseline_comparison": "So sánh đường cơ sở Template",
    "observed_pair_count": "Số cặp quan sát được",
    "excluded_pair_count": "Số cặp bị loại",
    "selected_feature_mention_rate": "Tỷ lệ đề cập đặc trưng được chọn",
    "concept_mention_rate": "Tỷ lệ đề cập khái niệm",
    "policy_compliance_rate": "Tỷ lệ tuân thủ chính sách",
    "claim_status_composition": "Cơ cấu trạng thái mệnh đề",
    "safe_phrase_signal": "Tín hiệu cụm từ an toàn",
    "utility_score": "Điểm tiện ích",
    "mean_end_to_end_yield": "Độ trung thành đầu-cuối trung bình",
    "mean_latency_seconds_planned": "Độ trễ trung bình theo kế hoạch",
    "mean_total_token_count_planned": "Tổng số token trung bình theo kế hoạch",
    "mean_supported_claims_per_1000_tokens": "Mệnh đề được hỗ trợ trung bình trên 1.000 token",
    "output_word_count": "Số từ đầu ra",
    "end_to_end_faithfulness_yield": "Độ trung thành đầu-cuối",
    "p10_end_to_end_yield": "Phân vị P10 của độ trung thành đầu-cuối",
    "usability_rate": "Tỷ lệ sử dụng được",
    "conservative_faithfulness": "Độ trung thành bảo thủ",
    "verifiability": "Khả năng kiểm chứng",
    "resolved_faithfulness": "Độ trung thành đã phân giải",
    "supported_claim_count": "Số mệnh đề được hỗ trợ",
    "candidate_v4_delta": "Chênh lệch Candidate–V4",
    "mean_end_to_end_operational_faithfulness": "Độ trung thành vận hành đầu-cuối trung bình",
    "micro_conservative_faithfulness": "Độ trung thành bảo thủ vi mô",
    "micro_verifiability": "Khả năng kiểm chứng vi mô",
    "micro_resolved_faithfulness": "Độ trung thành đã phân giải vi mô",
    "planned_llm_generations": "Số lần sinh LLM theo kế hoạch",
    "usable_llm_generations": "Số lần sinh LLM sử dụng được",
    "unusable_llm_generations": "Số lần sinh LLM không sử dụng được",
    "final_atomic_claims": "Mệnh đề nguyên tử cuối cùng",
    "applicable_claims": "Mệnh đề áp dụng được",
    "resolved_claims": "Mệnh đề đã phân giải",
    "primary_planned_pair_count": "Số cặp chính theo kế hoạch",
    "primary_adjusted_significant_pair_count": "Số cặp chính có ý nghĩa sau hiệu chỉnh",
    "canonical_cases": "Hồ sơ chuẩn hóa",
    "complete_llm_cases": "Hồ sơ đủ 18 điều kiện LLM",
    "incomplete_llm_cases": "Hồ sơ có thiếu có cấu trúc",
    "selected_feature_mention_rate": "Tỷ lệ đề cập đặc trưng được chọn",
    "concept_mention_rate": "Tỷ lệ đề cập khái niệm",
    "coverage": "Độ bao phủ",
    "policy_compliance": "Tuân thủ chính sách",
    "claim_status_composition": "Cơ cấu trạng thái mệnh đề",
    "safe_phrase_signal": "Tín hiệu cụm từ an toàn",
    "utility_score": "Điểm tiện ích",
    "mean_end_to_end_yield": "Độ trung thành đầu-cuối trung bình",
    "mean_latency_seconds_planned": "Độ trễ trung bình theo kế hoạch",
    "mean_total_token_count_planned": "Tổng số token trung bình theo kế hoạch",
    "mean_supported_claims_per_1000_tokens": "Mệnh đề được hỗ trợ trung bình trên 1.000 token",
    "candidate_v4_metric_delta": "Chênh lệch chỉ số Candidate–V4",
    "holm_adjusted_p_value": "Giá trị p hiệu chỉnh Holm",
    "rank_biserial_correlation": "Tương quan lưỡng phân hạng",
    "supported_claims_per_100_words": "Mệnh đề được hỗ trợ trên 100 từ",
    "output_word_count": "Số từ đầu ra",
    "CERTIFIED_HEADLINE": "Chỉ số chính đã chứng nhận",
    "CERTIFIED_SUPPORTING": "Chỉ số hỗ trợ đã chứng nhận",
    "denominator": "Mẫu số",
    "primary_metric": "Chỉ số chính",
    "claim_status": "Trạng thái mệnh đề",
    "planned_contrasts": "Đối sánh theo kế hoạch",
}

_TOKEN_VI: dict[str, str] = {
    "abs": "tuyệt đối", "adaptive": "thích ứng", "add": "bổ sung", "additional": "bổ sung",
    "adjusted": "đã hiệu chỉnh", "adjustment": "hiệu chỉnh", "all": "tất cả", "allowed": "được phép",
    "alpha": "alpha", "alternative": "thay thế", "analysis": "phân tích", "analytical": "phân tích",
    "applicable": "áp dụng được", "artifact": "hiện vật", "as": "dưới dạng", "available": "khả dụng",
    "avoid": "tránh", "backend": "backend", "band": "dải", "baseline": "đường cơ sở", "best": "tốt nhất",
    "biserial": "lưỡng phân", "branch": "nhánh", "by": "bởi", "candidate": "Candidate", "case": "hồ sơ",
    "category": "nhóm", "cause": "nguyên nhân", "char": "ký tự", "claim": "mệnh đề", "claims": "mệnh đề",
    "class": "lớp", "cleanup": "làm sạch", "code": "mã", "codes": "mã", "commit": "commit",
    "comparator": "đối chứng", "comparison": "so sánh", "complete": "đầy đủ", "compliant": "tuân thủ",
    "concept": "khái niệm", "conclusion": "kết luận", "condition": "điều kiện", "conditional": "có điều kiện",
    "conservative": "bảo thủ", "constraint": "ràng buộc", "contained": "được chứa", "context": "ngữ cảnh",
    "contract": "hợp đồng", "contradicted": "bị mâu thuẫn", "contradiction": "mâu thuẫn",
    "contrast": "đối sánh", "contribution": "đóng góp", "correct": "đúng", "corrected": "đã hiệu chỉnh",
    "correlation": "tương quan", "count": "số lượng", "coverage": "độ bao phủ", "criterion": "tiêu chí",
    "dashboard": "dashboard", "data": "dữ liệu", "decision": "quyết định", "declared": "được khai báo",
    "denominator": "mẫu số", "description": "mô tả", "deviation": "độ lệch", "df": "bậc tự do",
    "difference": "chênh lệch", "direction": "hướng", "disabled": "đã tắt", "display": "hiển thị",
    "distinct": "phân biệt", "distributed": "phân phối", "dominant": "chi phối", "dominated": "bị chi phối",
    "dominates": "chi phối", "empty": "rỗng", "enabled": "được bật", "end": "đầu-cuối",
    "endpoint": "tiêu chí cuối", "entropy": "entropy", "epsilon": "epsilon", "error": "lỗi",
    "eta": "eta", "evaluated": "được đánh giá", "evidence": "bằng chứng", "exact": "chính xác",
    "excluded": "bị loại", "exposed": "được phơi bày", "exposure": "mức phơi bày", "extraction": "trích xuất",
    "factor": "yếu tố", "factors": "yếu tố", "failed": "thất bại", "failure": "lỗi", "faithfulness": "độ trung thành",
    "feature": "đặc trưng", "field": "trường", "finish": "hoàn tất", "fixed": "cố định", "floor": "ngưỡng đo",
    "for": "cho", "forbidden": "bị cấm", "fourth": "thứ tư", "from": "từ", "gate": "cổng",
    "generation": "lần sinh", "generator": "bộ sinh", "geisser": "Geisser", "git": "Git", "grain": "độ hạt",
    "greenhouse": "Greenhouse", "ground": "chuẩn", "group": "nhóm", "grouped": "được nhóm", "guidance": "hướng dẫn",
    "has": "có", "high": "cao", "human": "con người", "id": "ID", "identical": "giống hệt",
    "ids": "các ID", "include": "bao gồm", "independent": "độc lập", "index": "chỉ mục", "inference": "suy luận",
    "informational": "thông tin", "input": "đầu vào", "intended": "dự kiến", "interaction": "tương tác",
    "internal": "nội bộ", "interpretation": "diễn giải", "invalid": "không hợp lệ", "is": "là", "item": "mục",
    "json": "JSON", "kpi": "KPI", "label": "nhãn", "latency": "độ trễ", "level": "mức", "limited": "bị giới hạn",
    "llm": "LLM", "loss": "tổn thất", "main": "chính", "mass": "khối lượng", "match": "khớp",
    "matched": "đã ghép", "maximum": "tối đa", "mean": "trung bình", "measured": "được đo", "measurement": "đo lường",
    "median": "trung vị", "mention": "đề cập", "message": "thông báo", "method": "phương pháp", "metric": "chỉ số",
    "metrics": "chỉ số", "minimum": "tối thiểu", "minus": "trừ", "missing": "thiếu", "missingness": "tình trạng thiếu",
    "mixed": "hỗn hợp", "model": "mô hình", "ms": "ms", "must": "bắt buộc", "naturalness": "độ tự nhiên",
    "no": "không", "none": "không có", "normalization": "chuẩn hóa", "normalized": "đã chuẩn hóa", "not": "không",
    "note": "ghi chú", "numerator": "tử số", "observation": "quan sát", "observed": "quan sát được", "of": "của",
    "optimal": "tối ưu", "option": "phương án", "order": "thứ tự", "ordinal": "thứ bậc", "orientation": "hướng",
    "oriented": "định hướng", "out": "đầu ra", "outcome": "kết quả", "output": "đầu ra", "overall": "tổng thể",
    "overlap": "chồng lấp", "package": "gói", "page": "trang", "pair": "cặp", "paired": "ghép cặp",
    "pairing": "ghép cặp", "parent": "nguồn cha", "parse": "phân tích cú pháp", "partial": "một phần", "pass": "đạt",
    "per": "trên", "phrase": "cụm từ", "pipeline": "pipeline", "planned": "theo kế hoạch", "policy": "chính sách",
    "population": "quần thể", "prediction": "dự đoán", "predicted": "được dự đoán", "primary": "chính",
    "probability": "xác suất", "q1": "Q1", "q3": "Q3", "quality": "chất lượng", "question": "câu hỏi",
    "rank": "hạng", "rate": "tỷ lệ", "ratio": "tỷ số", "raw": "thô", "reason": "lý do",
    "recommendation": "khuyến nghị", "recommended": "được khuyến nghị", "release": "bản phát hành", "repeat": "lặp lại",
    "report": "báo cáo", "reporting": "báo cáo", "required": "bắt buộc", "requires": "yêu cầu", "resolved": "đã phân giải",
    "response": "phản hồi", "restrictions": "giới hạn", "retry": "thử lại", "role": "vai trò", "row": "hàng",
    "rq": "RQ", "runtime": "runtime", "safe": "an toàn", "schema": "schema", "score": "điểm", "seconds": "giây",
    "selected": "được chọn", "selection": "lựa chọn", "semantic": "ngữ nghĩa", "sensitivity": "độ nhạy",
    "sentence": "câu", "sha256": "SHA-256", "shap": "SHAP", "share": "tỷ trọng", "signal": "tín hiệu",
    "significance": "ý nghĩa thống kê", "significant": "có ý nghĩa", "single": "đơn", "size": "kích thước",
    "skeleton": "khung", "slot": "ô", "source": "nguồn", "sources": "nguồn", "squares": "bình phương",
    "stable": "ổn định", "standard": "chuẩn", "statistic": "thống kê", "statistical": "thống kê", "status": "trạng thái",
    "strong": "mạnh", "structural": "cấu trúc", "structured": "có cấu trúc", "subject": "đối tượng",
    "success": "thành công", "sum": "tổng", "summary": "tóm tắt", "supported": "được hỗ trợ",
    "supporting": "hỗ trợ", "table": "bảng", "technical": "kỹ thuật", "template": "Template", "term": "thuật ngữ",
    "test": "kiểm định", "text": "văn bản", "threshold": "ngưỡng", "tier": "tầng", "title": "tiêu đề",
    "token": "token", "tokens": "token", "top": "hàng đầu", "top1": "top-1", "top3": "top-3", "top5": "top-5",
    "total": "tổng", "to": "đến", "tree": "cây", "true": "thực", "truncated": "bị cắt", "truncation": "cắt ngắn",
    "type": "kiểu", "uncertainty": "độ bất định", "uncorrected": "chưa hiệu chỉnh", "unit": "đơn vị", "units": "đơn vị",
    "unique": "duy nhất", "unsupported": "không được hỗ trợ", "unusable": "không sử dụng được", "usability": "khả năng sử dụng",
    "usable": "sử dụng được", "used": "được dùng", "utility": "tiện ích", "v4": "V4", "valid": "hợp lệ",
    "validation": "xác thực", "validator": "bộ kiểm định", "value": "giá trị", "verifiability": "khả năng kiểm chứng",
    "verifiable": "có thể kiểm chứng", "verified": "đã xác minh", "version": "phiên bản", "violation": "vi phạm",
    "visibility": "khả năng hiển thị", "visualization": "trực quan hóa", "weak": "yếu", "weighted": "có trọng số",
    "weight": "trọng số", "wilcoxon": "Wilcoxon", "word": "từ", "wording": "cách diễn đạt", "words": "từ",
    "yield": "độ trung thành",
}

_ACRONYM_TOKENS = {"api", "ci", "csv", "e2e", "id", "json", "llm", "p10", "rq", "sha256", "shap", "ui", "url", "v4"}


def methods_identifier_label(locale: object, identifier: object) -> str:
    """Return one audit display label while preserving the raw technical name separately."""

    resolved = normalize_locale(locale)
    text = str(identifier).strip()
    if not text:
        return ""
    if resolved == "en":
        return display_label(text)
    if text in _EXACT_VI:
        return _EXACT_VI[text]

    normalized = text.replace("–", "_").replace("-", "_")
    tokens = [token for token in re.split(r"_+", normalized.lower()) if token]
    rendered: list[str] = []
    for token in tokens:
        if token.isdigit():
            rendered.append(token)
            continue
        match = re.fullmatch(r"([rsq])([0-9]+)", token)
        if match:
            rendered.append(f"{match.group(1).upper()}{match.group(2)}")
            continue
        translated = _TOKEN_VI.get(token)
        if translated is not None:
            rendered.append(translated)
            continue
        # Unknown tokens are never leaked as English presentation copy.  The
        # exact raw identifier remains available in the adjacent technical-name
        # column for auditability.
        rendered.append(t(resolved, "methods.dictionary.unknown_token"))
    label = " ".join(rendered).strip() or t(resolved, "methods.dictionary.generic_field")
    return label[:1].upper() + label[1:]


def methods_unknown_identifier_tokens(identifier: object) -> tuple[str, ...]:
    text = str(identifier).strip().replace("–", "_").replace("-", "_").lower()
    unknown = []
    for token in [item for item in re.split(r"_+", text) if item]:
        if token.isdigit() or re.fullmatch(r"[rsq][0-9]+", token):
            continue
        if token not in _TOKEN_VI:
            unknown.append(token)
    return tuple(unknown)


__all__ = ["methods_identifier_label", "methods_unknown_identifier_tokens"]
