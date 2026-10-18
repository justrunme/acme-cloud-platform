# One image for the PreSync gate and the evidence store.
# Digests are recomputed from the repository files copied here, so the image is the commit.
FROM python:3.12-slim
WORKDIR /acme
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 65534:65534
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m"]
CMD ["tools.presync_gate"]
