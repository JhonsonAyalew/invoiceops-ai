# Daily workflow

1. **New job & upload** - enter a job name and your Fiverr order reference, drop the client's PDFs (or a ZIP) and press
   *Create job & start extraction*. Files from different jobs never mix.
2. **Processing** - watch progress live. Failed files show the reason (corrupted, encrypted, not a PDF, too large). Identical
   files are marked *Duplicate*. Use **Retry** on a failed document after fixing the cause (e.g. installing OCR).
3. **Results** - filter by status, search by supplier or number, and see duplicate candidates.
4. **Review workspace** - original PDF on the left-centre, extracted fields on the right.
   - *missing* = a required field was not found; *check* = low confidence; *AI* = value came from the AI; *edited* = you changed it.
   - The original extracted value is kept and shown under any field you change; every correction is logged.
   - Validation warnings (total does not add up, due date before invoice date, unreliable line item...) are listed at the top.
   - **Mark reviewed & next** saves your edits, marks the invoice as reviewed by you, and opens the next one. Shortcuts:
     `Ctrl+S` save, `Alt+←` / `Alt+→` previous / next.
5. **Export center** - generate Excel, invoices CSV, line-items CSV and the PDF report, then download them from the list.
   The report states how many invoices you marked as reviewed; it never claims review that did not happen.
6. **Delete the job** (Jobs page) when finished: removes the PDFs, extracted data, corrections and exports permanently.

## Good to know
- One PDF is treated as one invoice (multi-page invoices are fine; several invoices inside one PDF are not split).
- Totals in the PDF report are summed per currency and never mixed.
- Numbers you type in review may use `1,234.56` or `1.234,56`.
