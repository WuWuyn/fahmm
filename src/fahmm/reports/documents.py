from dataclasses import dataclass
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


@dataclass
class Passage:
    file: str
    location: str
    text: str

def read_document(path):
    if isinstance(path, Passage):
        yield path
        return
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.txt', '.md'):
        data = path.read_text(encoding='utf-8-sig')
        yield Passage(path.name, 'Văn bản', data)
    elif suffix == '.pdf':
        for i, page in enumerate(PdfReader(str(path)).pages, 1):
            yield Passage(path.name, str(i), page.extract_text() or '')
    elif suffix == '.docx':
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            parts.extend(' | '.join(c.text for c in row.cells) for row in table.rows)
        yield Passage(path.name, 'Nội dung và bảng (không xác định trang)', '\n'.join(parts))
    elif suffix == '.xlsx':
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in book:
                lines = []; start = None; last = None; length = 0
                for rowno, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    values = [str(v) if v is not None else '' for v in row]
                    if any(values):
                        line = f'Dòng {rowno}: ' + ' | '.join(values)
                        if lines and length + len(line) > 4000:
                            yield Passage(path.name, f'{sheet.title}!{start}-{last}', '\n'.join(lines))
                            lines = []; length = 0; start = None
                        if start is None: start = rowno
                        last = rowno; lines.append(line); length += len(line)
                if lines: yield Passage(path.name, f'{sheet.title}!{start}-{last}', '\n'.join(lines))
        finally:
            book.close()
    else:
        raise ValueError(f'Không hỗ trợ định dạng {suffix}')

def chunks(text, size=4000, overlap=400):
    if not 0 <= overlap < size:
        raise ValueError('overlap không hợp lệ')
    text = text.strip()
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + size)
        if end < len(text):
            split = text.rfind(' ', pos + size // 2, end)
            if split > pos:
                end = split
        yield text[pos:end]
        if end == len(text):
            break
        pos = max(pos + 1, end - overlap)
