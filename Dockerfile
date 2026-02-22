FROM python:3.11-slim

WORKDIR /app

# System deps: build basics + FFT (numpy/scipy) + postgres driver support
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code
COPY . /app

# Seed file must exist at ./seed/devicepassport_catalog.xlsx
# (You put your synthetic workbook there.)
EXPOSE 8501

CMD ["bash", "-lc", "python seed_db.py && streamlit run app.py --server.port=8501 --server.address=0.0.0.0"]
