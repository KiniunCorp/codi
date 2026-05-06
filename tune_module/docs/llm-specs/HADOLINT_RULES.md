# Hadolint Rules (Extended)

Based on our project's "Constitution" and standard security benchmarks (CIS), here is the prioritized list of **Hadolint Rules**.

I have categorized them by **Importance Level** so you can assign weights in your scoring script (e.g., Critical = -15 points, Warning = -5 points).

### 🚨 Level 1: CRITICAL (Security & Stability)

*These violations must be fixed immediately. They represent security holes or unbuildable/unstable images.*

| Rule ID | Name | Why it matters | Score Penalty |
| :--- | :--- | :--- | :--- |
| **DL3002** | **Last USER is root** | Running as root is the \#1 security risk in containers. | **-20** |
| **DL3007** | **Using `latest` tag** | `FROM node:latest` is mutable. Builds will break randomly when the upstream image changes. | **-15** |
| **DL3006** | **Untagged Image** | `FROM node` is implicit and dangerous. Always be explicit. | **-15** |
| **DL3020** | **Use COPY instead of ADD** | `ADD` can fetch remote URLs and unpack zips automatically, creating unpredictable behaviors. | **-10** |
| **DL3026** | **Use trusted registry** | If you set a trusted registry (e.g., your private repo) and pull from Docker Hub, this flags it. | **-10** |
| **DL4006** | **SHELL pipefail** | `RUN wget | bash` is dangerous. If `wget` fails but `bash` runs, the build might silently succeed with a broken state. | **-10** |

-----

### ⚠️ Level 2: WARNING (Performance & Size)

*These make your image fat, slow to build, or harder to debug. Crucial for the "Optimization" aspect of your tool.*

| Rule ID | Name | Why it matters | Score Penalty |
| :--- | :--- | :--- | :--- |
| **DL3009** | **Delete apt-get lists** | `apt-get update` fetches \~40MB of data. If you don't `rm -rf /var/lib/apt/lists/*` in the *same* layer, that dead weight is baked in forever. | **-10** |
| **DL3015** | **No install recommends** | Ubuntu installs "recommended" packages by default (e.g., docs, x11 libs). Disabling this saves \~30-50% size. | **-5** |
| **DL3008** | **Pin apt versions** | `apt-get install nginx` is bad. Use `nginx=1.19.*`. Prevents "it worked on my machine" bugs. | **-5** |
| **DL3018** | **Pin apk versions** | Same as above, but for Alpine (`apk add nodejs=18.x`). | **-5** |
| **DL3013** | **Pin pip versions** | `pip install flask` breaks when Flask updates. Use `flask==2.0.1`. | **-5** |
| **DL3059** | **Consolidate RUN** | Multiple `RUN` instructions create multiple layers. Combining them (`&&`) reduces filesystem overhead. | **-5** |

-----

### ℹ️ Level 3: INFO (Style & Best Practice)

*These affect readability and maintainability but won't break the build.*

| Rule ID | Name | Why it matters | Score Penalty |
| :--- | :--- | :--- | :--- |
| **DL3003** | **Use WORKDIR** | Don't use `RUN cd /app`. It is flaky because `cd` only affects the current layer. `WORKDIR` persists. | **-2** |
| **DL3000** | **Absolute WORKDIR** | `WORKDIR app` is ambiguous. Use `WORKDIR /app`. | **-1** |
| **DL3045** | **COPY to relative path** | `COPY . .` is better than `COPY . /app` if `WORKDIR` is already set. | **-1** |
| **DL3025** | **JSON CMD/ENTRYPOINT** | Use `CMD ["node", "app.js"]` (exec form) to ensure signals (Ctrl+C) pass correctly to the process. | **-2** |

-----

### 🛠️ How to Implement This in `scorer.py`

You can map these lists directly into your Python scoring logic:

```python
CRITICAL_RULES = ["DL3002", "DL3007", "DL3006", "DL3020", "DL4006"]
WARNING_RULES  = ["DL3009", "DL3015", "DL3008", "DL3018", "DL3013", "DL3059"]

def get_hadolint_penalty(rule_id):
    if rule_id in CRITICAL_RULES:
        return 15
    elif rule_id in WARNING_RULES:
        return 5
    return 1 # Default penalty for Info/Style
```