from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from .config import load_app_config, load_google_config
from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run newsletter pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--label", default=None, help="Override Gmail label")
    parser.add_argument("--max-messages", type=int, default=None)
    parser.add_argument("--state-file", default="data/state.json")
    parser.add_argument("--title-prefix", default="Newsletter Report")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    app_config = load_app_config(args.config)
    google_config = load_google_config()

    pipeline = Pipeline(app_config, google_config)
    result = pipeline.run(
        state_file=Path(args.state_file),
        label=args.label,
        max_messages=args.max_messages,
        title_prefix=args.title_prefix,
        dry_run=args.dry_run,
    )

    if result.get("doc_id"):
        print(f"Created doc: {result['doc_id']}")
    else:
        print("Dry run complete. No doc created.")


if __name__ == "__main__":
    main()
