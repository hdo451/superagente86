from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .analysis_agent import Report, ReportItem, CATEGORIES
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

    # ------------------------------------------------------------------
    # Main document creation with REAL Google Docs table
    # ------------------------------------------------------------------

    def create_report_doc(self, report: Report, title_prefix: str) -> str:
        creds = self._get_credentials()
        service = build("docs", "v1", credentials=creds)

        title = f"{title_prefix} {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        doc = service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        items = report.items
        num_rows = len(items) + 1  # +1 for header row
        num_cols = 4

        # --- Step 1: Insert a header line, then the table ---
        header_text = (
            f"REPORTE DE NEWSLETTERS\n"
            f"{report.generated_at.strftime('%Y-%m-%d %H:%M')}\n"
        )
        if report.executive_summary_es:
            header_text += f"{report.executive_summary_es}\n"
        header_text += "\n"

        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [
                {"insertText": {"location": {"index": 1}, "text": header_text}},
            ]},
        ).execute()

        # Read doc to find end position, then insert table there
        doc_struct = service.documents().get(documentId=doc_id).execute()
        body_content = doc_struct["body"]["content"]
        table_insert_idx = body_content[-1]["endIndex"] - 1

        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [
                {"insertTable": {
                    "rows": num_rows,
                    "columns": num_cols,
                    "location": {"index": table_insert_idx},
                }},
            ]},
        ).execute()

        # --- Step 2: Read back document to get cell indices ---
        doc_struct = service.documents().get(documentId=doc_id).execute()
        cell_indices = self._extract_cell_indices(doc_struct)

        # --- Step 3: Build cell data ---
        header_row = ["TITULAR", "CUERPO", "FUENTE", "ENLACES"]
        data_rows = []
        for item in items:
            enlaces_text = self._format_enlaces(item)
            data_rows.append([
                item.titular,
                item.cuerpo,
                item.fuente,
                enlaces_text,
            ])

        all_rows = [header_row] + data_rows

        # --- Step 4: Insert text into cells in REVERSE order ---
        # This is critical: inserting text shifts all subsequent indices,
        # so we must go from the last cell to the first.
        insert_requests = []
        for row_idx in range(len(all_rows) - 1, -1, -1):
            for col_idx in range(num_cols - 1, -1, -1):
                key = (row_idx, col_idx)
                if key not in cell_indices:
                    continue
                text = all_rows[row_idx][col_idx] if col_idx < len(all_rows[row_idx]) else ""
                if text:
                    insert_requests.append({
                        "insertText": {
                            "location": {"index": cell_indices[key]},
                            "text": text,
                        }
                    })

        if insert_requests:
            # Google Docs API limit per batch is ~500 requests; chunk if needed
            for chunk_start in range(0, len(insert_requests), 400):
                chunk = insert_requests[chunk_start:chunk_start + 400]
                service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": chunk},
                ).execute()

        # --- Step 5: Style the header row (bold) ---
        # Re-read to get updated indices after text insertion
        doc_struct = service.documents().get(documentId=doc_id).execute()
        style_requests = self._build_header_style_requests(doc_struct)
        if style_requests:
            service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": style_requests},
            ).execute()

        return doc_id

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_cell_indices(doc: dict) -> dict:
        """Get {(row, col): start_index} for the first paragraph in each cell."""
        indices = {}
        for element in doc["body"]["content"]:
            if "table" not in element:
                continue
            for row_idx, row in enumerate(element["table"].get("tableRows", [])):
                for col_idx, cell in enumerate(row.get("tableCells", [])):
                    for para in cell.get("content", []):
                        if "paragraph" in para:
                            elems = para["paragraph"].get("elements", [])
                            if elems:
                                idx = elems[0].get("startIndex")
                                if idx is not None:
                                    indices[(row_idx, col_idx)] = idx
                            break  # only first paragraph per cell
        return indices

    @staticmethod
    def _build_header_style_requests(doc: dict) -> list:
        """Bold the first row of the table."""
        requests = []
        for element in doc["body"]["content"]:
            if "table" not in element:
                continue
            first_row = element["table"].get("tableRows", [])[0]
            for cell in first_row.get("tableCells", []):
                for para in cell.get("content", []):
                    if "paragraph" in para:
                        elems = para["paragraph"].get("elements", [])
                        if elems:
                            start = elems[0].get("startIndex", 0)
                            end = elems[-1].get("endIndex", start)
                            if end > start:
                                requests.append({
                                    "updateTextStyle": {
                                        "range": {"startIndex": start, "endIndex": end},
                                        "textStyle": {"bold": True},
                                        "fields": "bold",
                                    }
                                })
                        break
        return requests

    @staticmethod
    def _format_enlaces(item: ReportItem) -> str:
        """Format links for the ENLACES cell."""
        parts = []
        for link in item.enlaces[:3]:
            if "youtu" in link.lower():
                parts.append(f"Video: {link}")
            else:
                parts.append(link)
        parts.append(f"Email: {item.email_link}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Preview for review agent (text only, no Google Docs)
    # ------------------------------------------------------------------

    def _render_report(self, report: Report) -> str:
        lines = [f"RESUMEN: {report.executive_summary_es}\n"]
        for item in report.items:
            lines.append(f"- {item.titular}")
            lines.append(f"  {item.cuerpo}")
            lines.append(f"  Fuente: {item.fuente}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Shortcut creation
    # ------------------------------------------------------------------

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
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "  <key>URL</key>\n"
            f"  <string>{url}</string>\n"
            "</dict>\n"
            "</plist>\n"
        )
