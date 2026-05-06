# 🗺️ Project Roadmap

## Phase 1: The Foundation
- [ ] Create `analyzer.py` implementing `DATA_PIPELINE.md`.
- [ ] Run analysis on the 7k scraped files.
- [ ] Generate `leaderboard.json` (Ranked files).

## Phase 2: Dataset Creation
- [ ] Select top 1,000 candidates (Score 30-80).
- [ ] Implement the "Teacher Loop" (API calls to GPT-4o with `DOCKER_CONSTITUTION.md`).
- [ ] Validate Teacher outputs (Do they build? Is the score higher?).
- [ ] Save to `train_dataset.jsonl`.

## Phase 3: Fine-Tuning
- [ ] Setup Unsloth environment.
- [ ] Load `train_dataset.jsonl`.
- [ ] Train Qwen2.5-Coder-3B (LoRA r=32).
- [ ] Export merged model (GGUF/Safetensors).

## Phase 4: Validation
- [ ] Run the new model on a "Held Out" set of 50 bad files.
- [ ] Measure average improvement:
    - [ ] Size reduction %.
    - [ ] Lint score increase.