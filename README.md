# Device Lifecycle Intelligence Platform (DLIP)

Streamlit app for multi-agent device compliance auditing (R2v3, GDPR, Sensor), with PostgreSQL-backed persistence.

## Dashboard Capabilities

- Operator, Engineering, and Executive views can each select a device and run role-specific AI analysis.
- Each role has its own analysis lens menu:
  - Operator: intake, exception, or release re-check.
  - Engineering: sensor degradation, R2v3 repair readiness, privacy data remanence, or audit-chain traceability.
  - Executive: board risk brief, compliance exposure, revenue recovery, or escalation watchlist.
- Engineering includes a Forecast Lab for watch future-state analysis.
- Executive includes a compact Future-State Snapshot for leadership review.

For future-state forecasting, the recommended baseline is linear battery degradation because battery health generally declines over time. The app also offers a hybrid trend plus Fourier residual model when repeated cycles exist. Fourier/Welch spectral analysis is used for sensor signal quality and periodic noise detection, which is better suited to sensor stability than direct battery-life forecasting.

Chart options include battery forecast, sensor waveform, sensor FFT/Welch spectrum, and a combined future-state summary.

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
