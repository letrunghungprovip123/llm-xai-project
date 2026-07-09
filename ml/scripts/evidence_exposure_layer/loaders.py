import json
from pathlib import Path


def load_ir_records(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input IR file not found: {path}")

    records = []
    
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"error JSON at line {line_no}: {e}")
            if not isinstance(item, dict):
                raise ValueError(f"IR line {line_no} is not an object")
            records.append(item)

    return records