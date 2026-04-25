# Prosperity 4

## Coding Rules
- No external libraries in `trader.py` — only Python stdlib + datamodel
- No imports: merge `strategies/` modules directly into `trader.py`
- Never modify `data/raw/` — derive separate files instead
- All logic in classes; `Trader.run()` is entry point


## Git Workflow
- `main` = submissions only; `dev` = active development
- Commit meaningfully; push after every commit: `git push origin dev`

## Round-Specific Info
See `rounds/roundX/CLAUDE.md` for products, limits, rule changes, and active strategies.
