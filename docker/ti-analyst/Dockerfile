FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY apps/ti-analyst/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/ti-analyst/ .
COPY docker/ti-analyst/entrypoint.sh /usr/local/bin/ti-analyst-entrypoint

RUN chmod +x /usr/local/bin/ti-analyst-entrypoint

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/ti-analyst-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-include", "*.py", "--reload-exclude", "*/__pycache__/*"]
