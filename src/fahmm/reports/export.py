import json
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from fahmm.reports.settings import FIELDS


def fmt(value):
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return str(value) if value is not None else "Chưa có thông tin"


def report_text(result, form=""):
    lines = ["# Báo cáo tổng hợp", "", f"Model: {result['model']}", ""]
    if form.strip():
        lines += ["## Form yêu cầu", form.strip(), ""]
    for key, label in FIELDS.items():
        lines += [f"## {label}", fmt(result["fields"].get(key)), ""]
    lines += ["## Nguồn dữ liệu"]
    lines += [
        f"- {x['file']} | {x['location']} | {FIELDS.get(x['field'], x['field'])}: {x['quote']}"
        for x in result["facts"]
    ] or ["Chưa có thông tin"]
    lines += ["", "## Mức độ tin cậy / cần kiểm tra"]
    lines += [f"- {x['issue']}: {x['data']} — {x['reason']}" for x in result["warnings"]] or [
        "Cần đối chiếu thủ công với nguồn."
    ]
    return "\n".join(lines)


def excel_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(("=", "+", "-", "@")) else s


def make_excel(result, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Tổng hợp"
    ws.append(
        [
            "STT",
            "Báo cáo",
            "Chủ đề",
            "Nội dung",
            "Kết quả",
            "Trạng thái",
            "Deadline",
            "Người phụ trách",
            "Rủi ro",
        ]
    )
    files = sorted({x["file"] for x in result["facts"]})
    for i, file in enumerate(files, 1):

        def get(key, source_file=file):
            return fmt(
                list(
                    dict.fromkeys(
                        x["value"]
                        for x in result["facts"]
                        if x["file"] == source_file and x["field"] == key
                    )
                )
                or None
            )

        ws.append(
            [
                i,
                file,
                get("chu_de"),
                get("noi_dung"),
                get("ket_qua"),
                get("chua_hoan_thanh"),
                get("deadline"),
                get("phu_trach"),
                get("rui_ro"),
            ]
        )
    source = wb.create_sheet("Chi tiết nguồn")
    source.append(
        ["File nguồn", "Trang/vị trí", "Trích dẫn ngắn", "Trường dữ liệu", "Giá trị trích xuất"]
    )
    for x in result["facts"]:
        source.append(
            [
                excel_safe(x["file"]),
                excel_safe(x["location"]),
                excel_safe(x["quote"]),
                FIELDS.get(x["field"], x["field"]),
                excel_safe(x["value"]),
            ]
        )
    warn = wb.create_sheet("Cần kiểm tra")
    warn.append(["Vấn đề", "Tài liệu liên quan", "Dữ liệu mâu thuẫn/thiếu", "Lý do cảnh báo"])
    for x in result["warnings"]:
        warn.append([excel_safe(x[k]) for k in ("issue", "documents", "data", "reason")])
    for sheet in wb:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24566A")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for col in sheet.columns:
            letter = get_column_letter(col[0].column)
            sheet.column_dimensions[letter].width = min(
                48, max(16, max(len(str(c.value or "")) for c in col[:100]) + 2)
            )
            for cell in col[1:]:
                if isinstance(cell.value, str):
                    cell.value = excel_safe(cell.value) if cell.data_type == "f" else cell.value
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


def export_all(result, directory, form=""):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names = ("Bao_Cao.md", "Ket_Qua.json", "Bao_Cao.docx", "Bang_Tong_Hop.xlsx")
    existing = [name for name in names if (directory / name).exists()]
    if existing:
        raise FileExistsError(
            "Đã tồn tại: " + ", ".join(existing) + ". Hãy chọn thư mục trống để không ghi đè."
        )
    text = report_text(result, form)
    (directory / "Bao_Cao.md").write_text(text, encoding="utf-8")
    (directory / "Ket_Qua.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    doc = Document()
    doc.add_heading("Báo cáo tổng hợp", 0)
    for line in text.splitlines()[1:]:
        if line.startswith("## "):
            doc.add_heading(line[3:], level=1)
        elif line:
            doc.add_paragraph(line)
    doc.save(directory / "Bao_Cao.docx")
    make_excel(result, directory / "Bang_Tong_Hop.xlsx")
