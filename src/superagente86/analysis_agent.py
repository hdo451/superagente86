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
    category: str = "general"  # new_models, research, robots, funding, apps, general
    has_prompt: bool = False
    has_video: bool = False
    has_company_news: bool = False


# Category definitions for AI news
CATEGORIES = {
    "new_models": {
        "name_es": "🚀 NUEVOS MODELOS",
        "name_en": "New Models",
        "keywords": ["gpt-5", "gpt-4", "claude", "gemini", "llama", "mistral", "model release", 
                     "new model", "launches", "released", "announced", "upgrade", "version",
                     "multimodal", "foundation model", "weights", "open source", "fine-tun"],
    },
    "research": {
        "name_es": "🔬 RESEARCH",
        "name_en": "Research",
        "keywords": ["paper", "arxiv", "research", "study", "breakthrough", "discovered",
                     "technique", "algorithm", "benchmark", "state-of-the-art", "sota",
                     "training", "inference", "reasoning", "evaluation", "dataset"],
    },
    "robots": {
        "name_es": "🤖 ROBOTS",
        "name_en": "Robots",
        "keywords": ["robot", "humanoid", "boston dynamics", "figure", "optimus", "tesla bot",
                     "autonomous", "embodied", "manipulation", "locomotion", "actuator",
                     "warehouse", "industrial robot", "cobot"],
    },
    "funding": {
        "name_es": "💰 FUNDING & EMPRESAS",
        "name_en": "Funding & Companies",
        "keywords": ["raised", "funding", "series", "valuation", "acquisition", "acquired",
                     "ipo", "merger", "billion", "million", "investor", "venture", "startup"],
    },
    "apps": {
        "name_es": "🛠️ APPS & TOOLS",
        "name_en": "Apps & Tools",
        "keywords": ["app", "tool", "plugin", "extension", "api", "sdk", "platform",
                     "saas", "product", "feature", "integration", "workflow", "automation"],
    },
    "general": {
        "name_es": "📰 GENERAL",
        "name_en": "General",
        "keywords": [],
    },
}


@dataclass
class Report:
    generated_at: dt.datetime
    executive_summary_es: str
    executive_summary_en: str
    items: List[ReportItem]


class AnalysisAgent:
    def analyze(self, messages: List[GmailMessage], include_exec_summary: bool) -> Report:
        grouped = self._group_by_topic(messages)
        items = [self._build_item(topic, msgs) for topic, msgs in grouped.items()]
        
        # Deduplicate similar news across categories
        items = self._deduplicate_items(items)
        
        exec_es, exec_en = (
            self._build_exec_summary(items) if include_exec_summary else ("", "")
        )
        return Report(
            generated_at=dt.datetime.now(dt.timezone.utc),
            executive_summary_es=exec_es,
            executive_summary_en=exec_en,
            items=items,
        )

    def _deduplicate_items(self, items: List[ReportItem]) -> List[ReportItem]:
        """Remove duplicate news that appear in multiple categories"""
        seen_topics = {}
        unique_items = []
        
        # Sort by priority to keep the highest priority version
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_items = sorted(items, key=lambda x: priority_order.get(x.priority, 2))
        
        for item in sorted_items:
            # Create a normalized key from significant topic words
            topic_words = item.topic.lower().split()
            # Remove common words
            stopwords = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are", 
                         "ai", "news", "update", "daily", "weekly", "newsletter", "today",
                         "this", "that", "with", "from", "your", "on", "at", "by"}
            key_words = set(w for w in topic_words if w not in stopwords and len(w) > 2)
            
            if not key_words:
                unique_items.append(item)
                continue
            
            # Check if similar topic already exists
            is_duplicate = False
            for seen_key, seen_item in seen_topics.items():
                common = key_words & seen_key
                # If more than 40% of significant words match, it's likely the same news
                match_ratio = len(common) / max(len(key_words), 1)
                if match_ratio >= 0.4 and len(common) >= 2:
                    # Merge sources into the existing item
                    seen_item.sources.extend(item.sources)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_topics[frozenset(key_words)] = item
                unique_items.append(item)
        
        return unique_items

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
        
        # Classify into category
        combined_text = " ".join(m.subject + " " + (m.body_text or m.snippet) for m in messages)
        category = self._classify_category(combined_text)
        
        priority = self._score_priority(tags, has_company_news, category)
        primary = messages[0]
        summary = self._summarize(primary, priority)
        
        return ReportItem(
            topic=topic,
            summary=summary,
            tags=list(set(tags)),
            priority=priority,
            sources=sources,
            category=category,
            has_prompt=has_prompt,
            has_video=has_video,
            has_company_news=has_company_news,
        )

    def _classify_category(self, text: str) -> str:
        """Classify text into one of the AI news categories"""
        text_lower = text.lower()
        scores = {}
        
        for cat_id, cat_info in CATEGORIES.items():
            if cat_id == "general":
                continue
            score = sum(1 for kw in cat_info["keywords"] if kw in text_lower)
            if score > 0:
                scores[cat_id] = score
        
        if not scores:
            return "general"
        
        # Return category with highest score
        return max(scores, key=scores.get)

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

    def _score_priority(self, tags: List[str], has_company_news: bool = False, category: str = "general") -> str:
        # High priority: funding news, new models, company announcements
        if "funding" in tags or has_company_news or category in ("funding", "new_models"):
            return "high"
        # Medium: research, robots, AI-related
        if "ai" in tags or "company" in tags or category in ("research", "robots"):
            return "medium"
        return "low"

    def _summarize(self, message: GmailMessage, priority: str) -> str:
        text = message.body_text.strip() if message.body_text else message.snippet
        text = self._clean_text(text)
        
        # Split into sentences and find the most informative ones
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Score sentences by informativeness
        news_keywords = {
            "announced", "launched", "released", "raised", "acquired", "partnership",
            "billion", "million", "percent", "growth", "revenue", "users",
            "new", "first", "largest", "update", "version", "model", "feature",
            "company", "startup", "ceo", "founder", "team", "employees",
        }
        
        scored_sentences = []
        seen_content = set()
        
        for s in sentences:
            s = s.strip()
            if len(s) < 20 or len(s) > 300:
                continue
            
            # Skip if too similar to already selected
            s_lower = s.lower()
            s_words = set(s_lower.split())
            is_duplicate = False
            for seen in seen_content:
                common = s_words & seen
                if len(common) > len(s_words) * 0.5:
                    is_duplicate = True
                    break
            if is_duplicate:
                continue
            
            # Score based on news keywords
            score = sum(1 for kw in news_keywords if kw in s_lower)
            # Bonus for having numbers (often indicates data/facts)
            if re.search(r'\d+', s):
                score += 1
            # Penalty for promotional language
            if any(w in s_lower for w in ["click", "subscribe", "join", "free", "discount"]):
                score -= 2
            
            if score > 0:
                scored_sentences.append((score, s))
                seen_content.add(frozenset(s_words))
        
        # Sort by score and take best sentences
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        best_sentences = [s for _, s in scored_sentences[:2]]
        
        if best_sentences:
            result = " ".join(best_sentences)
        else:
            # Fallback: take first non-trivial sentence
            for s in sentences:
                s = s.strip()
                if len(s) > 30 and not any(w in s.lower() for w in ["welcome", "hello", "hi ", "hey "]):
                    result = s
                    break
            else:
                result = text[:150] + "..." if len(text) > 150 else text
        
        # Ensure reasonable length
        words = result.split()
        max_words = 45 if priority == "high" else 30
        if len(words) > max_words:
            return " ".join(words[:max_words]) + "..."
        return result if result else "(sin resumen)"

    def _summarize_source(self, message: GmailMessage) -> str:
        # Use snippet only to avoid duplication with main summary
        text = message.snippet or ""
        text = self._clean_text(text)
        words = text.split()
        if len(words) > 25:
            return " ".join(words[:25]) + "..."
        return text if text else "(sin extracto)"

    def _clean_text(self, text: str) -> str:
        # Remove zero-width characters and artifacts
        text = re.sub(r'[\u200b\u200c\u200d\u2060\ufeff]+', '', text)
        # Remove ALL image placeholders and patterns
        text = re.sub(r'View image:.*?(?:Caption:|$)', '', text, flags=re.IGNORECASE|re.DOTALL)
        text = re.sub(r'Follow image link:.*?(?:\s|$)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[image\]|\[img\]|\(image\)|Image:', '', text, flags=re.IGNORECASE)
        # Remove newsletter intro/outro patterns
        intro_patterns = [
            r'Welcome back[^.]*\.?',
            r'Welcome,? \w+[^.]*\.?',
            r'Happy \w+day[^.]*\.?',
            r'Good (?:morning|afternoon|evening)[^.]*\.?',
            r'Hi there[^.]*\.?',
            r'Hello[^.]*\.?',
            r'Hey[^.]*\.?',
            r"Here'?s? (?:what|today)[^.]*\.?",
            r'In this (?:issue|edition|newsletter)[^.]*\.?',
            r'Today we[^.]*\.?',
            r'This week[^.]*\.?',
        ]
        for pattern in intro_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        # Remove promotional/CTA text
        text = re.sub(r'(?:Sign Up|Subscribe|Unsubscribe|Click here|Read more|View in browser|Advertise|Forward this|Refer a friend|Share this|Sponsor)[^.]*\.?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:Share|Tweet|Post|Like|Follow us|Join us)[^.]{0,30}', '', text, flags=re.IGNORECASE)
        # Remove URL patterns in text
        text = re.sub(r'https?://\S*', '', text)
        text = re.sub(r'www\.\S*', '', text)
        # Remove email artifacts
        text = re.sub(r'\(?\s*Caption:\s*\)?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Refer\s*\|\s*Tldr\s*\|\s*Advertise', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\|\s*Advertise', '', text, flags=re.IGNORECASE)
        # Remove repeated special chars
        text = re.sub(r'[\u2022\u2023\u25aa\u25ab\u25cf\u25cb]{2,}', '', text)
        # Clean whitespace
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        # Remove orphan punctuation and empty parens
        text = re.sub(r'\s[|:;,]+\s', ' ', text)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'\[\s*\]', '', text)
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
            r"(?:try|check out|download|use|introducing)\s+([A-Z][a-zA-Z0-9]{2,}(?:\s+[A-Z][a-zA-Z0-9]+)?)",
            r"(?:new app|new tool)[:\s]+([A-Z][a-zA-Z0-9]{2,}(?:\s+[A-Z0-9]+)?)",
        ]
        apps = []
        stopwords = {'the', 'and', 'for', 'with', 'this', 'that', 'your', 'our', 'his', 'her'}
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                cleaned = m.strip()
                if len(cleaned) > 2 and cleaned.lower() not in stopwords:
                    apps.append(cleaned)
        return list(set(apps))[:3]

    def _extract_company_news(self, text: str) -> List[str]:
        # Look for full sentence fragments with company + action
        patterns = [
            r"((?:OpenAI|Google|Microsoft|Meta|Apple|Amazon|Anthropic|Nvidia|Tesla|xAI|Mistral|Cohere)\s+(?:announced|launches|raised|acquired|partners|releases)[^.]{5,80})",
            r"(\$[\d.]+[MBK]?\s+(?:funding|raised|valuation)[^.]{5,50})",
        ]
        news = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                cleaned = self._clean_text(m)
                if len(cleaned) > 15:
                    news.append(cleaned[:100])
        return list(set(news))[:3]

    def _build_exec_summary(self, items: List[ReportItem]) -> tuple[str, str]:
        if not items:
            return "Sin novedades relevantes.", "No relevant updates."
        
        # Count by category
        cat_counts = {}
        for item in items:
            cat_counts[item.category] = cat_counts.get(item.category, 0) + 1
        
        # Build summary showing category breakdown
        parts_es = []
        parts_en = []
        for cat_id in ["new_models", "research", "robots", "funding", "apps", "general"]:
            if cat_id in cat_counts:
                count = cat_counts[cat_id]
                name_es = CATEGORIES[cat_id]["name_es"].split(" ", 1)[1]  # Remove emoji
                name_en = CATEGORIES[cat_id]["name_en"]
                parts_es.append(f"{count} {name_es}")
                parts_en.append(f"{count} {name_en}")
        
        es = f"Hoy: {', '.join(parts_es)}. Total: {len(items)} noticias."
        en = f"Today: {', '.join(parts_en)}. Total: {len(items)} news."
        
        return es, en
