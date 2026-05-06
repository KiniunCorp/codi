# CODI Demo — FastAPI (Python)

This folder contains a minimal FastAPI application with a purposefully naive Dockerfile. It is
used to validate the Python stack during CODI development.

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Container Build (naive)

```bash
docker build -t codi-demo-python .
docker run --rm -p 8000:8000 codi-demo-python
```
