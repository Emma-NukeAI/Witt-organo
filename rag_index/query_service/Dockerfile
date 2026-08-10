# Webapp read-only query service (block 2, ADR-0048). Mirrors the ingest_service packaging: the whole
# repo is the build context because the service reuses analysis/scripts/lib + rag_index/mcp_server.
# Deploy on the Dokploy INTERNAL network only — the webapp is the single exposed surface (ADR-0047 d.5).
FROM python:3.12-slim

WORKDIR /app
COPY rag_index/query_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

# Secrets arrive as env vars (Dokploy) or a mounted .secrets/deploy.env — never baked into the image.
ENV DI_QUERY_POOL_SIZE=8
EXPOSE 8078

WORKDIR /app/rag_index/query_service
# --workers 1 is REQUIRED: in-process TTL caches + (block 5) the serialized write queue assume ONE process.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8078", "--workers", "1"]
