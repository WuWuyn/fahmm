import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psutil
from config.settings import MODELS, ROOT
from core.llm import extract, running, unload

text = "Team đã completed UAT, tuy nhiên production deployment đang pending vì security review chưa approved. Người phụ trách: Lan. Deadline: 30/11/2026."
rows = []
for model in MODELS:
    print("Testing", model, flush=True)
    start = time.monotonic()
    try:
        parsed, response = extract(model, text)
        facts = parsed.model_dump()["facts"]
        seconds = time.monotonic() - start
        duration = response.get("eval_duration", 0)
        tokens = response.get("eval_count", 0)
        grounded = [
            f
            for f in facts
            if f["quote"] in text and f["value"].casefold() in f["quote"].casefold()
        ]
        row = {
            "model": model,
            "status": "OK",
            "seconds": round(seconds, 2),
            "tokens": tokens,
            "tokens_per_second": round(tokens / (duration / 1e9), 2) if duration else None,
            "json_valid": True,
            "facts": facts,
            "grounded_facts": grounded,
            "available_ram_gb": round(psutil.virtual_memory().available / 1024**3, 2),
        }
    except Exception as e:
        row = {
            "model": model,
            "status": "ERROR",
            "seconds": round(time.monotonic() - start, 2),
            "error": str(e),
            "available_ram_gb": round(psutil.virtual_memory().available / 1024**3, 2),
        }
    rows.append(row)
    (ROOT / "outputs" / "smoke_models.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(row, ensure_ascii=False), flush=True)
    try:
        for active in running():
            unload(active)
    except Exception as e:
        print("Unload failed:", e, flush=True)
