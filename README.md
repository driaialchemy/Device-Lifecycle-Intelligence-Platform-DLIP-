# Device Lifecycle Intelligence Platform (DLIP)

Streamlit app for multi-agent device compliance auditing (R2v3, GDPR, Sensor), with PostgreSQL-backed persistence.

## 1. Clone
```bash
git clone https://github.com/driaialchemy/Device-Lifecycle-Intelligence-Platform-DLIP-.git
cd Device-Lifecycle-Intelligence-Platform-DLIP-
```

## 2. Configure environment
```bash
cp .env.example .env
```

Edit `.env` and set:
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DATABASE_URL` (for your local Postgres)

## 3. Install dependencies
```bash
pip install -r requirements.txt
```

## 4. Start PostgreSQL and create DB
```sql
CREATE DATABASE device_passport;
```

Use the credentials from your `DATABASE_URL`.

## 5. Seed database (optional if already populated)
```bash
python seed_db.py
```

Optional seed overrides:
- `DP_SEED_XLSX` (path to workbook)
- `DP_SEED_SHEET` (sheet name, default: `devices`)

## 6. Run app
```bash
streamlit run app.py
```
