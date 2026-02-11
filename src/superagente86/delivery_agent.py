from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .analysis_agent import Report, ReportItem, ReportSource
from .config import ShortcutConfig


@dataclass
class HyperlinkMarker:
    text: str
    url: str


class DeliveryAgent:
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

    def create_report_doc(self, report: Report, title_prefix: str) -> str:
        creds = self._get_credentials()
        service = build("docs", "v1", credentials=creds)

        title = f"{title_prefix} {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        doc = service.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")

        # Build content and collect hyperlink positions
        content, hyperlinks = self._render_report_with_links(report)
        
        # Insert text first
        requests = [
            {"insertText": {"location": {"index": 1}, "text": content}}
        ]
        
        # Add hyperlink formatting requests
        # Links need to be applied in reverse order to preserve positions
        for start_idx, end_idx, url in reversed(hyperlinks):
            requests.append({
                "updateTextStyle": {
                    "range": {
                        "startIndex": start_idx + 1,  # +1 because doc starts at index 1
                        "endIndex": end_idx + 1,
                    },
                    "textStyle": {
                        "link": {"url": url}
                    },
                    "fields": "link"
                }
            })
        
        service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

        return doc_id

    def create_doc_shortcut(self, doc_id: str, shortcut: ShortcutConfig) -> Path:
        if not shortcut.enabled:
            raise ValueError("Shortcut creation is disabled")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        directory = self._resolve_directory(shortcut.directory)
        directory.mkdir(parents=True, exist_ok=True)

        name = shortcut.name_prefix.strip() or "Newsletter Report"
        if shortcut.include_timestamp:
            stamp = dt.datetime.now().strftime("%Y-%m-%d %H-%M")
            name = f"{name} - {stamp}"
        file_path = directory / f"{name}.webloc"

        file_path.write_text(self._webloc_content(doc_url), encoding="utf-8")
        return file_path

    @staticmethod
    def _resolve_directory(value: str) -> Path:
        if value.startswith("/") or value.startswith("~"):
            return Path(value).expanduser()
        return Path.home() / value

    @staticmethod
    def _webloc_content(url: str) -> str:
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
            "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\">\n"
            "<dict>\n"
            "  <key>URL</key>\n"
            f"  <string>{url}</string>\n"
            "</dict>\n"
            "</plist>\n"
        )

    def _render_report(self, report: Report) -> str:
        content, _ = self._render_report_with_links(report)
        return content

    def _render_report_with_links(self, report: Report) -> Tuple[str, List[Tuple[int, int, str]]]:
        """Returns (content_text, list of (start_idx, end_idx, url))"""
        lines = []
        hyperlinks: List[Tuple[int, int, str]] = []
        current_pos = 0
        
        def add_line(text: str):
            nonlocal current_pos
            lines.append(text)
            current_pos += len(text) + 1  # +1 for newline
        
        def add_link(display_text: str, url: str):
            nonlocal current_pos
            start = current_pos
            end = start + len(display_text)
            hyperlinks.append((start, end, url))
            return display_text
        
        add_line("📰 REPORTE DE NEWSLETTERS")
        add_line(f"   {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
        add_line("")
        
        if report.executive_summary_es or report.executive_summary_en:
            add_line("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            add_line("📊 RESUMEN EJECUTIVO")
            add_line(f"   {report.executive_summary_es}")
            add_line("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            add_line("")
        
        # Group by priority
        high_items = [i for i in report.items if i.priority == "high"]
        medium_items = [i for i in report.items if i.priority == "medium"]
        low_items = [i for i in report.items if i.priority == "low"]
        
        idx = 1
        if high_items:
            add_line("🔴 ALTA PRIORIDAD")
            add_line("─" * 40)
            for item in high_items:
                self._render_item_with_links(item, idx, lines, hyperlinks, current_pos)
                current_pos = sum(len(l) + 1 for l in lines)
                idx += 1
            add_line("")
        
        if medium_items:
            add_line("🟡 MEDIA PRIORIDAD")
            add_line("─" * 40)
            for item in medium_items:
                self._render_item_with_links(item, idx, lines, hyperlinks, current_pos)
                current_pos = sum(len(l) + 1 for l in lines)
                idx += 1
            add_line("")
        
        if low_items:
            add_line("🟢 BAJA PRIORIDAD / APPS")
            add_line("─" * 40)
            for item in low_items:
                self._render_item_with_links(item, idx, lines, hyperlinks, current_pos)
                current_pos = sum(len(l) + 1 for l in lines)
                idx += 1
        
        return "\n".join(lines), hyperlinks

    def _render_item_with_links(
        self, item: ReportItem, index: int, 
        lines: List[str], hyperlinks: List[Tuple[int, int, str]], 
        base_pos: int
    ):
        def current_pos():
            return sum(len(l) + 1 for l in lines)
        
        # Build tag indicators
        indicators = []
        if item.has_company_news:
            indicators.append("🏢")
        if item.has_video:
            indicators.append("🎬")
        if item.has_prompt:
            indicators.append("💡")
        
        indicator_str = " ".join(indicators) + " " if indicators else ""
        
        lines.append("")
        lines.append(f"{index}. {indicator_str}{item.topic.upper()}")
        lines.append(f"   Tags: {', '.join(item.tags)}")
        lines.append("")
        lines.append(f"   {item.summary}")
        lines.append("")
        
        # Render sources with their special content
        for source in item.sources:
            self._render_source_with_links(source, lines, hyperlinks)

        lines.append("")

    def _render_source_with_links(
        self, source: ReportSource, 
        lines: List[str], hyperlinks: List[Tuple[int, int, str]]
    ):
        def current_pos():
            return sum(len(l) + 1 for l in lines)
        
        sender_short = source.sender.split("<")[0].strip() if "<" in source.sender else source.sender
        time_str = source.received_at.strftime("%m-%d %H:%M")
        
        lines.append(f"   ┌─ 📧 {sender_short} ({time_str})")
        lines.append(f"   │  {source.summary}")
        
        # Show prompt of the day COMPLETE
        if source.prompt_of_day:
            lines.append(f"   │")
            lines.append(f"   │  💡 PROMPT OF THE DAY:")
            lines.append(f"   │  \"{source.prompt_of_day}\"")
        
        # Show company news
        if source.company_news:
            lines.append(f"   │")
            lines.append(f"   │  🏢 NOTICIAS: {', '.join(source.company_news)}")
        
        # Show video links with hyperlinks
        if source.video_links:
            lines.append(f"   │")
            lines.append(f"   │  🎬 VIDEOS:")
            for i, vlink in enumerate(source.video_links[:3]):
                pos = current_pos()
                link_text = f"Ver video {i+1}"
                prefix = f"   │     → "
                # Calculate position of the link text
                start_idx = pos + len(prefix)
                end_idx = start_idx + len(link_text)
                hyperlinks.append((start_idx, end_idx, vlink))
                lines.append(f"{prefix}{link_text}")
        
        # Show apps to try (secondary)
        if source.app_mentions:
            lines.append(f"   │  📱 Apps: {', '.join(source.app_mentions)}")
        
        # Other links with hyperlinks
        other_links = [l for l in source.extracted_links if l not in source.video_links][:3]
        if other_links:
            pos = current_pos()
            prefix = "   │  🔗 "
            line_parts = [prefix]
            link_start = pos + len(prefix)
            
            for i, link in enumerate(other_links):
                if i > 0:
                    line_parts.append(" | ")
                    link_start += 3
                
                link_text = f"Link {i+1}"
                hyperlinks.append((link_start, link_start + len(link_text), link))
                line_parts.append(link_text)
                link_start += len(link_text)
            
            lines.append("".join(line_parts))
        
        # Email link as hyperlink
        pos = current_pos()
        prefix = "   └─ 📌 "
        link_text = "Ver email"
        start_idx = pos + len(prefix)
        end_idx = start_idx + len(link_text)
        hyperlinks.append((start_idx, end_idx, source.email_link))
        lines.append(f"{prefix}{link_text}")
        lines.append("")
