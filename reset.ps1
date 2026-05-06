# ============================================================
# reset.ps1  —  Wipe all ingested data for a clean fresh start
# Run from the doc-qa-service folder:
#   powershell -ExecutionPolicy Bypass -File reset.ps1
# ============================================================

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host ""
Write-Host "==============================" -ForegroundColor Red
Write-Host "  Resetting all ingested data " -ForegroundColor Red
Write-Host "==============================" -ForegroundColor Red
Write-Host ""

# ── SQLite: clear all rows but keep the file ─────────────────────────────────
if (Test-Path "data\qa_store.db") {
    & "C:\Users\ebin.antony\Downloads\task\task\.venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect('data/qa_store.db')
for table in ['pdf_sections', 'pdf_tables', 'excel_rows']:
    con.execute(f'DELETE FROM {table}')
try:
    for table in ['pdf_sections', 'pdf_tables', 'excel_rows']:
        con.execute('DELETE FROM sqlite_sequence WHERE name=?', (table,))
except Exception:
    pass  # sqlite_sequence doesn't exist if tables were never populated
con.commit()
con.close()
print('  SQLite: all rows cleared, IDs reset to 1.')
"
} else {
    Write-Host "  Skipped: data\qa_store.db (not found)" -ForegroundColor DarkGray
}

# ── ChromaDB: delete the folder entirely (recreated fresh on next ingest) ─────
if (Test-Path "data\chroma_store") {
    Remove-Item "data\chroma_store" -Recurse -Force
    Write-Host "  Deleted: data\chroma_store\" -ForegroundColor Green
} else {
    Write-Host "  Skipped: data\chroma_store\ (not found)" -ForegroundColor DarkGray
}

# ── Python cache (optional cleanup) ──────────────────────────────────────────
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | ForEach-Object {
    Remove-Item $_.FullName -Recurse -Force
}
Write-Host "  Deleted: __pycache__ folders" -ForegroundColor Green

Write-Host ""
Write-Host "Done. Project is now in a fresh state." -ForegroundColor Cyan
Write-Host ""
Write-Host "To re-ingest your files run:" -ForegroundColor White
Write-Host "  python cli.py ingest --pdf data\manual.pdf --excel data\inventory.xlsx" -ForegroundColor Yellow
Write-Host ""
