# 🏗️ System Architecture: LLM-Based Dockerfile Optimizer

## 1. High-Level Concept
This tool uses a small, fine-tuned Language Model (Qwen2.5-Coder-3B) to automatically refactor Dockerfiles. It focuses on three metrics:
1.  **Security:** (CIS Benchmarks, non-root users).
2.  **Size:** (Alpine/Distroless, multi-stage builds).
3.  **Speed:** (Layer caching optimization).

## 2. The "Teacher-Student" Pipeline
We do not rely on raw GitHub data alone. We use a high-intelligence "Teacher" model to curate the dataset.

### A. The Data Loop
1.  **Ingest:** Raw Dockerfiles scraped from GitHub.
2.  **Analyze:** Run `hadolint` (Static) + `docker build` (Dynamic).
3.  **Score:** Calculate a "Badness Score" (0-100).
4.  **Enhance (Teacher):** A GPT-4 class model rewrites the "Middle 50%" of files using the `DOCKER_CONSTITUTION.md`.
5.  **Train (Student):** Fine-tune Qwen-3B on the pair: `(Bad Input + Analysis) -> (Golden Output)`.

### B. The Scoring Engine
A deterministic formula to validate improvements:
$$Score = 100 - (10 \times Errors) - (5 \times Warnings) - (20 \times SizeExcess) + (15 \times MultiStage)$$

## 3. Technology Stack
* **Base Model:** Qwen2.5-Coder-3B-Instruct.
* **Training:** Unsloth (QLoRA, 4-bit).
* **Tools:** `hadolint` (Linting), `docker` (Metrics), `python` (Orchestration).
* **Vector DB:** (Optional) For few-shot retrieval of similar solved cases.