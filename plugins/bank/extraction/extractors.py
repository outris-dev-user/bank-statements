"""Per-tool extractors. Each returns plain text (or table-flattened text).

Shared parser then turns text into transactions. Extractors that fail to
import or run raise; the runner catches and records them as 'unavailable'.
"""
from __future__ import annotations
from pathlib import Path
import io
import os
import shutil
import subprocess
import tempfile

# OpenMP thread count must be capped *before* torch is imported by any OCR
# engine — otherwise EasyOCR / docTR segfault on this Windows + torch CPU build.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# Load .env from backend/ if present so Azure keys are picked up.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
except ImportError:
    pass


# ---------- Pure text extractors (no OCR) ----------

def extract_pdfplumber(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def extract_pymupdf(path: Path) -> str:
    import fitz
    doc = fitz.open(path)
    out = "\n".join(page.get_text() for page in doc)
    doc.close()
    return out


def extract_pdfminer(path: Path) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(str(path))


def extract_pypdf2(path: Path) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def extract_pypdfium2(path: Path) -> str:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    parts = []
    for page in pdf:
        tp = page.get_textpage()
        parts.append(tp.get_text_range())
        tp.close()
        page.close()
    pdf.close()
    return "\n".join(parts)


# ---------- Table extractors ----------

def extract_pdfplumber_tables(path: Path) -> str:
    """Flatten all extracted tables to whitespace-separated rows."""
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            for table in p.extract_tables() or []:
                for row in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    out.append(" ".join(c for c in cells if c))
    return "\n".join(out)


def extract_camelot(path: Path) -> str:
    import camelot
    tables = camelot.read_pdf(str(path), pages="all", flavor="stream")
    out = []
    for t in tables:
        for _, row in t.df.iterrows():
            out.append(" ".join(str(c).strip() for c in row if str(c).strip()))
    return "\n".join(out)


def extract_tabula(path: Path) -> str:
    import tabula
    # encoding="cp1252" tolerates HDFC's non-UTF8 bullet chars in subprocess output.
    dfs = tabula.read_pdf(
        str(path), pages="all", lattice=False, stream=True, guess=True,
        encoding="cp1252",
    )
    out = []
    for df in dfs:
        for _, row in df.iterrows():
            out.append(" ".join(str(c).strip() for c in row if str(c) != "nan" and str(c).strip()))
    return "\n".join(out)


# ---------- OCR (rasterize first) ----------

def _rasterize(path: Path, dpi: int = 300):
    """Yield PIL.Image per page using pypdfium2 (no system deps)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    for page in pdf:
        img = page.render(scale=dpi / 72).to_pil()
        yield img
        page.close()
    pdf.close()


def extract_tesseract(path: Path) -> str:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    parts = []
    for img in _rasterize(path):
        parts.append(pytesseract.image_to_string(img, config="--psm 6"))
    return "\n".join(parts)


def extract_easyocr(path: Path) -> str:
    import easyocr
    import numpy as np
    reader = _easyocr_reader()
    parts = []
    for img in _rasterize(path, dpi=200):
        results = reader.readtext(np.array(img), detail=1, paragraph=False)
        # results: [(bbox, text, conf)]. Reconstruct lines by y-coordinate clustering.
        parts.append(_lines_from_ocr(results))
    return "\n".join(parts)


_EASYOCR_READER = None
def _easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import easyocr
        _EASYOCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _EASYOCR_READER


def extract_paddleocr(path: Path) -> str:
    import numpy as np
    ocr = _paddle_reader()
    parts = []
    for img in _rasterize(path, dpi=200):
        # v3 API: predict() returns list of dicts with rec_texts, rec_polys, rec_scores
        result = ocr.predict(np.array(img))
        flat = []
        for page_result in result or []:
            data = page_result if isinstance(page_result, dict) else getattr(page_result, "json", {}).get("res", {})
            texts = data.get("rec_texts", [])
            polys = data.get("rec_polys", data.get("dt_polys", []))
            scores = data.get("rec_scores", [1.0] * len(texts))
            for text, poly, score in zip(texts, polys, scores):
                bbox = poly.tolist() if hasattr(poly, "tolist") else poly
                flat.append((bbox, text, float(score)))
        parts.append(_lines_from_ocr(flat))
    return "\n".join(parts)


_PADDLE_READER = None
def _paddle_reader():
    global _PADDLE_READER
    if _PADDLE_READER is None:
        from paddleocr import PaddleOCR
        # paddleocr v3 dropped show_log; pass only args that exist.
        _PADDLE_READER = PaddleOCR(lang="en")
    return _PADDLE_READER


def extract_doctr(path: Path) -> str:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    model = _doctr_model()
    doc = DocumentFile.from_pdf(str(path))
    result = model(doc)
    return result.render()


_DOCTR_MODEL = None
def _doctr_model():
    global _DOCTR_MODEL
    if _DOCTR_MODEL is None:
        from doctr.models import ocr_predictor
        _DOCTR_MODEL = ocr_predictor(pretrained=True)
    return _DOCTR_MODEL


def extract_docling(path: Path) -> str:
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    result = converter.convert(str(path))
    md = result.document.export_to_markdown()
    # docling renders transactions as markdown tables. Convert pipe-delimited
    # rows to whitespace-separated so the shared regex parser sees them.
    out = []
    for line in md.split("\n"):
        if line.strip().startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append(" ".join(c for c in cells if c))
        else:
            out.append(line)
    return "\n".join(out)


def extract_rapidocr(path: Path) -> str:
    """ONNX-based OCR (no torch). Comes via docling install."""
    from rapidocr import RapidOCR
    import numpy as np
    engine = _rapidocr_engine()
    parts = []
    for img in _rasterize(path, dpi=200):
        result = engine(np.array(img))
        # rapidocr returns object with boxes/txts/scores attrs
        flat = []
        if hasattr(result, "boxes") and result.boxes is not None:
            for bbox, text, score in zip(result.boxes, result.txts or [], result.scores or []):
                flat.append((bbox.tolist() if hasattr(bbox, "tolist") else bbox, text, float(score)))
        parts.append(_lines_from_ocr(flat))
    return "\n".join(parts)


_RAPIDOCR_ENGINE = None
def _rapidocr_engine():
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        from rapidocr import RapidOCR
        _RAPIDOCR_ENGINE = RapidOCR()
    return _RAPIDOCR_ENGINE


# ---------- Cloud SaaS ----------

def extract_azure_docintel(path: Path) -> str:
    """Azure Document Intelligence with prebuilt-layout.

    Returns text reconstructed line-by-line so the shared regex parser
    can find transactions. Azure's layout model groups tokens by line
    out of the box.
    """
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.environ.get("AZURE_DOCINTEL_ENDPOINT")
    key = os.environ.get("AZURE_DOCINTEL_KEY")
    if not endpoint or not key:
        raise RuntimeError(
            "Set AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY in bank-analyser/backend/.env"
        )

    client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    with open(path, "rb") as f:
        poller = client.begin_analyze_document("prebuilt-layout", document=f)
    result = poller.result()

    # Azure detects tables with row/column indices — use those directly instead
    # of raw lines (raw lines mis-cluster when columns are visually close).
    rows = []
    for t in result.tables:
        grid = {}
        for c in t.cells:
            grid[(c.row_index, c.column_index)] = c.content.replace("\n", " ").strip()
        for r_i in range(t.row_count):
            cells = [grid.get((r_i, c_i), "") for c_i in range(t.column_count)]
            rows.append(" ".join(c for c in cells if c))
    return "\n".join(rows)


# ---------- OCR line reconstruction ----------

def _lines_from_ocr(detections, y_tol: int = 12) -> str:
    """Cluster (bbox, text, conf) detections into lines by y-coordinate.

    bbox is a 4-point polygon: [[x,y],...]. Use top-left y for clustering.
    Within a line, sort by left-x.
    """
    if not detections:
        return ""
    items = []
    for bbox, text, _conf in detections:
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        items.append((min(ys), min(xs), text))
    items.sort()  # by y, then x
    lines = []
    current_y = None
    current = []
    for y, x, text in items:
        if current_y is None or abs(y - current_y) <= y_tol:
            current.append((x, text))
            current_y = y if current_y is None else current_y
        else:
            current.sort()
            lines.append(" ".join(t for _, t in current))
            current = [(x, text)]
            current_y = y
    if current:
        current.sort()
        lines.append(" ".join(t for _, t in current))
    return "\n".join(lines)


# ---------- Registry ----------

EXTRACTORS = {
    "pdfplumber_text": extract_pdfplumber,
    "pdfplumber_tables": extract_pdfplumber_tables,
    "pymupdf": extract_pymupdf,
    "pdfminer": extract_pdfminer,
    "pypdf2": extract_pypdf2,
    "pypdfium2": extract_pypdfium2,
    "camelot_stream": extract_camelot,
    "tabula": extract_tabula,
    "tesseract": extract_tesseract,
    "easyocr": extract_easyocr,
    "paddleocr": extract_paddleocr,
    "doctr": extract_doctr,
    "docling": extract_docling,
    "rapidocr": extract_rapidocr,
    "azure_docintel": extract_azure_docintel,
}
