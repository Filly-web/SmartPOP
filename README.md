# Britam POP Management Portal — V1.0

Independent Flask application for Proof of Payment submission, cashier review, approval and bulk receipt batch export. It is separate from CETTP and has its own database configuration and upload directory.

## Included in V1.0
- Role-based accounts: Submitter, Cashier and Administrator.
- Submit POP with mandatory customer name, policy number, amount and PDF/JPG/PNG attachment.
- Optional policy type, debit note number and submitter note.
- Submitter-only record visibility; Cashier/Admin can review all submissions.
- Inline attachment preview and separate download.
- Cashier can complete debit note, payment mode, bank reference, debit/credit accounts, currency and currency rate; amount can be verified/amended.
- Approve, return for correction or reject with comments.
- Audit history for submission, cashier edits, decisions and batch inclusion.
- Multi-select approved POPs and create a unique receipt batch.
- Batch Excel export using the supplied original workbook, preserving its six worksheets and exact ten-column Template header.
- User administration and activation/deactivation.
- SQLite local default; PostgreSQL supported through `DATABASE_URL`.

## Local setup (Windows PowerShell)
1. Install Python 3.12.
2. Extract the ZIP.
3. Open PowerShell in the extracted folder.
4. Run:
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:SECRET_KEY = "replace-with-a-long-random-secret"
   $env:INITIAL_ADMIN_USERNAME = "popadmin"
   $env:INITIAL_ADMIN_PASSWORD = "set-a-strong-password-at-least-10-chars"
   $env:INITIAL_ADMIN_NAME = "POP Portal Administrator"
   python app.py
   ```
5. Browse to http://127.0.0.1:5000 and sign in with the configured administrator credentials.
6. Use **User administration** to create Cashier and submitter accounts.

The SQLite database is created at `instance/pop_portal.db`; uploaded POP files are stored in `uploads/`.

## Render deployment using existing Render account
Create a **new Web Service** in the existing Render account (do not connect this service to CETTP's service or database). Connect this project repository and use:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Runtime: Python 3.12

Set environment variables:
- `SECRET_KEY`: long random secret
- `DATABASE_URL`: connection string for a **new, dedicated POP Portal PostgreSQL database**. Do not use CETTP's database URL.
- `INITIAL_ADMIN_USERNAME`: administrator username
- `INITIAL_ADMIN_PASSWORD`: strong initial administrator password (10+ characters)
- `INITIAL_ADMIN_NAME`: POP Portal Administrator

The app automatically creates the first administrator when those three `INITIAL_ADMIN_*` variables are present and the username does not already exist. After first successful deployment and admin creation, remove `INITIAL_ADMIN_PASSWORD` from the service environment if desired; keep `SECRET_KEY` and `DATABASE_URL`.

### Important hosting note
Render's ephemeral filesystem is not suitable for retaining uploaded POP documents across redeploys/restarts. The first version stores files locally in `uploads/`, which is suitable for local testing but **not production-safe on Render** unless a persistent disk or object storage is configured. The Render Free plan does not provide a persistent disk. Before production use, configure persistent file storage (for example, a Render persistent disk on a supported paid service, or S3-compatible object storage) and update the file-storage adapter. Also use a persistent PostgreSQL database; do not use SQLite on Render.

## Workflow
1. Admin creates user accounts and assigns organisation and role.
2. Submitter signs in and uploads POP against customer/policy/amount.
3. Cashier reviews POP inline or downloads it, completes receipt details, saves and approves/returns/rejects.
4. Approved complete records appear under **Receipt batches**.
5. Cashier selects records and creates a batch. Records are locked from editing once batched.
6. Cashier downloads the generated workbook. Data is appended under the `Template` header; original lookup worksheets are retained.

## Export column mapping
`AllocationBasis` = `ON_POLICY`; `PolicyNumber` = policy number; `DebitnoteNumber` = debit note; `Amount` = verified amount; `PayMode` = selected template value; `BankReference` = bank reference; `DebitAccount` = selected template value; `CreditAccount` = selected template value; `Currency` = selected template value; `CurrencyRate` = cashier-entered rate.

## Current V1.0 limitations / next iteration
- No outbound email notifications yet; in-app statuses and comments are available.
- No direct receipt confirmation import from the internal system yet; `Receipted` status is reserved for the next workflow extension.
- File storage on Render must be upgraded to persistent/object storage before live production use.
- Add CSRF protection, password reset/change, login throttling and formal security review before external internet exposure.
- No edit/resubmit screen for returned POPs yet; the Cashier can return with a comment and the record remains visible to its submitter. Add submitter correction workflow in the next iteration.
