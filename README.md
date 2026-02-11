# Superagente86

Python pipeline that reads AI/tech newsletters from Gmail (label `newsletters`), extracts individual news items using Gemini, deduplicates across sources, and creates a Google Doc with a structured table report twice a day.

## Features

- **Gemini-powered extraction**: Each newsletter is analyzed by Gemini to extract individual news stories with clear headlines and summaries in English.
- **Real Google Docs table**: 3-column table (HEADLINE, SUMMARY, SOURCE) with bold headers.
- **Source priority**: The Neuron > TLDR AI > The Rundown AI > Superhuman > TLDR. Higher-priority sources win when deduplicating.
- **Quality review**: Gemini reviews the report for coherence (headline must match summary).
- **Automatic scheduling**: Runs at 08:30 and 13:30 daily via macOS launchd.

## Requirements

- Python 3.10+
- Google OAuth credentials (Gmail API + Google Docs API enabled)
- Gemini API key

## Quick Setup

1. Create a virtual environment and install:

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

2. Copy `.env.example` to `.env` and set your paths and API keys.
3. Place `credentials.json` in the project root.
4. First run (generates `token.json`):

   ```
   python -m superagente86.cli --config config.yaml --dry-run
   ```

5. Normal run:

   ```
   python -m superagente86.cli --config config.yaml
   ```

## Automatic Scheduling

To install the automatic schedule (08:30 and 13:30 daily):

```
./install_schedule.sh
```

This creates a macOS launchd agent. Logs go to `logs/`.

To uninstall:
```
launchctl bootout gui/$(id -u)/com.superagente86.newsletter
```

## Configuration

- Gmail label: defined in `config.yaml` as `label: newsletters`
- Schedule: 08:30 and 13:30 (US/Pacific timezone)
- Each run uses a time window based on the schedule
- A new Google Doc is created per run
- Duplicate news across newsletters is deduplicated by headline similarity
- A desktop shortcut (.webloc) to the Google Doc is created automatically
