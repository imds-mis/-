from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import qrcode
from docx import Document
from docx.shared import Inches, Pt


TOKEN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def replace_placeholders(text: str, values: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        value = values[key]
        return "" if value is None else str(value)
    return TOKEN.sub(repl, text)


def _replace_paragraph(paragraph, values: dict[str, Any]) -> None:
    full = "".join(run.text for run in paragraph.runs)
    replaced = replace_placeholders(full, values)
    if replaced == full:
        return
    if paragraph.runs:
        paragraph.runs[0].text = replaced
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.text = replaced


def _apply_clinic_header(doc: Document, clinic_header: dict[str, Any] | None, logo_path: Path | None) -> None:
    if not clinic_header:
        return
    for section in doc.sections:
        header = section.header
        if logo_path and logo_path.exists():
            p = header.add_paragraph()
            p.alignment = 1
            try:
                p.add_run().add_picture(str(logo_path), width=Inches(0.9))
            except Exception:
                pass
        name = str(clinic_header.get("clinic_name") or "").strip()
        if name:
            p = header.add_paragraph()
            p.alignment = 1
            run = p.add_run(name)
            run.bold = True
            run.font.size = Pt(12)
        details = [
            str(clinic_header.get("extra_line") or "").strip(),
            str(clinic_header.get("bin") or "").strip(),
            str(clinic_header.get("address") or "").strip(),
            str(clinic_header.get("phone") or "").strip(),
            str(clinic_header.get("license_text") or "").strip(),
        ]
        details = [item for item in details if item]
        if details:
            p = header.add_paragraph(" · ".join(details))
            p.alignment = 1
            for run in p.runs:
                run.font.size = Pt(8)
        footer_text = str(clinic_header.get("footer_text") or "").strip()
        if footer_text:
            p = section.footer.add_paragraph(footer_text)
            p.alignment = 1
            for run in p.runs:
                run.font.size = Pt(8)


def render_docx(
    source: Path,
    destination: Path,
    values: dict[str, Any],
    qr_url: str | None = None,
    clinic_header: dict[str, Any] | None = None,
    logo_path: Path | None = None,
) -> None:
    doc = Document(source)
    _apply_clinic_header(doc, clinic_header, logo_path)
    for paragraph in doc.paragraphs:
        _replace_paragraph(paragraph, values)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_paragraph(paragraph, values)
    for section in doc.sections:
        for paragraph in section.header.paragraphs:
            _replace_paragraph(paragraph, values)
        for paragraph in section.footer.paragraphs:
            _replace_paragraph(paragraph, values)
        if qr_url:
            with tempfile.TemporaryDirectory() as td:
                qr_path = Path(td) / "qr.png"
                qrcode.make(qr_url).save(qr_path)
                p = section.footer.add_paragraph()
                p.add_run("Проверка документа: ")
                p.add_run().add_picture(str(qr_path), width=Inches(0.75))
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise RuntimeError("LibreOffice is required for PDF rendering")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", td, str(docx_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        generated = Path(td) / f"{docx_path.stem}.pdf"
        if not generated.exists():
            raise RuntimeError("LibreOffice did not create PDF")
        shutil.copy2(generated, pdf_path)
