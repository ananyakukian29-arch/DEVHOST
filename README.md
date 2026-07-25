# Debt Radar 🎯

**Turns your codebase's silent complaints into a priority list.**

Debt Radar scans a repository and tells you *exactly* which files are the biggest technical debt risk — not by counting lint warnings, but by combining code smells with real git history to show where developers are already struggling.

---

## The Problem

Every team knows they have technical debt. Nobody can answer: **"What should we fix first?"**

- Linters flag hundreds of issues with no sense of priority.
- `TODO` and `FIXME` comments pile up and get ignored.
- Static analysis tools only look at the *code* — never at how often humans are actually fighting with it.

## The Solution

Debt Radar scans a repo and combines two signals nobody else combines:

1. **Static code smells** — `TODO`/`FIXME`/`HACK` comments, long functions, deep nesting, duplicated blocks
2. **Git commit history** — files with frequent bug-fix commits are riskier than files that never change

These are combined into an **Impact × Frequency-of-change** score, ranking files by real-world risk — not just theoretical code quality. An LLM then explains *why* each top-ranked file matters, in plain English.

> **Pitch line:** *Your codebase already told you what's broken — nobody was listening to git history.*

---

## How It Works

```
Repo path/zip
     │
     ▼
┌─────────────────┐     ┌──────────────────┐
│ Static Analyzer  │     │   Git Analyzer    │
│ (TODOs, smells)  │     │ (commit frequency)│
└────────┬─────────┘     └─────────┬─────────┘
         │                         │
         └───────────┬─────────────┘
                      ▼
              ┌───────────────┐
              │    Scorer      │  → Impact × Frequency
              └───────┬────────┘
                      ▼
              ┌───────────────┐
              │  LLM Narrator  │  → "Why this matters"
              └───────┬────────┘
                      ▼
              Ranked hotspot list
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Frontend | Streamlit |
| Analysis | Python (AST/regex, `git log --stat`) |
| Narration | LLM (via API) |

---

## Project Structure

```
backend/
├── main.py                    # FastAPI entrypoint
├── api/routes.py              # /scan, /report endpoints
├── services/scan_service.py   # orchestrates analyzers + scorer + LLM
├── core/
│   ├── static_analyzer.py     # TODO/FIXME finder, function length, nesting depth
│   ├── git_analyzer.py        # commit frequency per file
│   ├── scorer.py              # Impact × Frequency scoring
│   └── llm_client.py          # LLM narration wrapper
└── models/schemas.py          # Pydantic response models

frontend/
├── app.py                     # Streamlit entrypoint
├── api_client.py              # all HTTP calls to backend
└── components/
    ├── upload_panel.py
    ├── results_table.py
    └── explanation_card.py
```

---

## Getting Started

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

---

## API Contract

```python
class FileRisk(BaseModel):
    file_path: str
    score: float
    todo_count: int
    commit_frequency: int
    max_function_length: int
    explanation: str

class ScanResponse(BaseModel):
    repo_name: str
    ranked_files: list[FileRisk]
```

`POST /scan` — accepts a repo path or zip, returns a `ScanResponse` with files ranked by risk.

---

## Team

Built by a 3-person team with clear ownership boundaries:

- **Analysis Engine** — static analyzer, git analyzer, scoring logic
- **API + Orchestration** — FastAPI routes, LLM narration, schema contracts
- **Frontend** — Streamlit UI, results visualization

---

## Roadmap / Future Work

- Support for multiple languages beyond Python
- Trend view — risk score over time, not just a snapshot
- CI integration — flag new hotspots on every PR
- Team-level dashboard for tracking debt reduction over sprints
