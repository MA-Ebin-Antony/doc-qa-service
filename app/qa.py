import os
import logging
from typing import List, Dict, Any

from groq import Groq
from sqlalchemy.orm import Session

from app.database import get_collection
from app.models import PDFSection, PDFTable, ExcelRow

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "10"))


def _build_context_block(meta: dict, doc: str, db: Session) -> dict:
    rtype = meta.get("type")
    db_id = meta.get("db_id")

    if rtype == "pdf_section" and db_id:
        rec = db.get(PDFSection, db_id)
        if rec:
            return {
                "citation": f"[PDF] {rec.source_file} — page {rec.page_number}, section: '{rec.heading_text or 'N/A'}'",
                "content": f"Section '{rec.heading_text}' (p.{rec.page_number}):\n{rec.body_text}",
                "type": "pdf_section",
            }

    elif rtype == "pdf_table" and db_id:
        rec = db.get(PDFTable, db_id)
        if rec:
            header_line = " | ".join(rec.headers)
            rows_text = "\n".join(" | ".join(str(r.get(h, "")) for h in rec.headers) for r in rec.rows)
            return {
                "citation": f"[PDF Table] {rec.source_file} — page {rec.page_number}, near section: '{rec.section_heading or 'N/A'}'",
                "content": f"Table (p.{rec.page_number}):\n{header_line}\n{rows_text}",
                "type": "pdf_table",
            }

    elif rtype == "excel_row" and db_id:
        rec = db.get(ExcelRow, db_id)
        if rec:
            data_str = "; ".join(f"{k}: {v}" for k, v in rec.data.items())
            return {
                "citation": f"[Excel] {rec.source_file} — sheet '{rec.sheet_name}', row {rec.row_index}",
                "content": f"Row {rec.row_index} ({rec.sheet_name}): {data_str}",
                "type": "excel_row",
            }

    return {
        "citation": f"[{meta.get('source', 'unknown')}]",
        "content": doc,
        "type": rtype or "unknown",
    }


def answer_question(question: str, db: Session) -> Dict[str, Any]:
    collection = get_collection()
    results = collection.query(
        query_texts=[question],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []

    if not docs:
        return {
            "question": question,
            "answer": "No relevant information found in the ingested documents.",
            "citations": [],
            "context_chunks": [],
        }

    context_blocks = [_build_context_block(meta, doc, db) for doc, meta in zip(docs, metas)]

    context_text = "\n\n---\n\n".join(
        f"SOURCE {i+1}: {b['citation']}\n{b['content']}" for i, b in enumerate(context_blocks)
    )

    system_prompt = (
        "You are a precise document Q&A assistant. "
        "Answer the user's question using ONLY the provided source excerpts. "
        "Combine information from ALL relevant sources — do not stop at the first match. "
        "If a section and a table both contain relevant information, include details from both. "
        "Always cite which source (document, page, section, or row) each part of your answer comes from. "
        "If the answer is not present in the sources, say so clearly. "
        "Be concise and factual."
    )

    user_prompt = (
        f"SOURCES:\n{context_text}\n\n"
        f"QUESTION: {question}\n\n"
        "Provide a clear answer with citations."
    )

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    client = Groq(api_key=groq_api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=GROQ_MODEL,
        temperature=0.1,
        max_tokens=1024,
    )

    answer = chat_completion.choices[0].message.content.strip()
    citations = list({b["citation"] for b in context_blocks})

    logger.info(f"Q: '{question}' answered with {len(context_blocks)} chunks.")
    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "context_chunks": context_blocks,
    }
