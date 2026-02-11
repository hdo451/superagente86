# Superagente86 - Copilot Instructions

## Project Overview
Python newsletter processing pipeline. Reads AI/tech newsletters from Gmail, extracts news with Gemini, creates Google Docs table reports.

## Tech Stack
- Python 3.13, virtual environment at `.venv/`
- Google APIs: Gmail (readonly), Google Docs
- Gemini API: gemini-2.5-flash (free tier, 20 req/day)
- macOS launchd for scheduling

## Architecture
- `src/superagente86/gmail_agent.py` - Fetches emails from Gmail by label
- `src/superagente86/analysis_agent.py` - Gemini extracts news items as structured JSON
- `src/superagente86/review_agent.py` - Gemini reviews headline+summary coherence
- `src/superagente86/delivery_agent.py` - Creates Google Docs with real 3-column table (HEADLINE, SUMMARY, SOURCE)
- `src/superagente86/pipeline.py` - Orchestrates the full flow
- `src/superagente86/cli.py` - CLI entry point
- `config.yaml` - App configuration
- `.env` - API keys and credential paths

## Key Constraints
- Gemini free tier: 20 requests/day per model. Use retries wisely.
- Gmail scope is readonly - cannot modify emails.
- All output must be in English.
- Table must be a REAL Google Docs table (insertTable API), not tab-separated text.
- Insert table cell text in REVERSE order to avoid index shifting.

## Running
```
source .venv/bin/activate
python -m superagente86.cli --config config.yaml
```

## Scheduling
```
./install_schedule.sh  # Installs launchd for 08:30 & 13:30 daily
```
