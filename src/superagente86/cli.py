from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import load_app_config, load_google_config
from .pipeline import Pipeline


def setup_logging(log_dir: Path = None) -> None:
    """Configure logging to file and console"""
    if log_dir is None:
        log_dir = Path(__file__).parent.parent.parent / "logs"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "newsletter.log"
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


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
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("Newsletter pipeline starting...")
    
    parser = build_parser()
    args = parser.parse_args()

    app_config = load_app_config(args.config)
    google_config = load_google_config()

    pipeline = Pipeline(app_config, google_config)
    try:
        result = pipeline.run(
            state_file=Path(args.state_file),
            label=args.label,
            max_messages=args.max_messages,
            title_prefix=args.title_prefix,
            dry_run=args.dry_run,
        )

        if result.get("doc_id"):
            logger.info(f"✅ SUCCESS: Created doc {result['doc_id']}")
        else:
            logger.warning("⚠️ No document created (dry run or review failed)")
        
        logger.info(f"Pipeline completed successfully. Items processed: {result.get('items', 0)}")
    except Exception as e:
        logger.error(f"❌ Pipeline failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
