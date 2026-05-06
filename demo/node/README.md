# CODI Demo — Next.js (Node)

This project provides a tiny Next.js application with an intentionally naive Dockerfile. It
exists purely as a target for CODI optimisation experiments.

## Local Development

```bash
npm install
npm run dev
```

## Container Build (naive)

```bash
docker build -t codi-demo-node .
docker run --rm -p 3000:3000 codi-demo-node
```
