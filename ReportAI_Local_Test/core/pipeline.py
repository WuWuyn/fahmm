import time
from collections import defaultdict
from pathlib import Path

from config.settings import FIELDS

from core.documents import chunks, read_document
from core.llm import extract


def run_pipeline(paths, model, progress=lambda *args: None, cancel=None, use_gpu=False):
    started = time.monotonic()
    facts = []
    warnings = []
    seen = set()
    durations = []
    tokens = 0
    for index, path in enumerate(paths):
        if cancel and cancel.is_set():
            raise InterruptedError("Đã hủy xử lý")
        any_text = False
        try:
            for passage in read_document(path):
                for chunk in chunks(passage.text):
                    if cancel and cancel.is_set():
                        raise InterruptedError("Đã hủy xử lý")
                    any_text = True
                    progress(index, len(paths), f"{Path(path).name} • {passage.location}")
                    parsed, response = extract(model, chunk, use_gpu=use_gpu)
                    durations.append(response.get("eval_duration", 0))
                    tokens += response.get("eval_count", 0)
                    for f in parsed.facts:
                        if f.field not in FIELDS or not f.value.strip():
                            warnings.append(
                                {
                                    "issue": "Trường không hợp lệ",
                                    "documents": passage.file,
                                    "data": str(f.field),
                                    "reason": "Model trả trường không được hỗ trợ hoặc giá trị rỗng",
                                }
                            )
                            continue
                        if not f.quote.strip() or f.quote not in chunk:
                            warnings.append(
                                {
                                    "issue": "Trích dẫn không khớp",
                                    "documents": passage.file,
                                    "data": f.value,
                                    "reason": "Không tìm thấy nguyên văn trích dẫn trong đoạn nguồn; đã loại dữ kiện",
                                }
                            )
                            continue
                        if f.value.casefold() not in f.quote.casefold():
                            warnings.append(
                                {
                                    "issue": "Giá trị không khớp trích dẫn",
                                    "documents": passage.file,
                                    "data": f.value,
                                    "reason": "Giá trị không xuất hiện nguyên văn trong trích dẫn; đã loại dữ kiện",
                                }
                            )
                            continue
                        key = (passage.file, f.field, f.value.casefold().strip(), f.quote)
                        if key not in seen:
                            seen.add(key)
                            facts.append(
                                {
                                    "file": passage.file,
                                    "location": passage.location,
                                    "field": f.field,
                                    "value": f.value,
                                    "quote": f.quote,
                                }
                            )
            if not any_text:
                warnings.append(
                    {
                        "issue": "Không có văn bản",
                        "documents": Path(path).name,
                        "data": "",
                        "reason": "Không trích xuất được văn bản; có thể cần OCR",
                    }
                )
        except InterruptedError:
            raise
        except Exception as exc:
            warnings.append(
                {
                    "issue": "Lỗi xử lý tài liệu",
                    "documents": Path(path).name,
                    "data": "",
                    "reason": str(exc),
                }
            )
    grouped = defaultdict(list)
    for f in facts:
        if f["value"] not in grouped[f["field"]]:
            grouped[f["field"]].append(f["value"])
    for field in ("ngay_bao_cao", "deadline", "phu_trach"):
        vals = grouped[field]
        if len(vals) > 1:
            warnings.append(
                {
                    "issue": "Cần đối chiếu giá trị khác nhau",
                    "documents": ", ".join(
                        sorted({f["file"] for f in facts if f["field"] == field})
                    ),
                    "data": "; ".join(vals),
                    "reason": f"{FIELDS[field]} có nhiều giá trị; có thể thuộc các công việc khác nhau, không khẳng định mâu thuẫn.",
                }
            )
    for field, label in FIELDS.items():
        if not grouped[field]:
            warnings.append(
                {
                    "issue": "Thiếu thông tin",
                    "documents": ", ".join(Path(p).name for p in paths),
                    "data": label,
                    "reason": "Không có dữ kiện được xác thực bằng trích dẫn",
                }
            )
    return {
        "model": model,
        "fields": {k: grouped[k] or None for k in FIELDS},
        "facts": facts,
        "warnings": warnings,
        "metrics": {
            "seconds": round(time.monotonic() - started, 2),
            "tokens": tokens,
            "tokens_per_second": round(tokens / (sum(durations) / 1e9), 2)
            if sum(durations)
            else None,
        },
    }
