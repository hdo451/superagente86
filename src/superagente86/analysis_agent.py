from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, List

from .gmail_agent import GmailMessage


@dataclass
@dataclass
class ReportSource:
    sender: str
    received_at: dt.datetime
    email_link: str
    extracted_links: List[str]
    summary_es: str
    summary_en: str


@dataclass
class ReportItem:
    topic: str
    tags: List[str]
    priority: str
    summary_es: str
    summary_en: str
    sources: List[ReportSource]


@dataclass
class Report:
    generated_at: dt.datetime
    executive_summary_es: str
    executive_summary_en: str
    items: List[ReportItem]


class AnalysisAgent:
    def analyze(self, messages: List[GmailMessage], include_exec_summary: bool) -> Report:
        grouped = self._group_by_topic(messages)
        items = [self._build_item(topic, items) for topic, items in grouped.items()]
        exec_es, exec_en = (
            self._build_exec_summary(items) if include_exec_summary else ("", "")
        )
        return Report(
            generated_at=dt.datetime.now(dt.timezone.utc),
            executive_summary_es=exec_es,
            executive_summary_en=exec_en,
            items=items,
        )

    def _group_by_topic(self, messages: List[GmailMessage]) -> Dict[str, List[GmailMessage]]:
        grouped: Dict[str, List[GmailMessage]] = {}
        for message in messages:
            topic = self._normalize_topic(message.subject)
            grouped.setdefault(topic, []).append(message)
        for topic in grouped:
            grouped[topic].sort(key=lambda m: m.received_at, reverse=True)
        return grouped

    def _normalize_topic(self, subject: str) -> str:
        normalized = subject.strip().lower()
        for prefix in ("re:", "fw:", "fwd:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip()
        return " ".join(normalized.split()) or "(no subject)"

    def _build_item(self, topic: str, messages: List[GmailMessage]) -> ReportItem:
        tags = self._extract_tags(messages)
        priority = self._score_priority(tags)
        primary = messages[0]
        summary_es = self._summarize(primary)
        summary_en = self._summarize(primary)
        sources = [self._build_source(message) for message in messages]
        return ReportItem(
            topic=topic,
            summary_es=summary_es,
            summary_en=summary_en,
            tags=tags,
            priority=priority,
            sources=sources,
        )

    def _build_source(self, message: GmailMessage) -> ReportSource:
        summary_es = self._summarize(message)
        summary_en = self._summarize(message)
        return ReportSource(
            sender=message.sender,
            received_at=message.received_at,
            email_link=message.link,
            extracted_links=message.links,
            summary_es=summary_es,
            summary_en=summary_en,
        )

    def _extract_tags(self, messages: List[GmailMessage]) -> List[str]:
        text = " ".join(
            f"{message.subject} {message.snippet}" for message in messages
        ).lower()
        tags = []
        if "ai" in text or "ml" in text:
            tags.append("ai")
        if "product" in text:
            tags.append("product")
        if "funding" in text or "series" in text:
            tags.append("funding")
        if not tags:
            tags.append("general")
        return tags

    def _score_priority(self, tags: List[str]) -> str:
        if "funding" in tags:
            return "high"
        if "ai" in tags:
            return "medium"
        return "low"

    def _summarize(self, message: GmailMessage) -> str:
        text = message.body_text.strip()
        if not text:
            text = message.snippet
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        preview = ". ".join(sentences[:2])
        if preview:
            return preview + "."
        return message.snippet

    def _build_exec_summary(self, items: List[ReportItem]) -> tuple[str, str]:
        if not items:
            return "Sin novedades relevantes.", "No relevant updates."
        high = sum(1 for item in items if item.priority == "high")
        medium = sum(1 for item in items if item.priority == "medium")
        low = sum(1 for item in items if item.priority == "low")
        es = f"Resumen rapido: {high} alta, {medium} media, {low} baja prioridad."
        en = f"Quick summary: {high} high, {medium} medium, {low} low priority."
        return es, en
