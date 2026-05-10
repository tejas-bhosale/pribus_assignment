FROM python:3.11-slim

WORKDIR /app

# Install dependencies in a separate layer for better cache utilisation
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# 4 workers handles concurrent bulk requests; timeout covers slow upstream API
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "wsgi:app"]
