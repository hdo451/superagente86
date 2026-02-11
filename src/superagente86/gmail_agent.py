from __future__ import annotations

import base64
import datetime as dt
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import List, Optional

from googleapiclient.discovery import build
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

        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        message_ids = [msg["id"] for msg in response.get("messages", [])]

        messages: List[GmailMessage] = []
        for message_id in message_ids:
            raw = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
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

            body_text = self._extract_body(payload)
            links = self._extract_links(payload)
            messages.append(
                GmailMessage(
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    received_at=received_at,
                    snippet=raw.get("snippet", ""),
                    body_text=body_text,
                    link=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
                    links=links,
                )
            )
        return messages

    def _extract_body(self, payload: dict) -> str:
        if "parts" in payload:
            parts = payload.get("parts", [])
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    return self._decode_body(part.get("body", {}).get("data"))
            for part in parts:
                if part.get("mimeType") == "text/html":
                    return self._strip_html(
                        self._decode_body(part.get("body", {}).get("data"))
                    )
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

    @staticmethod
    def _strip_html(text: str) -> str:
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
