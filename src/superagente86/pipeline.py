from __future__ import annotations

import datetime as dt
import json
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
        state = self._load_state(state_file)
        now = dt.datetime.now(self._resolve_timezone(self._app_config.schedule.timezone))
        window_start, window_end = self._compute_window(
            now, self._app_config.schedule.times
        )

        messages = self._gmail.fetch_messages(
            label=label or self._app_config.label,
            max_results=max_messages or self._app_config.max_messages,
            after_ts=window_start,
            before_ts=window_end,
        )

        report = self._analysis.analyze(
            messages, include_exec_summary=self._app_config.report.include_exec_summary
        )

        # Review content before creating document
        review_feedback = None
        if self._review.enabled:
            content_preview = self._delivery._render_report(report)
            review_feedback = self._review.review_document_text(content_preview)
            print(f"\n📋 DOCUMENT REVIEW:")
            print(f"   Quality: {'✅ Good' if review_feedback.is_good else '⚠️ Needs improvement'}")
            if review_feedback.issues:
                print(f"   Issues detected:")
                for issue in review_feedback.issues:
                    print(f"      - {issue}")
            if review_feedback.suggestions:
                print(f"   Suggestions:")
                for suggestion in review_feedback.suggestions:
                    print(f"      - {suggestion}")
            print(f"   Summary: {review_feedback.summary}")
            print()

        doc_id = None
        shortcut_path = None
        if not dry_run:
            doc_id = self._delivery.create_report_doc(report, title_prefix=title_prefix)

            # Mark processed emails as read
            message_ids = [m.message_id for m in messages]
            if message_ids:
                try:
                    self._gmail.mark_as_read(message_ids)
                    print(f"   ✅ Marked {len(message_ids)} emails as read")
                except Exception as e:
                    print(f"   ⚠️ Could not mark emails as read: {e}")

            if self._app_config.shortcut.enabled and doc_id:
                shortcut_path = self._delivery.create_doc_shortcut(
                    doc_id, self._app_config.shortcut
                )

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
        times = [Pipeline._parse_time(value) for value in schedule_times]
        times.sort()

        today = now.date()
        scheduled_today = [dt.datetime.combine(today, t, tzinfo=now.tzinfo) for t in times]
        latest = None
        for scheduled in scheduled_today:
            if scheduled <= now:
                latest = scheduled
        if latest is None:
            latest = dt.datetime.combine(
                today - dt.timedelta(days=1), times[-1], tzinfo=now.tzinfo
            )

        previous = None
        for scheduled in scheduled_today:
            if scheduled < latest:
                previous = scheduled
        if previous is None:
            previous = dt.datetime.combine(
                today - dt.timedelta(days=1), times[-1], tzinfo=now.tzinfo
            )

        return previous, latest

    @staticmethod
    def _parse_time(value: str) -> dt.time:
        return dt.datetime.strptime(value, "%H:%M").time()
