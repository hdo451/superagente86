from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .gmail_agent import GmailMessage


@dataclass
class ReportSource:
    sender: str
    received_at: dt.datetime
    email_link: str
    extracted_links: List[str]
    summary: str
    prompt_of_day: Optional[str] = None
    video_links: List[str] = field(default_factory=list)
    app_mentions: List[str] = field(default_factory=list)
    company_news: List[str] = field(default_factory=list)


@dataclass
class ReportItem:
    topic: str
    tags: List[str]
    priority: str
    summary: str
    sources: List[ReportSource]
    has_prompt: bool = False
    has_video: bool = False
    has_company_news: bool = False


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
        sources = [self._build_source(message) for message in messages]
        
        # Check for special content
        has_prompt = any(s.prompt_of_day for s in sources)
        has_video = any(s.video_links for s in sources)
        has_company_news = any(s.company_news for s in sources)
        
        # Adjust priority based on content
        if has_company_news:
            tags.append("company")
        if has_prompt:
            tags.append("prompt")
        if has_video:
            tags.append("video")
        
        priority = self._score_priority(tags, has_company_news)
        primary = messages[0]
        summary = self._summarize(primary, priority)
        
        return ReportItem(
            topic=topic,
            summary=summary,
            tags=list(set(tags)),
            priority=priority,
            sources=sources,
            has_prompt=has_prompt,
            has_video=has_video,
            has_company_news=has_company_news,
        )

    def _build_source(self, message: GmailMessage) -> ReportSource:
        text = message.body_text or message.snippet
        
        # Extract prompt of the day
        prompt = self._extract_prompt(text)
        
        # Detect video links
        video_links = self._extract_video_links(message.links)
        
        # Detect app mentions vs company news
        app_mentions = self._extract_app_mentions(text)
        company_news = self._extract_company_news(text)
        
        summary = self._summarize_source(message)
        
        return ReportSource(
            sender=message.sender,
            received_at=message.received_at,
            email_link=message.link,
            extracted_links=[l for l in message.links if l not in video_links],
            summary=summary,
            prompt_of_day=prompt,
            video_links=video_links,
            app_mentions=app_mentions,
            company_news=company_news,
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

    def _score_priority(self, tags: List[str], has_company_news: bool = False) -> str:
        if "funding" in tags or has_company_news:
            return "high"
        if "ai" in tags or "company" in tags:
            return "medium"
        return "low"

    def _summarize(self, message: GmailMessage, priority: str) -> str:
        text = message.body_text.strip() if message.body_text else message.snippet
        text = self._clean_text(text)
        
        # More words for important news
        word_limit = 50 if priority == "high" else 30
        words = text.split()
        if len(words) > word_limit:
            return " ".join(words[:word_limit]) + "..."
        return text

    def _summarize_source(self, message: GmailMessage) -> str:
        text = message.body_text.strip() if message.body_text else message.snippet
        text = self._clean_text(text)
        words = text.split()
        if len(words) > 40:
            return " ".join(words[:40]) + "..."
        return text

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\r\n]+", " ", text)
        return text.strip()

    def _extract_prompt(self, text: str) -> Optional[str]:
        patterns = [
            r"prompt\s*(?:of\s*the\s*)?day[:\s]*([^\n]{10,500})",
            r"daily\s*prompt[:\s]*([^\n]{10,500})",
            r"today'?s?\s*prompt[:\s]*([^\n]{10,500})",
            r"prompt:\s*([^\n]{10,500})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_video_links(self, links: List[str]) -> List[str]:
        video_domains = ["youtube.com", "youtu.be", "vimeo.com", "loom.com", "wistia.com"]
        return [l for l in links if any(d in l.lower() for d in video_domains)]

    def _extract_app_mentions(self, text: str) -> List[str]:
        patterns = [
            r"(?:try|check out|download|use)\s+([A-Z][a-zA-Z0-9]+)",
            r"app[:\s]+([A-Z][a-zA-Z0-9]+)",
            r"tool[:\s]+([A-Z][a-zA-Z0-9]+)",
        ]
        apps = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            apps.extend(matches)
        return list(set(apps))[:5]

    def _extract_company_news(self, text: str) -> List[str]:
        keywords = [
            r"(\w+)\s+(?:announced|launches|raised|acquired|partnership|IPO|valuation)",
            r"(?:announced|launches|raised|acquired)\s+(?:by\s+)?(\w+)",
            r"(OpenAI|Google|Microsoft|Meta|Apple|Amazon|Anthropic|Nvidia|Tesla)[^.]{0,100}(?:announced|launch|partner|acqui|fund|invest)",
        ]
        news = []
        for pattern in keywords:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                for m in matches:
                    if isinstance(m, tuple):
                        news.extend([x for x in m if x])
                    else:
                        news.append(m)
        return list(set(news))[:5]

    def _build_exec_summary(self, items: List[ReportItem]) -> tuple[str, str]:
        if not items:
            return "Sin novedades relevantes.", "No relevant updates."
        high = sum(1 for item in items if item.priority == "high")
        medium = sum(1 for item in items if item.priority == "medium")
        low = sum(1 for item in items if item.priority == "low")
        es = f"Resumen rapido: {high} alta, {medium} media, {low} baja prioridad."
        en = f"Quick summary: {high} high, {medium} medium, {low} low priority."
        return es, en
