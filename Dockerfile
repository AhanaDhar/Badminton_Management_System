# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# Optional CA mount supports builds inside the managed workspace.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd --create-home --uid 10001 academy
COPY --chown=academy:academy . .
USER academy
EXPOSE 5000 8501
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "backend:create_app()"]
