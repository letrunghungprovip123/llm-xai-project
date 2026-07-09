from pathlib import Path

INPUT_IR_PATH = Path("data/reports/explanation_ir_v2/evaluation/explanation_ir_v2.jsonl")
OUTPUT_DIR = Path("data/reports/evidence_exposure/evaluation")
MANIFEST_DIR = Path("data/manifests")

LEVEL_FILE_NAMES = {
    "S0": "prediction_only.jsonl",
    "S1": "raw_shap_fixed_topk.jsonl",
    "S2": "semantic_shap_fixed_topk.jsonl",
    "S3": "adaptive_coverage_constraints.jsonl",
    "S4": "adaptive_entropy_concept_quality.jsonl",
    "S5": "backend_overguided.jsonl",
}