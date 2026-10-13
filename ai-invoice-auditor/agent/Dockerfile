FROM python:3.11.9-slim-bookworm

# 1) System packages (change rarely). Dataset languages: English, Spanish, German.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa tesseract-ocr-deu poppler-utils \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# 2) Python deps (change occasionally) - copied before source so code edits don't reinstall
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Application code (changes constantly)
COPY app ./app
USER appuser

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
