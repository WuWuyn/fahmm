"""Create a simple, editable Word document from saved minutes Markdown."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("w", W)


def _tag(name: str) -> str:
    return f"{{{W}}}{name}"


def _xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _safe_text(value: str) -> str:
    return "".join(char for char in value if char in "\t\n\r" or ord(char) >= 32)


def _paragraph(body: ET.Element, text: str, style: str, *, indent: bool = False) -> None:
    paragraph = ET.SubElement(body, _tag("p"))
    properties = ET.SubElement(paragraph, _tag("pPr"))
    ET.SubElement(properties, _tag("pStyle"), {_tag("val"): style})
    if indent:
        ET.SubElement(properties, _tag("ind"), {_tag("left"): "360"})
    run = ET.SubElement(paragraph, _tag("r"))
    node = ET.SubElement(run, _tag("t"), {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    node.text = _safe_text(text)


def _document(markdown: str) -> bytes:
    document = ET.Element(_tag("document"))
    body = ET.SubElement(document, _tag("body"))
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            _paragraph(body, heading.group(2), "Title" if level == 1 else f"Heading{level - 1}")
        elif line.startswith("> "):
            _paragraph(body, line[2:], "Quote")
        elif re.match(r"^[-*+]\s+", line):
            _paragraph(body, "• " + line[2:], "ListParagraph", indent=True)
        elif re.match(r"^\d+\.\s+", line):
            _paragraph(body, line, "ListParagraph", indent=True)
        else:
            _paragraph(body, line, "Normal")
    section = ET.SubElement(body, _tag("sectPr"))
    ET.SubElement(section, _tag("pgSz"), {_tag("w"): "11906", _tag("h"): "16838"})
    ET.SubElement(section, _tag("pgMar"), {
        _tag("top"): "1134", _tag("right"): "1134", _tag("bottom"): "1134", _tag("left"): "1134",
        _tag("header"): "708", _tag("footer"): "708", _tag("gutter"): "0",
    })
    return _xml(document)


def _styles() -> bytes:
    styles = ET.Element(_tag("styles"))
    for style_id, size, bold, before, after in (
        ("Normal", 22, False, 0, 120),
        ("Title", 36, True, 0, 240),
        ("Heading1", 28, True, 300, 140),
        ("Heading2", 24, True, 220, 100),
        ("Quote", 20, False, 40, 100),
        ("ListParagraph", 22, False, 0, 80),
    ):
        style = ET.SubElement(styles, _tag("style"), {_tag("type"): "paragraph", _tag("styleId"): style_id})
        ET.SubElement(style, _tag("name"), {_tag("val"): style_id})
        properties = ET.SubElement(style, _tag("pPr"))
        ET.SubElement(properties, _tag("spacing"), {_tag("before"): str(before), _tag("after"): str(after)})
        run = ET.SubElement(style, _tag("rPr"))
        ET.SubElement(run, _tag("rFonts"), {_tag("ascii"): "Aptos", _tag("hAnsi"): "Aptos"})
        ET.SubElement(run, _tag("sz"), {_tag("val"): str(size)})
        if bold:
            ET.SubElement(run, _tag("b"))
    return _xml(styles)


def render_docx(markdown: str) -> bytes:
    """Return a valid OOXML document without requiring Word or a network service."""
    types = ET.Element(f"{{{CONTENT}}}Types")
    ET.SubElement(types, f"{{{CONTENT}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(types, f"{{{CONTENT}}}Default", {"Extension": "xml", "ContentType": "application/xml"})
    ET.SubElement(types, f"{{{CONTENT}}}Override", {"PartName": "/word/document.xml", "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"})
    ET.SubElement(types, f"{{{CONTENT}}}Override", {"PartName": "/word/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"})
    root_rels = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(root_rels, f"{{{REL}}}Relationship", {"Id": "rId1", "Type": f"{DOC_REL}/officeDocument", "Target": "word/document.xml"})
    doc_rels = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(doc_rels, f"{{{REL}}}Relationship", {"Id": "rId1", "Type": f"{DOC_REL}/styles", "Target": "styles.xml"})
    result = io.BytesIO()
    with ZipFile(result, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xml(types))
        archive.writestr("_rels/.rels", _xml(root_rels))
        archive.writestr("word/document.xml", _document(markdown))
        archive.writestr("word/styles.xml", _styles())
        archive.writestr("word/_rels/document.xml.rels", _xml(doc_rels))
    return result.getvalue()
