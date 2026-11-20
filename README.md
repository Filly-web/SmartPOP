# Britam POP Management Portal — V1.0.1 (CETTP PostgreSQL-ready)

A Flask portal for Proof of Payment submission, cashier review, approval, receipt batching and Excel export.

## Database integration with CETTP

This version is designed to use the **existing CETTP PostgreSQL database connection** while keeping its data isolated from CETTP application tables. POP Portal tables are explicitly prefixed:

- `popm_users`
- `popm_submissions`
- `popm_batches`
- `popm_audit_log`

The app does not rename, update, or delete CETTP tables. It creates only the four `popm_*` tables if they are missing. Use `POP_DATABASE_URL` (recommended) rather than sharing the generic `DATABASE_URL` environment variable. Set its value to the CETTP PostgreSQL connection string, but do not put it in source code or share it in chat. Confirm the database role has permission to create and use tables.

## Local setup (Windows PowerShell)

1. Extract the ZIP and open PowerShell in the `pop_portal_build` folder.
2. Create a virtual environment and install dependencies:
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Configure local environment (local SQLite is used only if no database URL is set):
   ```powershell
   $env:POP_SECRET_KEY = "use-a-long-random-secret"
   $env:INITIAL_ADMIN_USERNAME = "popadmin"
   $env:INITIAL_ADMIN_PASSWORD = "choose-a-strong-password-10-chars-or-more"
   $env:INITIAL_ADMIN_NAME = "POP Portal Administrator"
   python app.py
   ```
4. Open `http://127.0.0.1:5000`. Use the initial admin credentials you configured and create the cashier/submitter accounts.


## Render deployment using CETTP PostgreSQL

Create a **separate web service** for POP Portal. The included `render.yaml` configures a Standard web service and 1 GB persistent disk for uploads. If the service's disk or plan differs in your Render account, review that cost/availability before deploying.

Set the service environment variables:

- `POP_SECRET_KEY`: long random secret (generated in the blueprint)
- `POP_DATABASE_URL`: the CETTP PostgreSQL connection URL (private/internal URL where available). Use the connection URL, not a database password alone. Keep it private.
- `POP_UPLOAD_DIR`: `/var/data/pop-uploads` (already set in blueprint; must match the persistent disk mount)
- `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_NAME`: first admin account values

After the first successful deployment and administrator creation, remove `INITIAL_ADMIN_PASSWORD` from the environment if desired. Do not remove `POP_SECRET_KEY` or `POP_DATABASE_URL`.


## Workflow

1. Admin creates user accounts and assigns organisation and role.
2. Submitter submits a POP with customer, policy, amount and attachment.
3. Cashier reviews the POP, completes receipt details, saves and approves/returns/rejects.
4. Approved complete records can be selected into a batch; batched records are locked from accounting changes.
5. Cashier downloads a generated workbook using the supplied bulk receipts template. The template's lookup sheets and dropdown list extension are preserved.

## Export mapping

`AllocationBasis` = `ON_POLICY`; `PolicyNumber` = policy number; `DebitnoteNumber` = debit note; `Amount` = verified amount; `PayMode` = cashier-selected value; `BankReference` = bank reference; `DebitAccount` = selected value; `CreditAccount` = selected value; `Currency` = selected value; `CurrencyRate` = cashier-entered rate.

## Important deployment/security notes

- The four POP tables use a unique prefix to avoid name collisions with CETTP tables, but this is still a shared database. Back up CETTP PostgreSQL before deployment and verify permissions/schema policy with the database owner.
- POP documents are stored on the configured persistent disk. Local file storage is used only for local testing.
- V1.0.1 is a baseline; before internet-facing or broad business use, add CSRF protection, rate-limiting, password reset/change, email notifications, submitter correction/resubmission for returned POPs, stronger file validation/virus scanning, and a security review.
- No CETTP records are modified by this application. It is only intended to create/read/write its own `popm_*` tables.
