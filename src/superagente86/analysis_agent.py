from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import google.generativeai as genai

from .gmail_agent import GmailMessage


@dataclass
class ReportItem:
    """A single news item extracted from a newsletter."""
    titular: str
    cuerpo: str
    fuente: str  # Newsletter name (e.g. "The Neuron", "TLDR AI")
    source_priority: int = 99  # Lower = higher priority


CATEGORIES = {
    "new_models": {"name_es": "🚀 NUEVOS MODELOS", "name_en": "New Models"},
    "research": {"name_es": "🔬 RESEARCH", "name_en": "Research"},
    "robots": {"name_es": "🤖 ROBOTS", "name_en": "Robots"},
    "funding": {"name_es": "💰 FUNDING & EMPRESAS", "name_en": "Funding & Companies"},
    "apps": {"name_es": "🛠️ APPS & TOOLS", "name_en": "Apps & Tools"},
    "general": {"name_es": "📰 GENERAL", "name_en": "General"},
}


@dataclass
class Report:
    generated_at: dt.datetime
    executive_summary: str
    items: List[ReportItem]


# Newsletter source priority (lower = processed first, items kept over duplicates)
SOURCE_PRIORITY = {
    "the neuron": 0,
    "tldr ai": 1,
    "the rundown ai": 2,
    "superhuman": 3,
    "tldr": 4,
}


class AnalysisAgent:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self._model_names = [
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-flash-latest",
            ]
        else:
            self._model_names = []

    def analyze(self, messages: List[GmailMessage], include_exec_summary: bool) -> Report:
        all_items: List[ReportItem] = []

        # Optimize: extract all news in a single API call if possible
        if self._model_names and messages:
            all_items = self._extract_all_news_items_batch(messages)
        
        if not all_items and messages:
            # Fallback to per-message extraction if batch fails
            for msg in messages:
                items = self._extract_news_items(msg)
                all_items.extend(items)

        # Sort by source priority (The Neuron first, then TLDR AI, etc.)
        all_items.sort(key=lambda x: x.source_priority)

        # Deduplicate: keep first occurrence (highest priority source)
        all_items = self._deduplicate(all_items)

        exec_summary = ""
        if include_exec_summary and all_items:
            sources = set(it.fuente for it in all_items)
            exec_summary = f"{len(all_items)} news items from {len(sources)} newsletters."

        return Report(
            generated_at=dt.datetime.now(dt.timezone.utc),
            executive_summary=exec_summary,
            items=all_items,
        )

    # ------------------------------------------------------------------
    # Gemini API with rate-limit retry
    # ------------------------------------------------------------------

    def _gemini_call(self, prompt: str, max_retries: int = 2):
        """Call Gemini with retry on rate limit errors."""
        last_error: Exception | None = None
        for model_name in self._model_names:
            for attempt in range(max_retries + 1):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    # Small delay between calls to avoid per-minute rate limits
                    time.sleep(2)
                    return response
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    # Try next model if this one is unavailable or has no quota
                    if "not found" in err_str or "limit: 0" in err_str or "Quota exceeded" in err_str:
                        break
                    if "429" in err_str and attempt < max_retries:
                        wait = 15 * (attempt + 1)
                        print(f"   ⏳ Rate limit on {model_name}, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    break
        if last_error:
            raise last_error
        raise RuntimeError("No Gemini models configured")

    # ------------------------------------------------------------------
    # Batch extraction (optimized: 1 request for all emails)
    # ------------------------------------------------------------------

    def _extract_all_news_items_batch(self, messages: List[GmailMessage]) -> List[ReportItem]:
        """Extract news from ALL newsletters in a single API call.
        This is 80% more efficient than per-message extraction."""
        
        if not messages:
            return []
        
        # Prepare all email content
        email_blocks = []
        for i, msg in enumerate(messages, 1):
            fuente = self._extract_source_name(msg.sender)
            # Prefer HTML (structured) over plain text
            body = msg.body_html or msg.body_text or msg.snippet or ""
            body = self._strip_footer(body)
            
            email_blocks.append(
                f"--- EMAIL {i}: {fuente} ---\n"
                f"Subject: {msg.subject}\n\n"
                f"Content:\n{body}\n"  # NO TRUNCATION
            )
        
        combined_content = "\n".join(email_blocks)
        
        prompt = (
            "You are an assistant that extracts individual news stories from tech/AI newsletters.\n"
            "Analyze the following BATCH of newsletter emails and extract EACH individual news story.\n"
            "For each story return:\n"
            '- "titular": short, clear headline in English (max 12 words)\n'
            '- "fuente": newsletter name (e.g., "The Neuron", "TLDR AI")\n'
            '- "cuerpo": summary in English, 1-3 sentences. Explain what happened, who is involved, and why it matters.\n\n'
            "EXTRACTION GUIDELINES:\n"
            "- Extract ALL individual news items from the content (aim for 10+ items if present).\n"
            "- Include items that are clearly identifiable news stories with a headline and descriptive text.\n"
            "- Summaries should be substantial but can be concise (even 15-20 words is acceptable).\n"
            "- Ignore ads, job offers, sponsor sections, footers, and promotional blocks.\n"
            "- The headline must relate to the body. If they don't match, skip that item.\n"
            "- Prioritize breadth: capture as many relevant news items as possible.\n"
            "- Return up to 100 items total across all newsletters.\n"
            "- Respond ONLY with a valid JSON array, no markdown or explanations.\n\n"
            f"Content:\n{combined_content}\n\n"  # NO TRUNCATION
            'Respond ONLY with JSON array: [{"titular": "...", "fuente": "...", "cuerpo": "..."}]'
        )
        
        try:
            response = self._gemini_call(prompt)
            raw = response.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                return []
        except Exception:
            return []
        
        items: List[ReportItem] = []
        for entry in parsed[:100]:  # Max 100 items across all newsletters
            titular = (entry.get("titular") or "").strip()
            fuente = (entry.get("fuente") or "").strip()
            cuerpo = (entry.get("cuerpo") or "").strip()
            
            if not titular or not fuente or not cuerpo or len(cuerpo) < 15:
                continue
            
            priority = self._get_source_priority(fuente)
            items.append(ReportItem(
                titular=titular,
                cuerpo=cuerpo,
                fuente=fuente,
                source_priority=priority,
            ))
        
        return items if items else []

    # ------------------------------------------------------------------
    # Gemini API with rate-limit retry
    # ------------------------------------------------------------------

    def _extract_news_items(self, message: GmailMessage) -> List[ReportItem]:
        """Use Gemini to extract individual news from a newsletter email."""
        fuente = self._extract_source_name(message.sender)
        priority = self._get_source_priority(fuente)

        # Prefer HTML (structured) over plain text
        body = message.body_html or message.body_text or message.snippet or ""
        body = self._strip_footer(body)

        if not self._model_names or len(body.strip()) < 50:
            return self._fallback_extract(message, fuente, priority)

        prompt = (
            "You are an assistant that extracts individual news stories from tech/AI newsletters.\n"
            "Analyze the following email and extract EACH individual news story.\n"
            "For each story return:\n"
            '- "titular": short, clear headline in English (max 12 words)\n'
            '- "cuerpo": summary in English, 1-3 sentences. Explain what happened, who is involved, and why it matters.\n\n'
            "EXTRACTION GUIDELINES:\n"
            "- Extract ALL individual news items from this newsletter (aim for 5-15+ items if present).\n"
            "- Include items that are clearly identifiable news stories with a headline and descriptive text.\n"
            "- Summaries should be substantial but can be concise (even 15-20 words is acceptable).\n"
            "- Ignore ads, job offers, sponsor sections, footers, memes, and promotional content.\n"
            "- The headline must relate to the body. If they don't match, skip that item.\n"
            "- Prioritize breadth: capture as many relevant news items as possible.\n"
            "- Return up to 50 items from this newsletter.\n"
            "- Respond ONLY with a valid JSON array, no markdown or explanations.\n\n"
            f"Newsletter: {fuente}\n"
            f"Subject: {message.subject}\n\n"
            f"Content:\n{body}\n\n"  # NO TRUNCATION - pass full content
            'Respond ONLY with JSON array: [{"titular": "...", "cuerpo": "..."}]'
        )

        try:
            response = self._gemini_call(prompt)
            raw = response.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                return self._fallback_extract(message, fuente, priority)
        except Exception:
            return self._fallback_extract(message, fuente, priority)

        items: List[ReportItem] = []
        for entry in parsed[:50]:  # Max 50 items per newsletter
            titular = (entry.get("titular") or "").strip()
            cuerpo = (entry.get("cuerpo") or "").strip()
            if not titular or not cuerpo or len(cuerpo) < 15:
                continue

            items.append(ReportItem(
                titular=titular,
                cuerpo=cuerpo,
                fuente=fuente,
                source_priority=priority,
            ))

        return items if items else self._fallback_extract(message, fuente, priority)

    def _fallback_extract(self, message: GmailMessage, fuente: str, priority: int) -> List[ReportItem]:
        """Regex-based fallback when Gemini is unavailable."""
        subject = message.subject.strip()
        subject = re.sub(r'^[^\w]*', '', subject).strip()
        subject = subject[:80] if len(subject) > 80 else subject

        body = message.body_text or message.snippet or ""
        body = self._strip_footer(body)
        body = re.sub(r'https?://\S+', '', body)
        body = re.sub(r'[\u200b\u200c\u200d\u2060\ufeff\u00ad]+', '', body)
        body = re.sub(r'\s+', ' ', body).strip()
        cuerpo = body[:300].strip()
        if len(cuerpo) < 20:
            cuerpo = f"Newsletter from {fuente}: {subject}"

        return [ReportItem(
            titular=subject,
            cuerpo=cuerpo,
            fuente=fuente,
            source_priority=priority,
        )]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _deduplicate(self, items: List[ReportItem]) -> List[ReportItem]:
        """Merge duplicate news across newsletters. Items are pre-sorted by priority.
        When a duplicate is found, its source name is appended to the existing item's fuente."""
        unique: List[ReportItem] = []
        seen_keys: List[set] = []

        stopwords = {
            "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are",
            "de", "la", "el", "en", "con", "por", "que", "un", "una", "los", "las",
            "su", "del", "al", "se", "no", "es", "lo", "como", "más", "ya",
        }

        for item in items:
            words = set(
                w for w in re.findall(r'\w+', item.titular.lower())
                if w not in stopwords and len(w) > 2
            )
            if not words:
                unique.append(item)
                seen_keys.append(words)
                continue

            dup_index = -1
            for idx, seen in enumerate(seen_keys):
                if not seen:
                    continue
                common = words & seen
                ratio = len(common) / min(len(words), len(seen)) if min(len(words), len(seen)) > 0 else 0
                # Lower threshold to 50% for more aggressive deduplication
                if ratio >= 0.50 and len(common) >= 2:
                    dup_index = idx
                    break

            if dup_index >= 0:
                # Merge: append this source to the existing item's SOURCE column
                existing = unique[dup_index]
                if item.fuente not in existing.fuente:
                    existing.fuente = f"{existing.fuente}, {item.fuente}"
            else:
                unique.append(item)
                seen_keys.append(words)

        return unique

    @staticmethod
    def _extract_source_name(sender: str) -> str:
        """Extract clean newsletter name from sender field."""
        name = sender.split("<")[0].strip().strip('"').strip("'")
        # Remove quotes and common suffixes
        name = re.sub(r'\s*(?:via|by|from)\s+.*$', '', name, flags=re.IGNORECASE)
        return name.strip() or sender

    @staticmethod
    def _get_source_priority(fuente: str) -> int:
        fuente_lower = fuente.lower()
        for key, prio in SOURCE_PRIORITY.items():
            if key in fuente_lower:
                return prio
        return 99

    @staticmethod
    def _strip_footer(text: str) -> str:
        """Remove common email footer/boilerplate text."""
        # Cut at common footer markers
        markers = [
            r"(?:^|\n)[-_=]{10,}",
            r"(?:^|\n)(?:Unsubscribe|CHANGE E-MAIL|Manage your subscription|Sent by|You'?re receiving)",
            r"(?:^|\n)(?:Copyright|©|\(c\))\s+\d{4}",
            r"(?:^|\n)Refer\s*\|\s*Tldr",
            r"(?:^|\n)(?:No longer want|To stop receiving)",
            r"(?:^|\n)(?:Legal and Privacy|Privacy Policy)",
        ]
        for marker in markers:
            match = re.search(marker, text, re.IGNORECASE)
            if match and match.start() > len(text) * 0.3:
                text = text[:match.start()]
        return text.strip()
