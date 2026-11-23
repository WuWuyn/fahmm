import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.documents import chunks, read_document
from core.export import export_all
from core.llm import Extracted
from core.pipeline import run_pipeline
from openpyxl import load_workbook


class TestCore(unittest.TestCase):
    def test_chunk_coverage_overlap(self):
        text = ("alpha beta gamma delta " * 500).strip()
        parts = list(chunks(text, 400, 40))
        self.assertGreater(len(parts), 2)
        self.assertEqual(parts[0][:20], text[:20])
        self.assertEqual(parts[-1][-20:], text[-20:])
        self.assertTrue(all(parts[i][-20:] in parts[i + 1] for i in range(len(parts) - 1)))

    def test_schema_validation(self):
        with self.assertRaises(ValueError):
            Extracted.model_validate_json('{"facts":"not a list"}')

    def test_grounding_export_and_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "report.txt"
            path.write_text("Người phụ trách: Lan.", encoding="utf-8")

            def fake(*a, **k):
                return Extracted.model_validate(
                    {
                        "facts": [
                            {"field": "phu_trach", "value": "Lan", "quote": "Người phụ trách: Lan"},
                            {"field": "deadline", "value": "2027", "quote": "không có"},
                        ]
                    }
                ), {"eval_count": 3, "eval_duration": 1000000000}

            with patch("core.pipeline.extract", fake):
                result = run_pipeline([path, Path(d) / "missing.pdf"], "model")
            self.assertEqual(result["fields"]["phu_trach"], ["Lan"])
            self.assertIsNone(result["fields"]["deadline"])
            self.assertTrue(any(w["issue"] == "Trích dẫn không khớp" for w in result["warnings"]))
            self.assertTrue(any(w["issue"] == "Lỗi xử lý tài liệu" for w in result["warnings"]))
            export_all(result, d)
            book = load_workbook(Path(d) / "Bang_Tong_Hop.xlsx")
            self.assertEqual(book.sheetnames, ["Tổng hợp", "Chi tiết nguồn", "Cần kiểm tra"])
            self.assertEqual(book["Chi tiết nguồn"]["E2"].value, "Lan")

    def test_memory_warning(self):
        from types import SimpleNamespace

        from core.llm import extract

        with (
            patch("core.llm.running", return_value=[]),
            patch("core.llm.psutil.virtual_memory", return_value=SimpleNamespace(available=100)),
            self.assertRaises(MemoryError),
        ):
            extract("model", "text")

    def test_docx_xlsx_markdown(self):
        from docx import Document
        from openpyxl import Workbook

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            doc = Document()
            doc.add_paragraph("Báo cáo tiếng Việt")
            doc.save(d / "a.docx")
            wb = Workbook()
            wb.active.append(["Chủ đề", "Dự án"])
            wb.save(d / "b.xlsx")
            (d / "c.md").write_text("# Nội dung", encoding="utf-8")
            self.assertIn("Báo cáo tiếng Việt", next(read_document(d / "a.docx")).text)
            sheet = next(read_document(d / "b.xlsx"))
            self.assertIn("Dự án", sheet.text)
            self.assertIn("1-1", sheet.location)
            self.assertIn("Nội dung", next(read_document(d / "c.md")).text)


if __name__ == "__main__":
    unittest.main()
