from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .analysis_agent import Report, ReportItem, ReportSource
from .config import ShortcutConfig


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

        content = self._render_report(report)
        requests = [
            {"insertText": {"location": {"index": 1}, "text": content}}
        ]
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
        lines = []
        lines.append(f"Reporte: {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        
        if report.executive_summary_es or report.executive_summary_en:
            lines.append("━━━ RESUMEN ━━━")
            lines.append(f"ES: {report.executive_summary_es}")
            lines.append(f"EN: {report.executive_summary_en}")
            lines.append("")
        
        for i, item in enumerate(report.items, 1):
            lines.extend(self._render_item(item, i))
        
        return "\n".join(lines)

    def _render_item(self, item: ReportItem, index: int) -> List[str]:
        lines = [
            f"\n{index}. {item.topic.upper()}",
            f"   [Priority: {item.priority.upper()} | Tags: {', '.join(item.tags)}]",
            "",
            f"   {item.summary_es}",
            "",
        ]
        
        # Render sources compactly
        for source in item.sources:
            lines.extend(self._render_source(source))
        
        return lines

    def _render_source(self, source: ReportSource) -> List[str]:
        sender_short = source.sender.split("<")[0].strip() if "<" in source.sender else source.sender
        time_str = source.received_at.strftime("%m-%d %H:%M")
        
        lines = [
            f"   📧 {sender_short} ({time_str})",
            f"      └─ {source.summary_es[:100]}..." if len(source.summary_es) > 100 else f"      └─ {source.summary_es}",
        ]
        
        if source.extracted_links:
            links_str = " | ".join(source.extracted_links[:3])
            if len(source.extracted_links) > 3:
                links_str += f" + {len(source.extracted_links) - 3} more"
            lines.append(f"      🔗 {links_str}")
        
        lines.append(f"      📌 {source.email_link}")
        lines.append("")
        
        return lines
