# 📊 Data Pipeline Specification

## 1. Input Processing (`analyzer.py`)
This script processes the raw 7k scraped files.

**Requirements:**
1.  **Lint:** Run `subprocess.run(['hadolint', '-f', 'json', file])`.
2.  **Build:** Run `docker build` (with timeout=300s).
3.  **Metric Extraction:**
    * `metrics['size']`: Image size in MB.
    * `metrics['layers']`: Count of layers.
    * `metrics['smells']`: List of Hadolint error codes.

## 2. Scoring Logic (`scorer.py`)
Input: Hadolint JSON + Build Stats.
Output: Integer (0-100).

**Algorithm:**
```python
def calculate_score(stats):
    score = 100
    # Penalties
    score -= (len(stats['errors']) * 10)
    score -= (len(stats['warnings']) * 5)
    
    if stats['size_mb'] > 1000: score -= 30
    elif stats['size_mb'] > 500: score -= 15
    
    if "USER" not in content: score -= 20
    
    # Bonuses
    if "AS builder" in content: score += 20
    
    return max(0, score)
```

## 3. Data Strategy
* Trash: Score < 20 (Too broken to learn from).
* Gold: Score > 90 (Keep for "Corruption" strategy).
* Training Candidates: Score 30-80 (The "Fixable" range).

