#!/usr/bin/env python3
"""Quick script to inspect generated Google Doc structure."""
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

token_path = Path("token.json")
creds_data = json.load(open(token_path))
creds = Credentials.from_authorized_user_info(creds_data)
service = build("docs", "v1", credentials=creds)

doc_id = "1r_6D8zs0HIFEPriJP5BI7hQLc7zsmuh8fm5x3zByAKQ"
doc = service.documents().get(documentId=doc_id).execute()

body = doc["body"]["content"]
for element in body:
    if "paragraph" in element:
        text = ""
        for run in element["paragraph"].get("elements", []):
            if "textRun" in run:
                text += run["textRun"]["content"]
        if text.strip():
            print(f"[PARAGRAPH] {text.strip()}")
    elif "table" in element:
        table = element["table"]
        num_rows = len(table.get("tableRows", []))
        print(f"\n[TABLE] {num_rows} rows x {table.get('columns', '?')} cols")
        for row_idx, row in enumerate(table.get("tableRows", [])):
            cells = row.get("tableCells", [])
            cell_texts = []
            for cell in cells:
                cell_text = ""
                for para in cell.get("content", []):
                    if "paragraph" in para:
                        for run in para["paragraph"].get("elements", []):
                            if "textRun" in run:
                                cell_text += run["textRun"]["content"]
                cell_texts.append(cell_text.strip()[:80])
            print(f"  Row {row_idx}: {' | '.join(cell_texts)}")
        print()
