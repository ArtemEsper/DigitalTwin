"""
Document parser.

Converts uploaded .pdf, .docx, and .txt files to plain text
before passing to the candidate extractor.
"""

import io
import logging

logger = logging.getLogger(__name__)


def parse_pdf(data: bytes) -> str:
    """Extract plain text from a PDF byte stream using PyMuPDF."""
    import fitz  # pymupdf

    text_parts = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n\n".join(text_parts).strip()


def parse_docx(data: bytes) -> str:
    """Extract plain text from a .docx byte stream using python-docx.

    Walks the document body in reading order, extracting text from both
    top-level paragraphs and table cells (tables are common in Ukrainian
    Word documents for layout purposes).
    """
    from docx import Document

    doc = Document(io.BytesIO(data))
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    parts = []

    def _para_text(el) -> str:
        return "".join(t.text or "" for t in el.iter(f"{{{W}}}t"))

    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            text = _para_text(child)
            if text.strip():
                parts.append(text)
        elif tag == "tbl":
            for row in child.iter(f"{{{W}}}tr"):
                for cell in row.iter(f"{{{W}}}tc"):
                    cell_texts = [
                        _para_text(p)
                        for p in cell.iter(f"{{{W}}}p")
                        if _para_text(p).strip()
                    ]
                    if cell_texts:
                        parts.append("\n".join(cell_texts))

    return "\n\n".join(parts).strip()


def parse_txt(data: bytes) -> str:
    """Decode a plain text file, trying UTF-8 then latin-1 as fallback."""
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return data.decode("latin-1").strip()


def parse_file(filename: str, data: bytes) -> str:
    """
    Dispatch to the correct parser based on file extension.
    Returns the extracted plain text.
    Raises ValueError for unsupported file types.
    """
    lower = filename.lower()

    if lower.endswith(".pdf"):
        text = parse_pdf(data)
    elif lower.endswith(".docx"):
        text = parse_docx(data)
    elif lower.endswith(".txt"):
        text = parse_txt(data)
    else:
        raise ValueError(
            f"Unsupported file type: {filename!r}. "
            "Supported formats: .pdf, .docx, .txt"
        )

    if not text:
        raise ValueError(f"No text could be extracted from {filename!r}")

    logger.info("Parsed %d characters from %s", len(text), filename)
    return text
