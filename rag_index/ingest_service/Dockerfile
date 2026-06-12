# Hosted ingestion service for the DATA INAMOVIBLE (ADR-0017/0021).
# Build context = REPO ROOT (so it can copy the reused libs). See docker-compose.ingest.yml.
FROM python:3.12-slim

WORKDIR /app
COPY rag_index/ingest_service/requirements.txt /app/req.txt
RUN pip install --no-cache-dir -r /app/req.txt

# the libs the service reuses (raw_store, resolve_id, corpus_classifier, add_dataset) + the index + ingest
COPY analysis/scripts /app/analysis/scripts
COPY rag_index /app/rag_index
COPY analysis/outputs/verified_identifiers.json /app/analysis/outputs/verified_identifiers.json
COPY analysis/outputs/refseq_ensembl_xref.json /app/analysis/outputs/refseq_ensembl_xref.json

ENV INGEST_QUEUE_DIR=/data/queue
EXPOSE 8077
CMD ["uvicorn", "rag_index.ingest_service.app:app", "--host", "0.0.0.0", "--port", "8077"]
