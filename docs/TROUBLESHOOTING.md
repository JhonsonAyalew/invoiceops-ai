# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Settings → OCR says **paddleocr is not installed** | Run `scripts\setup.bat` (or `pip install -r requirements.txt`) and restart. |
| Settings → OCR says **PP-OCRv6 Medium model folder(s) missing** | Run `scripts\download_models.bat`, or set `PADDLE_MODEL_DIR` to the folder containing `PP-OCRv6_medium_det` and `PP-OCRv6_medium_rec`. |
| **Poppler not found** | Set `POPPLER_PATH` to the folder containing `pdftoppm.exe`. |
| Scanned documents show `ocr_failed` | Fix the OCR item above, then press **Retry** on each document. |
| `setup.bat`: database migration failed | PostgreSQL not running, wrong password/URL in `.env`, or the `invoiceops` database was not created. |
| Browser shows "Admin token required" | `ADMIN_TOKEN` is set in `.env`; enter that value. |
| Upload says `file_too_large` | Raise `MAX_UPLOAD_MB`. ZIP errors: `zip_too_many_files` / `zip_too_large` raise `MAX_ZIP_*`. |
| A number was misread (e.g. 1.234 as 1234) | The document mixes formats. Correct it in the review workspace; it is flagged when totals do not add up. |
| Ollama: cannot connect | Start Ollama, check `OLLAMA_URL`, run `ollama pull <model>`. |
| Groq: `GROQ_API_KEY is not configured` | Add the key to `.env` and restart the server. |
| Groq: authentication failed / model not available | Check the key and `GROQ_MODEL` (for example `openai/gpt-oss-20b`), then use **Settings → AI provider → Test connection**. |
| Cloud AI skipped: no consent | Open the job and click **Authorise Groq** (or tick the consent box when creating the job). |
| Port 8000 in use | Edit `--port` in `scripts\start.bat`. |
| Everything OCR-based is slow | Lower `OCR_DPI` to 200, or raise `PROCESSING_WORKERS` if you have spare CPU cores. PaddleOCR predictions are serialised for stability. |
| OCR fails with a oneDNN / PIR attribute error | The app disables oneDNN (`enable_mkldnn=False`); keep `PADDLE_DEVICE=cpu` unless you installed the CUDA build. |
