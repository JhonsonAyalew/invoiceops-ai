# Windows installation

Everything runs on your own PC. Allow about 30 minutes the first time.

## 1. Install the prerequisites
| Tool | Version | Where |
|---|---|---|
| Python | **3.12** (tick "Add python.exe to PATH") | python.org/downloads — required for the PaddleOCR wheels |
| PostgreSQL | 15 or newer | postgresql.org/download/windows (remember the `postgres` password you set) |
| Poppler | any recent Windows build | see section 3 |
| Node.js 20+ | **only** if you want to rebuild the interface | nodejs.org |

## 2. Create the database
Open **SQL Shell (psql)** from the Start menu, log in as `postgres`, then run:
```sql
CREATE USER invoiceops WITH PASSWORD 'choose-a-password';
CREATE DATABASE invoiceops OWNER invoiceops;
```

## 3. Install Poppler (renders PDF pages for OCR)
1. Download a Windows build of Poppler (for example the "poppler-windows" releases on GitHub) and unzip it to `C:\poppler`.
2. Find the folder that contains `pdftoppm.exe` (usually `C:\poppler\Library\bin` or `C:\poppler\bin`).
3. Put that folder in `POPPLER_PATH` in `.env`.
Without Poppler, scanned PDFs fail with a clear "Poppler not found" message; text PDFs still work.

## 4. PP-OCRv6 Medium models
`scripts\setup.bat` downloads the two offline inference models automatically into `%LOCALAPPDATA%\InvoiceOps\paddle_models`:
`PP-OCRv6_medium_det` and `PP-OCRv6_medium_rec` (~130 MB total). To download or repair them manually, run:
```bat
scripts\download_models.bat
```
No Tesseract installation and no traineddata files are needed. The model is multilingual (English, German, French, Spanish).

## 5. Configure and install
1. Unzip the project, e.g. to `C:\InvoiceOps`.
2. Double-click `scripts\setup.bat`. The first run creates `.env` and stops. Open `.env` in Notepad and set at least
   `DATABASE_URL` (use your password) and, if different, `POPPLER_PATH`.
3. Run `scripts\setup.bat` again. It creates a virtual environment, installs the locked dependencies, downloads the OCR models if
   missing, creates the database tables (Alembic) and prints an OCR readiness report.

## 6. Run
Double-click `scripts\start.bat`. The browser opens on **http://127.0.0.1:8000**. Keep the black window open while you work.
The server listens only on your own PC. The built interface is included in `frontend\dist`, so Node.js is not required to run it.

## 7. Check OCR
Open **Settings → OCR**. You should see `PaddleOCR 3.7.0`, model `PP-OCRv6 Medium`, detection/recognition loaded from disk, and
Poppler found. Any problem is listed there with the fix.

## Developing the interface (optional)
```
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to port 8000
npm run build      # rebuilds frontend\dist
```

## Running the tests
`scripts\test.bat` (OCR tests need Poppler and the downloaded models; set `TEST_DATABASE_URL` to also run against PostgreSQL).
