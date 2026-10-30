from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}


@dataclass
class ExtractedPage:
    text: str
    page: int | None
    tables: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)


def _clean_table(rows: Iterable[Iterable[object]]) -> str:
    lines = []
    for row in rows:
        values = [str(value or "").strip().replace("\n", " ") for value in row]
        if any(values):
            lines.append(" | ".join(values))
    return "\n".join(lines)


def load_file(path: Path, document_name: str | None = None) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix or '(no extension)'}")

    pages: list[ExtractedPage]
    if suffix == ".pdf":
        import pdfplumber

        pages = []
        with path.open("rb") as stream, pdfplumber.open(stream) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                extracted = page.extract_text() or ""
                table_text = [_clean_table(table) for table in (page.extract_tables() or [])]
                table_text = [table for table in table_text if table]
                if not extracted.strip() and not table_text:
                    logger.warning(
                        "PDF page has no extractable text or tables; skipping page (OCR is disabled)",
                        extra={"document": path.name, "page": index},
                    )
                pages.append(ExtractedPage(extracted, index, table_text))
    elif suffix == ".docx":
        doc = DocxDocument(path)
        paragraphs = []
        headings = []
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if text:
                paragraphs.append(text)
                if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                    headings.append(text)
        tables = [_clean_table([[cell.text for cell in row.cells] for row in table.rows]) for table in doc.tables]
        pages = [ExtractedPage("\n".join(paragraphs), None, [table for table in tables if table], headings)]
    else:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        headings = [element.get_text(" ", strip=True) for element in soup.find_all(["h1", "h2", "h3"])]
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for row in table.find_all("tr"):
                rows.append([cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])])
            content = _clean_table(rows)
            if content:
                tables.append(content)
            table.decompose()
        text = soup.get_text("\n", strip=True)
        pages = [ExtractedPage(text, None, tables, headings)]

    result = []
    for page in pages:
        common = {
            "source": document_name or path.name,
            "document_name": document_name or path.name,
            "page": page.page,
            "section_heading": " | ".join(page.headings) if page.headings else "",
            "policy_category": _infer_category(path.name, page.text),
        }
        if page.text.strip():
            result.append(Document(page_content=page.text.strip(), metadata={**common, "content_type": "text"}))
        for table_index, table in enumerate(page.tables):
            result.append(Document(
                page_content=f"Extracted policy table:\n{table}",
                metadata={**common, "content_type": "table", "table_index": table_index},
            ))
    return result


def _infer_category(name: str, text: str) -> str:
    sample = f"{name} {text[:1000]}".lower()
    categories = {
        "settlements": ("settlement",),
        "refunds": ("refund",),
        "payouts": ("payout",),
        "disputes": ("dispute", "chargeback"),
        "compliance": ("compliance",),
        "fees": ("fee", "fees"),
        "limits": ("limit",),
        "kyc": ("kyc", "know your customer"),
        "onboarding": ("onboard",),
        "risk": ("risk",),
    }
    return next(
        (category for category, terms in categories.items() if any(term in sample for term in terms)),
        "general",
    )
