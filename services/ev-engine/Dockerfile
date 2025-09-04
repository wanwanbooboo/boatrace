FROM python:3.11-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PIP_NO_CACHE_DIR=1 \
TZ=Asia/Tokyo


RUN apt-get update && apt-get install -y --no-install-recommends \
tzdata curl ca-certificates && \
rm -rf /var/lib/apt/lists/*


# 非rootユーザ
RUN useradd -u 10001 -m app
WORKDIR /app


COPY requirements.txt ./
RUN pip install -r requirements.txt


COPY app ./app
USER app


EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]