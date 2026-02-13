FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY pyproject.toml README.md /app/
COPY curious_now /app/curious_now
COPY config /app/config
COPY design_docs /app/design_docs
COPY scripts /app/scripts

RUN python -m pip install --upgrade pip \
    && pip install .

USER app

EXPOSE 8000

CMD ["uvicorn", "curious_now.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
