from __future__ import annotations

import base64
import datetime as dt
import random
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


@dataclass
class GmailMessage:
    message_id: str
    subject: str
    sender: str
    received_at: dt.datetime
    snippet: str
    body_text: str
    body_html: str  # NEW: Store raw HTML for better extraction
    link: str
    links: List[str]


class GmailAgent:
    def __init__(self, credentials_path: str, token_path: str, scopes: List[str]) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._scopes = scopes

    def _get_credentials(self) -> Credentials:
        creds = None
        try:
            creds = Credentials.from_authorized_user_file(self._token_path, self._scopes)
        except Exception:
            creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_path, self._scopes
                )
                creds = flow.run_local_server(port=0)
            with open(self._token_path, "w", encoding="utf-8") as handle:
                handle.write(creds.to_json())
        return creds

    def fetch_messages(
        self,
        label: str,
        max_results: int,
        after_ts: Optional[dt.datetime] = None,
        before_ts: Optional[dt.datetime] = None,
    ) -> List[GmailMessage]:
        creds = self._get_credentials()
        service = build("gmail", "v1", credentials=creds)

        query = f"label:{label}"
        if after_ts:
            query += f" after:{int(after_ts.timestamp())}"
        if before_ts:
            query += f" before:{int(before_ts.timestamp())}"

        # ULTRA-RESILIENT: 10 attempts with exponential backoff + jitter
        # Max delays: 1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s, 512s
        # Total ~17 minutes of waiting if all retries fail
        max_retries = 10
        for attempt in range(max_retries):
            try:
                response = (
                    service.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=max_results)
                    .execute()
                )
                break
            except (HttpError, TimeoutError, OSError) as e:
                if attempt < max_retries - 1:
                    base_wait = min(2 ** attempt, 60)  # Cap at 60s
                    jitter = random.uniform(0, base_wait * 0.3)
                    wait_time = base_wait + jitter
                    print(f"⚠️  Gmail timeout, waiting {wait_time:.1f}s... ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Gmail API failed after {max_retries} attempts")
                    raise
        
        message_ids = [msg["id"] for msg in response.get("messages", [])]

        messages: List[GmailMessage] = []
        for message_id in message_ids:
            # Retry for individual messages too
            for attempt in range(max_retries):
                try:
                    raw = (
                        service.users()
                        .messages()
                        .get(userId="me", id=message_id, format="full")
                        .execute()
                    )
                    break
                except (HttpError, TimeoutError, OSError) as e:
                    if attempt < max_retries - 1:
                        base_wait = min(2 ** attempt, 60)
                        jitter = random.uniform(0, base_wait * 0.3)
                        wait_time = base_wait + jitter
                        time.sleep(wait_time)
                    else:
                        raise
            
            payload = raw.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "(unknown)")
            date_header = headers.get("date")
            received_at = (
                parsedate_to_datetime(date_header)
                if date_header
                else dt.datetime.now(dt.timezone.utc)
            )

            body_text = self._extract_body(payload, mime_type="text/plain")
            body_html = self._extract_body(payload, mime_type="text/html")
            links = self._extract_links(payload)
            messages.append(
                GmailMessage(
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    received_at=received_at,
                    snippet=raw.get("snippet", ""),
                    body_text=body_text,
                    body_html=body_html,
                    link=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
                    links=links,
                )
            )
        return messages

    def _extract_body(self, payload: dict, mime_type: str = "text/plain") -> str:
        """Extract body in specified MIME type.
        If not found, falls back to the other type."""
        if "parts" in payload:
            parts = payload.get("parts", [])
            # First try to find the requested mime type
            for part in parts:
                if part.get("mimeType") == mime_type:
                    data = part.get("body", {}).get("data")
                    text = self._decode_body(data)
                    if mime_type == "text/html":
                        return text  # Return raw HTML, don't strip
                    return text
            # Fallback: try the other type
            fallback_type = "text/html" if mime_type == "text/plain" else "text/plain"
            for part in parts:
                if part.get("mimeType") == fallback_type:
                    text = self._decode_body(part.get("body", {}).get("data"))
                    if fallback_type == "text/html":
                        return self._html_to_clean_text(text)  # Clean HTML if falling back
                    return text
        # Direct body (not multipart)
        data = payload.get("body", {}).get("data")
        return self._decode_body(data)

    def _extract_links(self, payload: dict) -> List[str]:
        links: List[str] = []
        for part in self._collect_parts(payload):
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if not data:
                continue
            text = self._decode_body(data)
            if mime == "text/plain":
                links.extend(self._extract_links_from_text(text))
            elif mime == "text/html":
                links.extend(self._extract_links_from_html(text))

        deduped = []
        seen = set()
        # Filter out tracking and promotional links
        skip_patterns = [
            "unsubscribe", "unsub", "optout", "opt-out",
            "manage-subscription", "preferences",
            "refer", "referral", "share",
            "twitter.com/intent", "facebook.com/sharer",
            "linkedin.com/share", "mailto:",
            "tracking", "click.", "trk.", "r.", "t.",
            "list-manage.com", "mailchimp.com",
            "beehiiv.com", "substack.com/redirect",
        ]
        for link in links:
            if link in seen:
                continue
            link_lower = link.lower()
            if any(pattern in link_lower for pattern in skip_patterns):
                continue
            seen.add(link)
            deduped.append(link)
        return deduped

    def _collect_parts(self, payload: dict) -> List[dict]:
        parts = [payload]
        for part in payload.get("parts", []) or []:
            parts.extend(self._collect_parts(part))
        return parts

    def _extract_links_from_text(self, text: str) -> List[str]:
        candidates = re.findall(r"https?://[^\s\)\]>\"]+", text)
        return [self._clean_link(link) for link in candidates]

    def _extract_links_from_html(self, html: str) -> List[str]:
        hrefs = re.findall(r"href=[\"'](https?://[^\"']+)[\"']", html, re.I)
        urls = re.findall(r"https?://[^\s\)\]>\"]+", html)
        candidates = hrefs + urls
        return [self._clean_link(link) for link in candidates]

    @staticmethod
    def _clean_link(link: str) -> str:
        return link.rstrip(".,;)")

    @staticmethod
    def _decode_body(data: Optional[str]) -> str:
        if not data:
            return ""
        decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
        return decoded.decode("utf-8", errors="ignore")

    def mark_as_read(self, message_ids: List[str]) -> None:
        """Mark messages as read in Gmail."""
        if not message_ids:
            return
        
        creds = self._get_credentials()
        service = build("gmail", "v1", credentials=creds)
        
        # Ultra-resilient retry logic
        max_retries = 10
        for attempt in range(max_retries):
            try:
                # Use batch modify to mark all as read
                service.users().messages().batchModify(
                    userId="me",
                    body={
                        "ids": message_ids,
                        "removeLabelIds": ["UNREAD"]
                    }
                ).execute()
                break
            except (HttpError, TimeoutError, OSError) as e:
                if attempt < max_retries - 1:
                    base_wait = min(2 ** attempt, 60)
                    jitter = random.uniform(0, base_wait * 0.3)
                    wait_time = base_wait + jitter
                    time.sleep(wait_time)
                else:
                    raise

    @staticmethod
    def _strip_html(text: str) -> str:
        """Legacy: Simple HTML stripper. Use _html_to_clean_text() for better results."""
        stripped = []
        skip = False
        for char in text:
            if char == "<":
                skip = True
                continue
            if char == ">":
                skip = False
                continue
            if not skip:
                stripped.append(char)
        return "".join(stripped)

    @staticmethod
    def _html_to_clean_text(html: str) -> str:
        """Convert HTML to clean text while preserving structure.
        - Remove script/style tags
        - Remove HTML tags
        - Normalize whitespace
        - Preserve line breaks from block elements"""
        import re
        
        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Add newlines before block-level elements to preserve structure
        block_elements = ['</div>', '</p>', '</h[1-6]>', '</li>', '</table>', '</tr>', '</td>']
        for elem in block_elements:
            html = re.sub(elem, elem + '\n', html, flags=re.IGNORECASE)
        
        # Remove remaining HTML tags
        html = re.sub(r'<[^>]+>', '', html)
        
        # Decode HTML entities
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&amp;', '&')
        html = html.replace('&quot;', '"')
        html = html.replace('&#39;', "'")
        
        # Normalize whitespace
        lines = [line.strip() for line in html.split('\n')]
        lines = [line for line in lines if line]  # Remove empty lines
        
        return '\n'.join(lines)
