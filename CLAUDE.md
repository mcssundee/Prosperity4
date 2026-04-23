# Prosperity 4 — Global Rules

## Project Overview
IMC Prosperity 4 trading competition. 5 rounds total. Each round:
- **Algo section**: submit a single `trader.py` file with a `Trader` class and `run()` method
- **Manual section**: human decisions supported by tooling in `rounds/roundX/manual/`

## Submission Process
1. Develop strategy in `rounds/roundX/algo/trader.py`
2. Merge any shared modules from `strategies/` directly into that file (no imports allowed)
3. Copy final file to root `trader.py` before submitting
4. Commit and tag: `git tag round1-submission`

## Coding Rules (Algo)
- No external libraries in `trader.py` — only Python stdlib + the official datamodel
- All strategy logic as classes; `Trader.run()` is the entry point
- Never modify `data/raw/` — derive all processed files separately
- Keep `strategies/` modules importable and testable independently

## Git Workflow
- `main` branch = submitted versions only
- `dev` branch = active development
- Commit at meaningful checkpoints (before submission, after backtesting a new idea)
- Push to GitHub after every commit: `git push origin dev`

## Per-Round Context
Each round has its own `CLAUDE.md` in `rounds/roundX/`. That file contains:
- New products introduced and their mechanics
- Position limits per product
- Rule changes from previous round
- Which strategies from `strategies/` are active this round

## Backtesting
Run: `python backtesting/backtester.py --round 1`
Data lives in `data/raw/round1/` — never overwrite it.
