from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from zoneinfo import ZoneInfo

from .analysis_agent import AnalysisAgent
from .config import AppConfig, GoogleConfig
from .delivery_agent import DeliveryAgent
from .gmail_agent import GmailAgent
from .review_agent import ReviewAgent, ReviewFeedback


class Pipeline:
    def __init__(self, app_config: AppConfig, google_config: GoogleConfig) -> None:
        self._app_config = app_config
        self._google_config = google_config
        self._analysis = AnalysisAgent()
        self._review = ReviewAgent(api_key=os.getenv("GEMINI_API_KEY"))
        
        # Setup logging
        self._logger = logging.getLogger(__name__)
        
        # Combine all scopes for unified auth
        combined_scopes = list(set(google_config.gmail_scopes + google_config.docs_scopes))
        
        self._gmail = GmailAgent(
            credentials_path=google_config.credentials_path,
            token_path=google_config.token_path,
            scopes=combined_scopes,
        )
        self._delivery = DeliveryAgent(
            credentials_path=google_config.credentials_path,
            token_path=google_config.token_path,
            scopes=combined_scopes,
        )

    def run(
        self,
        state_file: Path,
        label: Optional[str] = None,
        max_messages: Optional[int] = None,
        title_prefix: str = "Newsletter Report",
        dry_run: bool = False,
    ) -> dict:
        self._logger.info("=" * 60)
        self._logger.info("🚀 Pipeline started")
        
        state = self._load_state(state_file)
        
        # Get current time in UTC for consistency with Gmail API
        now_utc = dt.datetime.now(dt.timezone.utc)
        tz = self._resolve_timezone(self._app_config.schedule.timezone)
        now_local = now_utc.astimezone(tz)
        
        # Determine the search window:
        # - First run: compute from schedule
        # - Subsequent runs: use saved window, extend end to now
        if "window_end" in state and state["window_end"]:
            try:
                window_end_saved = dt.datetime.fromisoformat(state["window_end"])
                window_start_saved = dt.datetime.fromisoformat(state["window_start"])
                
                # Check if we've moved past the saved window end (next scheduled execution)
                if now_utc >= window_end_saved:
                    # We've passed to the next execution slot, compute new window
                    self._logger.info("Advanced to next scheduled window")
                    window_start_local, window_end_local = self._compute_window(now_local, self._app_config.schedule.times)
                    window_start = window_start_local.astimezone(dt.timezone.utc)
                    window_end = window_end_local.astimezone(dt.timezone.utc)
                else:
                    # Still in current window, search from start to now
                    window_start = window_start_saved
                    window_end = now_utc
                    self._logger.info("Continuing current scheduled window")
            except Exception as e:
                self._logger.warning(f"Could not parse saved window: {e}, recomputing")
                window_start_local, window_end_local = self._compute_window(now_local, self._app_config.schedule.times)
                window_start = window_start_local.astimezone(dt.timezone.utc)
                window_end = window_end_local.astimezone(dt.timezone.utc)
        else:
            self._logger.info("First run, computing initial window from schedule")
            window_start_local, window_end_local = self._compute_window(now_local, self._app_config.schedule.times)
            window_start = window_start_local.astimezone(dt.timezone.utc)
            window_end = window_end_local.astimezone(dt.timezone.utc)
        
        self._logger.info(f"Search window: {window_start.isoformat()} to {window_end.isoformat()}")

        messages = self._gmail.fetch_messages(
            label=label or self._app_config.label,
            max_results=max_messages or self._app_config.max_messages,
            after_ts=window_start,
            before_ts=window_end,
        )
        self._logger.info(f"✉️ Fetched {len(messages)} emails from '{self._app_config.label}'")

        report = self._analysis.analyze(
            messages, include_exec_summary=self._app_config.report.include_exec_summary
        )
        self._logger.info(f"📊 Analyzed {len(report.items)} news items")

        # Review content before creating document
        review_feedback = None
        doc_id = None
        shortcut_path = None

        if not report.items:
            self._logger.info("No news items found; skipping review and document creation")
        elif self._review.enabled:
            content_preview = self._delivery._render_report(report)
            review_feedback = self._review.review_document_text(content_preview)
            self._logger.info(f"📋 Document review: {'✅ PASS' if review_feedback.is_good else '❌ FAIL'}")

            if not review_feedback.is_good:
                self._logger.warning(f"Review issues: {review_feedback.issues}")
                self._logger.warning(f"Suggestions: {review_feedback.suggestions}")
                self._logger.warning(f"Summary: {review_feedback.summary}")
                self._logger.error("Document creation SKIPPED due to review failure")
            else:
                if review_feedback.issues:
                    self._logger.info(f"Minor issues detected: {review_feedback.issues}")
                if review_feedback.suggestions:
                    self._logger.info(f"Suggestions: {review_feedback.suggestions}")
                self._logger.info(f"Summary: {review_feedback.summary}")
        else:
            self._logger.info("Review disabled (no API key configured)")

        # Only create document if review passed or is disabled
        if not report.items:
            self._logger.info("Document creation skipped: no news items")
        elif not dry_run and (not self._review.enabled or review_feedback.is_good):
            try:
                doc_id = self._delivery.create_report_doc(report, title_prefix=title_prefix)
                self._logger.info(f"📄 Document created: {doc_id}")

                # Mark processed emails as read
                message_ids = [m.message_id for m in messages]
                if message_ids:
                    try:
                        self._gmail.mark_as_read(message_ids)
                        self._logger.info(f"✅ Marked {len(message_ids)} emails as read")
                    except Exception as e:
                        self._logger.warning(f"Could not mark emails as read: {e}")

                if self._app_config.shortcut.enabled and doc_id:
                    shortcut_path = self._delivery.create_doc_shortcut(
                        doc_id, self._app_config.shortcut
                    )
                    self._logger.info(f"🔗 Shortcut created: {shortcut_path}")
            except Exception as e:
                self._logger.error(f"Document creation failed: {e}", exc_info=True)
                doc_id = None
        elif dry_run:
            self._logger.info("DRY RUN: Document creation skipped")
        else:
            self._logger.warning("Document creation SKIPPED: Review did not pass")

        state["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat()
        state["window_start"] = window_start.isoformat()
        state["window_end"] = window_end.isoformat()
        state["last_doc_id"] = doc_id
        state["last_count"] = len(messages)
        if review_feedback:
            state["last_review"] = {
                "is_good": review_feedback.is_good,
                "issues": review_feedback.issues,
                "suggestions": review_feedback.suggestions,
                "summary": review_feedback.summary,
            }
        self._save_state(state_file, state)
        self._logger.info("State saved")
        self._logger.info("=" * 60)

        return {
            "doc_id": doc_id,
            "shortcut_path": str(shortcut_path) if shortcut_path else None,
            "items": len(messages),
            "review": review_feedback,
            "state": state,
        }

    @staticmethod
    def _load_state(state_file: Path) -> dict:
        if not state_file.exists():
            return {}
        return json.loads(state_file.read_text(encoding="utf-8"))

    @staticmethod
    def _save_state(state_file: Path, state: dict) -> None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> dt.tzinfo:
        if not timezone_name or timezone_name.lower() == "local":
            return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc

    @staticmethod
    def _compute_window(
        now: dt.datetime, schedule_times: List[str]
    ) -> Tuple[dt.datetime, dt.datetime]:
        """Compute the search window based on scheduled times.
        
        Returns (start, end) tuple where:
        - start: the last scheduled execution time (before or equal to now)
        - end: the next scheduled execution time (after now)
        
        This ensures we capture all emails between consecutive scheduled runs.
        """
        times = [Pipeline._parse_time(value) for value in schedule_times]
        times.sort()

        today = now.date()
        
        # Find the most recent scheduled time (at or before now)
        latest = None
        for t in times:
            scheduled = dt.datetime.combine(today, t, tzinfo=now.tzinfo)
            if scheduled <= now:
                latest = scheduled
        
        # If no scheduled time today has passed, use yesterday's last time
        if latest is None:
            latest = dt.datetime.combine(
                today - dt.timedelta(days=1), times[-1], tzinfo=now.tzinfo
            )
        
        # Find the next scheduled time (after now)
        next_time = None
        for t in times:
            scheduled = dt.datetime.combine(today, t, tzinfo=now.tzinfo)
            if scheduled > now:
                next_time = scheduled
                break
        
        # If no scheduled time after now today, use tomorrow's first time
        if next_time is None:
            next_time = dt.datetime.combine(
                today + dt.timedelta(days=1), times[0], tzinfo=now.tzinfo
            )
        
        return latest, next_time

    @staticmethod
    def _parse_time(value: str) -> dt.time:
        return dt.datetime.strptime(value, "%H:%M").time()
