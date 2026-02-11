from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import google.generativeai as genai

from .gmail_agent import GmailMessage


@dataclass
class ReportSource:
    sender: str
    received_at: dt.datetime
    email_link: str
    extracted_links: List[str]
    video_links: List[str] = field(default_factory=list)


@dataclass
class ReportItem:
    """A single news item extracted from a newsletter."""
    titular: str
    cuerpo: str
    fuente: str  # Newsletter name (e.g. "The Neuron", "TLDR AI")
    enlaces: List[str]
    email_link: str
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
    executive_summary_es: str
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
            self._model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self._model = None

    def analyze(self, messages: List[GmailMessage], include_exec_summary: bool) -> Report:
        all_items: List[ReportItem] = []

        for msg in messages:
            items = self._extract_news_items(msg)
            all_items.extend(items)

        # Sort by source priority (The Neuron first, then TLDR AI, etc.)
        all_items.sort(key=lambda x: x.source_priority)

        # Deduplicate: keep first occurrence (highest priority source)
        all_items = self._deduplicate(all_items)

        exec_es = ""
        if include_exec_summary and all_items:
            sources = set(it.fuente for it in all_items)
            exec_es = f"{len(all_items)} noticias de {len(sources)} newsletters."

        return Report(
            generated_at=dt.datetime.now(dt.timezone.utc),
            executive_summary_es=exec_es,
            items=all_items,
        )

    # ------------------------------------------------------------------
    # Gemini API with rate-limit retry
    # ------------------------------------------------------------------

    def _gemini_call(self, prompt: str, max_retries: int = 2):
        """Call Gemini with retry on rate limit errors."""
        for attempt in range(max_retries + 1):
            try:
                response = self._model.generate_content(prompt)
                # Small delay between calls to avoid per-minute rate limits
                time.sleep(2)
                return response
            except Exception as e:
                err_str = str(e)
                # Don't retry daily quota exhaustion — it won't recover
                if "PerDay" in err_str or "limit: 0" in err_str:
                    raise
                if "429" in err_str and attempt < max_retries:
                    wait = 15 * (attempt + 1)
                    print(f"   ⏳ Rate limit, esperando {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    # ------------------------------------------------------------------
    # Gemini-based extraction
    # ------------------------------------------------------------------

    def _extract_news_items(self, message: GmailMessage) -> List[ReportItem]:
        """Use Gemini to extract individual news from a newsletter email."""
        fuente = self._extract_source_name(message.sender)
        priority = self._get_source_priority(fuente)
        email_link = message.link
        video_links = self._extract_video_links(message.links)
        other_links = [l for l in message.links if l not in video_links]

        body = message.body_text or message.snippet or ""
        body = self._strip_footer(body)

        if not self._model or len(body.strip()) < 50:
            return self._fallback_extract(message, fuente, priority)

        prompt = (
            "Eres un asistente que extrae noticias individuales de newsletters de tecnología/IA.\n"
            "Analiza el siguiente email y extrae CADA noticia individual.\n"
            "Para cada noticia devuelve:\n"
            '- "titular": titular corto y claro en español (máx 12 palabras)\n'
            '- "cuerpo": resumen en español de 2-3 oraciones. Debe explicar claramente qué pasó, '
            "quién está involucrado y por qué importa. NO incluyas texto de pie de página, "
            "enlaces, ni contenido promocional.\n\n"
            "REGLAS:\n"
            "- Máximo 5 noticias por newsletter. Prioriza las más importantes.\n"
            "- Ignora publicidad, ofertas de trabajo, secciones de referidos, pie de página.\n"
            "- Ignora secciones tipo 'Prompt of the day' o 'Meme of the day'.\n"
            "- Solo extrae noticias reales con información sustancial.\n"
            "- Si no hay noticias claras, devuelve un array vacío.\n"
            "- Responde SOLO con un JSON array válido, sin markdown ni explicaciones.\n\n"
            f"Newsletter: {fuente}\n"
            f"Asunto: {message.subject}\n\n"
            f"Contenido:\n{body[:6000]}\n\n"
            'Responde SOLO con JSON: [{"titular": "...", "cuerpo": "..."}]'
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
        for entry in parsed[:5]:  # Max 5 items per newsletter
            titular = (entry.get("titular") or "").strip()
            cuerpo = (entry.get("cuerpo") or "").strip()
            if not titular or not cuerpo or len(cuerpo) < 20:
                continue

            # Assign relevant links from the email
            enlaces = list(video_links[:2]) + list(other_links[:2])

            items.append(ReportItem(
                titular=titular,
                cuerpo=cuerpo,
                fuente=fuente,
                enlaces=enlaces[:4],
                email_link=email_link,
                source_priority=priority,
            ))

        return items if items else self._fallback_extract(message, fuente, priority)

    def _fallback_extract(self, message: GmailMessage, fuente: str, priority: int) -> List[ReportItem]:
        """Regex-based fallback when Gemini is unavailable."""
        subject = message.subject.strip()
        # Clean subject: remove emojis and newsletter prefixes
        subject = re.sub(r'^[^\w]*', '', subject).strip()
        subject = subject[:80] if len(subject) > 80 else subject

        body = message.body_text or message.snippet or ""
        body = self._strip_footer(body)
        # Clean body: remove URLs, artifacts, take first meaningful chunk
        body = re.sub(r'https?://\S+', '', body)
        body = re.sub(r'[\u200b\u200c\u200d\u2060\ufeff\u00ad]+', '', body)
        body = re.sub(r'\s+', ' ', body).strip()
        # Take first 300 chars that look like actual content
        cuerpo = body[:300].strip()
        if len(cuerpo) < 20:
            cuerpo = f"Newsletter de {fuente}: {subject}"

        video_links = self._extract_video_links(message.links)
        other_links = [l for l in message.links if l not in video_links]

        return [ReportItem(
            titular=subject,
            cuerpo=cuerpo,
            fuente=fuente,
            enlaces=(video_links[:2] + other_links[:2])[:4],
            email_link=message.link,
            source_priority=priority,
        )]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _deduplicate(self, items: List[ReportItem]) -> List[ReportItem]:
        """Remove duplicate news across newsletters. Items are pre-sorted by priority."""
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

            is_dup = False
            for seen in seen_keys:
                if not seen:
                    continue
                common = words & seen
                ratio = len(common) / min(len(words), len(seen)) if min(len(words), len(seen)) > 0 else 0
                if ratio >= 0.5 and len(common) >= 2:
                    is_dup = True
                    break

            if not is_dup:
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
    def _extract_video_links(links: List[str]) -> List[str]:
        video_domains = ["youtube.com", "youtu.be", "vimeo.com"]
        return [l for l in links if any(d in l.lower() for d in video_domains)]

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
