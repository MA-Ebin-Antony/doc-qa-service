import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.database import init_db, SessionLocal
from app.ingest import ingest_pdf, ingest_excel
from app.qa import answer_question


def cmd_ingest(args):
    init_db()
    db = SessionLocal()
    try:
        if args.pdf:
            print(f"Ingesting PDF: {args.pdf}")
            result = ingest_pdf(args.pdf, db)
            if result.get("skipped"):
                print(f"  → Already ingested, skipped. Run reset.ps1 to re-ingest.")
            else:
                print(f"  → {result['sections']} sections, {result['tables']} tables ingested.")
        if args.excel:
            print(f"Ingesting Excel: {args.excel}")
            result = ingest_excel(args.excel, db)
            if result.get("skipped"):
                print(f"  → Already ingested, skipped. Run reset.ps1 to re-ingest.")
            else:
                print(f"  → {result['rows']} rows ingested.")
    finally:
        db.close()


def cmd_ask(args):
    db = SessionLocal()
    try:
        result = answer_question(args.question, db)
        print(f"\nQuestion: {result['question']}\n")
        print(f"Answer:\n{result['answer']}\n")
        print("Citations:")
        for c in result["citations"]:
            print(f"  • {c}")
        if args.verbose:
            print("\n--- Context chunks ---")
            for chunk in result["context_chunks"]:
                print(f"\n[{chunk['citation']}]\n{chunk['content'][:300]}...")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Document Q&A Service CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest PDF and/or Excel files")
    p_ingest.add_argument("--pdf", help="Path to the PDF file")
    p_ingest.add_argument("--excel", help="Path to the Excel file")

    p_ask = sub.add_parser("ask", help="Ask a question")
    p_ask.add_argument("question", help="Natural-language question")
    p_ask.add_argument("--verbose", "-v", action="store_true", help="Show retrieved context chunks")

    args = parser.parse_args()

    if args.command == "ingest":
        if not args.pdf and not args.excel:
            parser.error("Provide at least --pdf or --excel (or both).")
        cmd_ingest(args)
    elif args.command == "ask":
        cmd_ask(args)


if __name__ == "__main__":
    main()
