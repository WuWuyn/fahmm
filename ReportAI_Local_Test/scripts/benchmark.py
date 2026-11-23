import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MODELS, ROOT
from core.llm import running, unload
from core.pipeline import run_pipeline
from openpyxl import Workbook

data = ROOT / "tests" / "data"
paths = [
    data / name
    for name in (
        "vietnamese.txt",
        "english.txt",
        "mixed.txt",
        "numbers.txt",
        "conflict_a.txt",
        "conflict_b.txt",
        "long.txt",
        "broken.pdf",
    )
]
if not paths[-2].exists():
    paths[-2].write_text(
        ("Báo cáo dài: nhóm đã kiểm tra hệ thống. Không có vấn đề mới.\n" * 85)
        + "Người phụ trách: Trang. Deadline: 31/12/2026.",
        encoding="utf-8",
    )
expected = {
    "vietnamese.txt": ["An", "15/12/2026"],
    "english.txt": ["David", "18 December 2026"],
    "mixed.txt": ["Lan", "30/11/2026"],
    "numbers.txt": ["Minh", "20/12/2026", "250"],
    "conflict_a.txt": ["25/12/2026"],
    "conflict_b.txt": ["30/12/2026"],
    "long.txt": ["Trang", "31/12/2026"],
}
out = ROOT / "outputs"
out.mkdir(exist_ok=True)
rows = []
for model in MODELS:
    print("Đang chạy", model, flush=True)
    try:
        r = run_pipeline(paths, model, lambda i, n, s: print(s, flush=True))
        hits = 0
        total = sum(map(len, expected.values()))
        for f, vals in expected.items():
            text = " ".join(
                x["value"] + " " + x["quote"] for x in r["facts"] if x["file"] == f
            ).casefold()
            hits += sum(1 for v in vals if v.casefold() in text)
        errors = [
            w
            for w in r["warnings"]
            if w["issue"] == "Lỗi xử lý tài liệu" and w["documents"] != "broken.pdf"
        ]
        row = {
            "model": model,
            **r["metrics"],
            "matched_expected": hits if not errors else None,
            "expected": total,
            "recall": round(hits / total, 3) if not errors else None,
            "valid_facts": len(r["facts"]),
            "processing_errors": len(errors),
            "warnings": len(r["warnings"]),
            "ram_available_gb": round(__import__("psutil").virtual_memory().available / 1024**3, 2),
            "status": ("Không hoàn tất: " + errors[0]["reason"]) if errors else "Hoàn tất",
        }
        (out / ("benchmark_" + str(MODELS.index(model) + 1) + ".json")).write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        row = {"model": model, "status": "Lỗi: " + str(e)}
    rows.append(row)
    (out / "benchmark.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(row, ensure_ascii=False), flush=True)
    try:
        for active in running():
            unload(active)
    except Exception as e:
        print("Không giải phóng được:", e, flush=True)
wb = Workbook()
ws = wb.active
ws.title = "Benchmark"
keys = [
    "model",
    "seconds",
    "tokens_per_second",
    "matched_expected",
    "expected",
    "recall",
    "valid_facts",
    "processing_errors",
    "warnings",
    "ram_available_gb",
    "status",
]
ws.append(keys)
for row in rows:
    ws.append([row.get(k) for k in keys])
ws.freeze_panes = "A2"
ws.auto_filter.ref = ws.dimensions
wb.save(out / "Benchmark.xlsx")
