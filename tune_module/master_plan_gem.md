This document consolidates our entire discussion into a single, execution-ready Master Plan. This effectively serves as your **Technical Design Document (TDD)** for the project.

-----

# 🐳 Project: LLM-Based Dockerfile Optimizer

**Target Model:** Qwen2.5-Coder-3B-Instruct (via QLoRA)  
**Goal:** Create a specialized 3B parameter model capable of analyzing, refactoring, and optimizing Dockerfiles for Security, Speed, and Size.

-----

## 1\. High-Level Architecture

The system relies on a **Teacher-Student** architecture to bootstrap high-quality training data, followed by **Reinforcement Learning** (DPO) to align the model with real-world build metrics.

### The "Smart Loop" Workflow

1.  **Ingest:** Raw Dockerfile (from GitHub scraping).
2.  **Audit:** Run deterministic tools (`hadolint`, `docker build`).
3.  **Enrich:** Teacher LLM (GPT-4o) applies the "Constitution" to generate a Golden Solution.
4.  **Train:** Fine-tune Student (Qwen-3B) on `(Bad Input + Audit Data) -> (Golden Output)`.
5.  **Refine:** Use DPO (Direct Preference Optimization) based on actual build stats (Size/Time).

-----

## 2\. Phase I: Knowledge Engineering ("The Constitution")

Before generating data, we define the "Ground Truth." This prevents the model from hallucinating optimizations.

**Action:** Create `docker_best_practices.md`.  
**Content Source:** CIS Benchmarks, Hadolint Rules, BuildKit Docs.  
*(Refer to the previous response for the full markdown content of this file).*

**Key Pillars:**

  * **Security:** Non-root users, pinned versions, no secrets in ENV.
  * **Performance:** Multi-stage builds, correct layer ordering.
  * **Syntax:** Hadolint compliance (no `cd`, use `WORKDIR`).

-----

## 3\. Phase II: Data Pipeline & Curation

We need to transform 7,000 raw text files into a structured training set.

### A. The Analyzer Script

A Python script that runs for every raw file to extract "Context."

```python
# Output Structure (Metadata)
{
  "file_id": "gh_12345",
  "original_content": "FROM node...",
  "metrics": {
    "size_mb": 850,       # from docker build
    "build_time_s": 120,  # from docker build
    "hadolint_score": 45, # calculated from raw hadolint json
    "violations": ["DL3002", "DL3003"]
  }
}
```

### B. The Scoring Algorithm (0-100)

A deterministic formula to rank files.
$$Score = 100 - (10 \times \text{Errors}) - (5 \times \text{Warnings}) - (20 \times \text{SizeExcess}) + (15 \times \text{MultiStage})$$

**Usage:**

  * **Filter:** Discard files with Score \< 20 (Trash) or Score \> 90 (Already perfect).
  * **Selection:** Pick the "Middle 50%" to be fixed by the Teacher.

-----

## 4\. Phase III: Synthetic Data Generation (The Teacher)

We cannot train on raw GitHub files. We must create **Paired Data** (`Input` -\> `Ideal`).

### Strategy A: The "Repair" Loop (Primary)

Use a Teacher LLM to fix the "Middle 50%" of files.

  * **System Prompt:** Inject `docker_best_practices.md`.
  * **User Prompt:**
    ```text
    INPUT CONTEXT:
    - Lint Errors: DL3003, DL3008
    - Current Size: 800MB

    RAW FILE:
    [Insert Code]

    TASK:
    Rewrite this file to fix all lint errors and reduce size using multi-stage builds.
    ```
  * **Output:** The "Golden" Dockerfile.

### Strategy B: The "Corruption" Loop (Secondary)

Use the top 10% of "Perfect" files found in the wild.

  * **Action:** Write a script to *break* them (Flatten stages, unpin versions, add `sudo`).
  * **Pair:** `Input` (Corrupted) -\> `Output` (Original Perfect).

-----

## 5\. Phase IV: Fine-Tuning (The Student)

Training the Qwen2.5-Coder-3B model.

### Training Config (Unsloth)

  * **Framework:** Unsloth (Fastest for Llama/Qwen).
  * **Quantization:** 4-bit (QLoRA).
  * **Rank (LoRA r):** 32 or 64 (Higher is better for code logic).
  * **Context Window:** 4096 or 8192 tokens.

### Data Format (JSONL)

The prompt structure must be explicit to teach the model to use the metadata.

```json
{
  "instruction": "You are a Docker Expert. Optimize the following file based on the analysis report. Fix all security issues and minimize image size.",
  "input": "ANALYSIS REPORT:\n- Severity: High\n- Detected Smells: User is Root (DL3002), Apt-get lists not deleted (DL3009)\n- Size Context: Current image is 1.2GB (Target: <300MB)\n\nRAW DOCKERFILE:\nFROM ubuntu:latest\nRUN apt-get update && apt-get install nodejs\n...",
  "output": "FROM node:18-alpine AS builder\nWORKDIR /app\n..."
}
```

-----

## 6\. Phase V: RLHF / DPO (The Expert Polish)

This creates the "Super Expert" behavior.

1.  **Generate:** The SFT model generates 2 variants for a bad file.
      * *Variant A:* Uses `alpine`. (Builds: 150MB)
      * *Variant B:* Uses `ubuntu`. (Builds: 600MB)
2.  **Evaluate:** The script builds both. Variant A wins.
3.  **Train:** Feed this pair into the DPO Trainer.
      * *Chosen:* Variant A
      * *Rejected:* Variant B
4.  **Outcome:** The model learns that "Alpine = Good" without us explicitly writing a rule for it; it learns from the *outcome*.

-----

## 7\. Execution Roadmap (Next Steps)

1.  **Environment Setup:**
      * Install `hadolint`, `docker`, `python`, `unsloth`.
      * Get API Key for Teacher LLM (OpenAI/Anthropic).
2.  **Data Curation (Week 1):**
      * Run Analyzer on 7k files.
      * Filter top 1k candidates.
      * Run Teacher Loop to generate 1k "Golden" pairs.
3.  **Training V1 (Week 2):**
      * Train SFT Model.
      * Evaluate on a held-out test set (does it hallucinate commands?).
4.  **Evaluation Loop (Week 3):**
      * Build the outputs of V1.
      * Calculate real improvement stats (Avg size reduction %).
5.  **DPO Iteration (Week 4):**
      * (Optional) If V1 plateaus, run the DPO loop.

### Final Deliverable

A Python tool where you drop a Dockerfile, and it returns:

1.  **The Optimization Report** (What was wrong).
2.  **The New Dockerfile** (The code).
3.  **Projected Savings** (e.g., "Estimated size reduction: 60%").
