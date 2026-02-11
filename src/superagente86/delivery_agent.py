from __future__ import annotations

import datetime as dt
from typing import List

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .analysis_agent import Report, ReportItem, ReportSource


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

    def _render_report(self, report: Report) -> str:
        lines = []
        lines.append(f"Reporte generado: {report.generated_at.isoformat()}")
        lines.append("")
        if report.executive_summary_es or report.executive_summary_en:
            lines.append("Resumen ejecutivo (ES):")
            lines.append(report.executive_summary_es)
            lines.append("")
            lines.append("Executive summary (EN):")
            lines.append(report.executive_summary_en)
            lines.append("")
        lines.append("Items:")
        for item in report.items:
            lines.extend(self._render_item(item))
        lines.append("")
        return "\n".join(lines)

    def _render_item(self, item: ReportItem) -> List[str]:
        lines = [
            f"- {item.topic}",
            f"  Priority: {item.priority}",
            f"  Tags: {', '.join(item.tags)}",
            f"  ES: {item.summary_es}",
            f"  EN: {item.summary_en}",
            "  Fuentes:",
        ]
        for source in item.sources:
            lines.extend(self._render_source(source))
        lines.append("")
        return lines

    def _render_source(self, source: ReportSource) -> List[str]:
        lines = [
            f"    - {source.sender} ({source.received_at.isoformat()})",
            f"      Email: {source.email_link}",
            f"      ES: {source.summary_es}",
            f"      EN: {source.summary_en}",
        ]
        if source.extracted_links:
            lines.append("      Links:")
            for link in source.extracted_links:
                lines.append(f"        - {link}")
        return lines
