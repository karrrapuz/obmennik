FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade 'pip>=26.2.2,<27' \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:application --factory --host 0.0.0.0 --port ${PORT:-8000}"]
