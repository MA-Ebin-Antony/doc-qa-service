"""
Ingestion module: parse PDF and Excel files, store into SQLite + ChromaDB.

PDF strategy (pdfplumber):
- Iterate pages; extract tables first so their bounding boxes are known.
- For text, rebuild sections by detecting heading-like lines (bold/large font
  or ALL-CAPS short lines). Each section accumulates body text until a new
  heading is found.
- Tables are stored as structured JSON (headers + list-of-row-dicts).

Excel strategy (openpyxl / pandas):
- Read with pandas, using infer_datetime_format and dtype inference.
- Store one SQLite row per spreadsheet row; also embed a text summary of
  each row into ChromaDB for semantic search.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import pdfplumber
from sqlalchemy.orm import Session

from app.models import PDFSection, PDFTable, ExcelRow
from app.database import get_collection

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_heading(line: str, chars: list) -> tuple[bool, int]:
    """
    Heuristic: a line is a heading if it is short (<= 120 chars) and either
    all-uppercase, or uses a font size clearly larger than body text.
    Returns (is_heading, level) where level 1 = largest.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False, 0

    # All-caps heuristic
    alpha = [c for c in stripped if c.isalpha()]
    if alpha and all(c.isupper() for c in alpha) and len(stripped) > 2:
        return True, 1

    # Font-size heuristic (pdfplumber chars)
    if chars:
        sizes = [c.get("size", 0) for c in chars if c.get("text", "").strip()]
        if sizes:
            avg_size = sum(sizes) / len(sizes)
            if avg_size >= 13:
                return True, 1
            if avg_size >= 11:
                return True, 2

    return False, 0


def _sanitize_for_json(obj):
    """Recursively convert non-serializable types (Timestamps, etc.) to str."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ─────────────────────────────────────────────────────────────────────────────
# PDF ingestion
# ─────────────────────────────────────────────────────────────────────────────

def ingest_pdf(pdf_path: str, db: Session) -> Dict[str, int]:
    """
    Parse a PDF and persist sections + tables to SQLite and ChromaDB.
    Returns a summary dict with counts.
    """
    path = Path(pdf_path)
    filename = path.name

    # Guard: skip if already ingested
    existing = db.query(PDFSection).filter_by(source_file=filename).first()
    if existing:
        logger.info(f"PDF '{filename}' already ingested — skipping. Delete data/qa_store.db and data/chroma_store to re-ingest.")
        return {"sections": 0, "tables": 0, "skipped": True}

    collection = get_collection()

    sections_added = 0
    tables_added = 0
    chroma_docs: List[str] = []
    chroma_ids: List[str] = []
    chroma_metas: List[dict] = []

    current_heading = None
    current_level = 0
    current_body: List[str] = []
    current_page = 1

    def _flush_section():
        nonlocal sections_added
        body = "\n".join(current_body).strip()
        if not body:
            return
        sec = PDFSection(
            source_file=filename,
            page_number=current_page,
            heading_level=current_level or None,
            heading_text=current_heading,
            body_text=body,
        )
        db.add(sec)
        db.flush()

        # Embed for vector search
        text_for_embed = f"{current_heading or ''}\n{body}"
        chroma_docs.append(text_for_embed)
        chroma_ids.append(f"pdf_section_{sec.id}")
        chroma_metas.append({
            "type": "pdf_section",
            "source": filename,
            "page": current_page,
            "heading": current_heading or "",
            "db_id": sec.id,
        })
        sections_added += 1

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            current_page = page.page_number

            # ── Tables ────────────────────────────────────────────────────────
            page_tables = page.extract_tables()
            table_bboxes = [t.bbox for t in page.find_tables()] if page.find_tables() else []

            for tbl_idx, raw_table in enumerate(page_tables):
                if not raw_table or len(raw_table) < 2:
                    continue
                headers = [str(h).strip() if h else f"col{i}" for i, h in enumerate(raw_table[0])]
                rows = []
                for raw_row in raw_table[1:]:
                    row_dict = {}
                    for j, cell in enumerate(raw_row):
                        col = headers[j] if j < len(headers) else f"col{j}"
                        row_dict[col] = str(cell).strip() if cell is not None else ""
                    rows.append(row_dict)

                tbl = PDFTable(
                    source_file=filename,
                    page_number=current_page,
                    section_heading=current_heading,
                    headers=headers,
                    rows=rows,
                )
                db.add(tbl)
                db.flush()
                tables_added += 1

                # Embed a text representation of the table
                table_text = f"Table on page {current_page} (section: {current_heading or 'N/A'}):\n"
                table_text += " | ".join(headers) + "\n"
                for r in rows[:20]:  # cap for embedding size
                    table_text += " | ".join(str(v) for v in r.values()) + "\n"
                chroma_docs.append(table_text)
                chroma_ids.append(f"pdf_table_{tbl.id}")
                chroma_metas.append({
                    "type": "pdf_table",
                    "source": filename,
                    "page": current_page,
                    "heading": current_heading or "",
                    "db_id": tbl.id,
                })

            # ── Text / Sections ───────────────────────────────────────────────
            words = page.extract_words(extra_attrs=["size", "fontname"])
            lines_raw = page.extract_text() or ""
            for line in lines_raw.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                # Get chars for this line to check font size
                line_chars = [w for w in words if w.get("text", "") in stripped]
                is_h, level = _is_heading(stripped, line_chars)
                if is_h:
                    _flush_section()
                    current_heading = stripped
                    current_level = level
                    current_body = []
                else:
                    current_body.append(stripped)

    # Flush last section
    _flush_section()
    db.commit()

    # Batch-upsert into ChromaDB (max 500 at a time)
    if chroma_docs:
        batch_size = 500
        for i in range(0, len(chroma_docs), batch_size):
            collection.upsert(
                documents=chroma_docs[i:i+batch_size],
                ids=chroma_ids[i:i+batch_size],
                metadatas=chroma_metas[i:i+batch_size],
            )

    logger.info(f"PDF '{filename}': {sections_added} sections, {tables_added} tables ingested.")
    return {"sections": sections_added, "tables": tables_added}


# ─────────────────────────────────────────────────────────────────────────────
# Excel ingestion
# ─────────────────────────────────────────────────────────────────────────────

def ingest_excel(xlsx_path: str, db: Session) -> Dict[str, int]:
    """
    Parse an Excel file and persist each row to SQLite + ChromaDB.
    Returns a summary dict with counts.
    """
    path = Path(xlsx_path)
    filename = path.name

    # Guard: skip if already ingested
    existing = db.query(ExcelRow).filter_by(source_file=filename).first()
    if existing:
        logger.info(f"Excel '{filename}' already ingested — skipping. Delete data/qa_store.db and data/chroma_store to re-ingest.")
        return {"rows": 0, "skipped": True}

    collection = get_collection()

    total_rows = 0
    chroma_docs: List[str] = []
    chroma_ids: List[str] = []
    chroma_metas: List[dict] = []

    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")

    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name, dtype=None)
        # Convert Timestamp columns to ISO strings for JSON serialisation
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")

        columns = list(df.columns)

        for row_idx, row in df.iterrows():
            row_dict = _sanitize_for_json(row.to_dict())
            er = ExcelRow(
                source_file=filename,
                sheet_name=sheet_name,
                row_index=int(row_idx),
                data=row_dict,
            )
            db.add(er)
            db.flush()
            total_rows += 1

            # Build a textual summary for embedding
            parts = [f"{k}: {v}" for k, v in row_dict.items() if v not in (None, "", "nan", "None")]
            row_text = f"[{filename} / sheet:{sheet_name} / row:{row_idx}] " + "; ".join(parts)
            chroma_docs.append(row_text)
            chroma_ids.append(f"excel_row_{er.id}")
            chroma_metas.append({
                "type": "excel_row",
                "source": filename,
                "sheet": sheet_name,
                "row_index": int(row_idx),
                "db_id": er.id,
            })

    db.commit()

    # Batch-upsert into ChromaDB
    if chroma_docs:
        batch_size = 500
        for i in range(0, len(chroma_docs), batch_size):
            collection.upsert(
                documents=chroma_docs[i:i+batch_size],
                ids=chroma_ids[i:i+batch_size],
                metadatas=chroma_metas[i:i+batch_size],
            )

    logger.info(f"Excel '{filename}': {total_rows} rows ingested.")
    return {"rows": total_rows}
