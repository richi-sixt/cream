FROM python:3.14-slim

WORKDIR /app

# System deps for pdfplumber / Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libjpeg62-turbo && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn fpdf2

COPY . .

ENV PYTHONPATH=/app

# Generate demo PDFs + seed DB on build
RUN python demo/init_demo.py

ENV FLASK_ENV=production
ENV SERVE_PDF_INLINE=true
ENV PENDENT_DIR=/app/demo/example/01-Rechnungen-Pendent
ENV BEZAHLT_DIR=/app/demo/example/02-Rechnungen-Bezahlt
ENV BEWEGUNGEN_DIR=/app/demo/example/03-Bewegungen

EXPOSE 5001

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "run:app"]
