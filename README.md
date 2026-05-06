# Document Q&A Service

A small service that ingests a PDF manual and an Excel inventory file, stores their content in a hybrid database, and answers natural-language questions grounded in the stored data — with citations — using **Groq** as the LLM backend.

---

## Prerequisites

- Python 3.10+
- A free [Groq API key](https://console.groq.com)

---

### setup

```powershell
cd doc-qa-service
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
# Create .env manually and add: GROQ_API_KEY=your_key_here or use below step to create env and assign keys
```

After setup, create a `.env` file in the project folder with your Groq API key:
```
echo "GROQ_API_KEY="your_env_key" > .env
```

## Ingest Your Files

```powershell
python cli.py ingest --pdf data\manual.pdf --excel data\inventory.xlsx
```

Expected output like below:
```
Ingesting PDF: data\manual.pdf
  → 12 sections, 3 tables ingested.
Ingesting Excel: data\inventory.xlsx
  → 297 rows ingested.


## Ask Questions

### CLI
```powershell
python cli.py ask "What are the safety precautions before maintenance?"
python cli.py ask "What fuel filter part is required and what is the part number?"
python cli.py ask "Spares required for cooling system"
python cli.py ask "What is the overhaul interval for the pump?"

```



### Parsing Strategy

**PDF** — parsed using `pdfplumber`
- Reads the file page by page
- Extracts tables and saves them as structured rows
- Detects headings and splits the text into labelled sections

**Excel** — parsed using `pandas` and `openpyxl`
- Reads all sheets automatically
- Preserves column types — numbers, dates, and text are kept as-is
- Each row is saved individually so it can be searched later

### Database Schema

```
pdf_sections    — one row per heading + body text block
  id, source_file, page_number, heading_level, heading_text, body_text

pdf_tables      — one row per table extracted from the PDF
  id, source_file, page_number, section_heading, headers (JSON), rows (JSON)

excel_rows      — one row per spreadsheet row, per sheet
  id, source_file, sheet_name, row_index, data (JSON)
```

### Why SQLite + ChromaDB?

**SQLite** — structured, relational, zero-config, single file. Stores the full text and data. Can run exact SQL queries.

**ChromaDB** — vector database for semantic search. Stores `all-MiniLM-L6-v2` embeddings locally (no API key needed, ~90 MB model auto-downloaded on first run). Finds relevant chunks by *meaning*, not just keyword match.

Together:
- SQLite answers *what exactly is stored*
- ChromaDB answers *what is most relevant to this question*

### How Q&A Works (RAG — Retrieval-Augmented Generation)

```
User question
    ↓
① ChromaDB — embed question, find top-10 closest chunks
    ↓
② SQLite — fetch full text/data for each chunk
    ↓
③ Build prompt: system instructions + source excerpts + question
    ↓
④ Groq llama-3.3-70b-versatile — reads sources, writes cited answer
    ↓
Answer + citations returned
```

The LLM **never searches the database directly** — ChromaDB + SQLite do the searching. The LLM only reads what is passed in the prompt and writes a coherent, cited response.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Your Groq API key — get free at https://console.groq.com |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `SQLITE_PATH` | `data/qa_store.db` | SQLite database file path |
| `CHROMA_PATH` | `data/chroma_store` | ChromaDB persistence folder |
| `RETRIEVAL_TOP_K` | `10` | Number of chunks retrieved per question |

---

## What I'd Do With Another Day

1. **Add a simple web UI** — a basic HTML page where users can type a question and see the answer, instead of using the command line.
2. **Support more file types** — allow uploading Word documents (.docx) or plain text files alongside PDF and Excel.
5. **Multi-language support** — allow questions to be asked in languages other than English and return answers in the same language.
