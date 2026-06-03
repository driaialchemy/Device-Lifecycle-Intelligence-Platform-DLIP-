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
- `DATABASE_URL` if you are not using the bundled Docker database

## 3. Install dependencies
```bash
pip install -r requirements.txt
```

## 4. Start PostgreSQL
The quickest local path is the bundled Docker database. It uses host port `5434`
by default so it does not conflict with an existing local PostgreSQL on `5432`.

```bash
docker compose up -d dp-db
```

If you prefer your own PostgreSQL server, create the database named in
`DATABASE_URL` and update `.env` with your credentials.

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
