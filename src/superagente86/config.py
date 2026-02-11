from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import yaml


@dataclass
class ScheduleConfig:
    times: List[str]
    timezone: str


@dataclass
class ReportConfig:
    language: str
    include_exec_summary: bool


@dataclass
class ShortcutConfig:
    enabled: bool
    name_prefix: str
    directory: str
    include_timestamp: bool


@dataclass
class AppConfig:
    label: str
    max_messages: int
    report: ReportConfig
    schedule: ScheduleConfig
    shortcut: ShortcutConfig


@dataclass
class GoogleConfig:
    gmail_scopes: List[str]
    docs_scopes: List[str]
    token_path: str
    credentials_path: str


def load_app_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    report = raw.get("report", {})
    schedule = raw.get("schedule", {})
    shortcut = raw.get("shortcut", {})

    return AppConfig(
        label=raw.get("label", "newsletters"),
        max_messages=int(raw.get("max_messages", 50)),
        report=ReportConfig(
            language=report.get("language", "bilingual"),
            include_exec_summary=bool(report.get("include_exec_summary", True)),
        ),
        schedule=ScheduleConfig(
            times=schedule.get("times", ["08:30", "13:30"]),
            timezone=schedule.get("timezone", "local"),
        ),
        shortcut=ShortcutConfig(
            enabled=bool(shortcut.get("enabled", False)),
            name_prefix=shortcut.get("name_prefix", "Newsletter Report"),
            directory=shortcut.get("directory", "Desktop"),
            include_timestamp=bool(shortcut.get("include_timestamp", True)),
        ),
    )


def load_google_config() -> GoogleConfig:
    gmail_scopes = os.getenv("GMAIL_SCOPES", "").split() or [
        "https://www.googleapis.com/auth/gmail.modify"
    ]
    docs_scopes = os.getenv("DOCS_SCOPES", "").split() or [
        "https://www.googleapis.com/auth/documents"
    ]

    return GoogleConfig(
        gmail_scopes=gmail_scopes,
        docs_scopes=docs_scopes,
        token_path=os.getenv("GOOGLE_TOKEN_PATH", "token.json"),
        credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
    )
