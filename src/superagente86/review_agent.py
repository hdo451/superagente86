from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from typing import List, Optional

import google.generativeai as genai
from PIL import Image


@dataclass
class ReviewFeedback:
    is_good: bool
    issues: List[str]
    suggestions: List[str]
    summary: str


class ReviewAgent:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self._api_key:
            genai.configure(api_key=self._api_key)
            self._model_names = [
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-flash-latest",
            ]
        else:
            self._model_names = []

    @property
    def enabled(self) -> bool:
        return bool(self._model_names)

    def review_document_text(self, content: str) -> ReviewFeedback:
        """Review document content as text (cheaper, faster)"""
        if not self._model_names:
            return ReviewFeedback(
                is_good=True,
                issues=[],
                suggestions=[],
                summary="Review disabled (no API key)"
            )

        prompt = """You are a document reviewer. Analyze the following newsletter report and evaluate:

1. Is it easy to read and understand?
2. Is the structure clear?
3. Is there redundant or confusing information?
4. Are the summaries useful and accurate?
5. CRITICAL: For each headline+summary pair, verify that the summary actually relates to the headline. Flag any mismatches where the body text doesn't match its headline.

Respond in English with this exact format:
QUALITY: [GOOD/FAIR/POOR]
ISSUES:
- issue 1
- issue 2
SUGGESTIONS:
- suggestion 1
- suggestion 2
SUMMARY: [one line summarizing your evaluation]

If there are no issues, write "None" under ISSUES.

DOCUMENT TO REVIEW:
"""
        try:
            response_text = self._generate_text(prompt + content[:8000])
            return self._parse_response(response_text)
        except Exception as e:
            return ReviewFeedback(
                is_good=False,
                issues=[f"Review error: {str(e)}"],
                suggestions=[],
                summary="Could not complete review"
            )

    def review_document_image(self, image_bytes: bytes) -> ReviewFeedback:
        """Review document as image (visual analysis)"""
        if not self._model_names:
            return ReviewFeedback(
                is_good=True,
                issues=[],
                suggestions=[],
                summary="Review disabled (no API key)"
            )

        prompt = """You are a document design reviewer. Look at this image of a report and evaluate:

1. Is it visually appealing and easy to scan?
2. Is the visual hierarchy clear (titles, sections)?
3. Is there too much text together?
4. Is the whitespace adequate?
5. Are the sections clearly distinguished?

Respond in English with this exact format:
QUALITY: [GOOD/FAIR/POOR]
ISSUES:
- issue 1
- issue 2
SUGGESTIONS:
- suggestion 1
- suggestion 2
SUMMARY: [one line summarizing your visual evaluation]

If there are no issues, write "None" under ISSUES.
"""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            response_text = self._generate_image(prompt, image)
            return self._parse_response(response_text)
        except Exception as e:
            return ReviewFeedback(
                is_good=False,
                issues=[f"Visual review error: {str(e)}"],
                suggestions=[],
                summary="Could not complete visual review"
            )

    def _generate_text(self, prompt: str) -> str:
        last_error: Exception | None = None
        for model_name in self._model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "not found" in err_str or "limit: 0" in err_str or "Quota exceeded" in err_str:
                    continue
                break
        if last_error:
            raise last_error
        raise RuntimeError("No Gemini models configured")

    def _generate_image(self, prompt: str, image: Image.Image) -> str:
        last_error: Exception | None = None
        for model_name in self._model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, image])
                return response.text
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "not found" in err_str or "limit: 0" in err_str or "Quota exceeded" in err_str:
                    continue
                break
        if last_error:
            raise last_error
        raise RuntimeError("No Gemini models configured")

    def _parse_response(self, text: str) -> ReviewFeedback:
        lines = text.strip().split("\n")
        
        is_good = True
        issues = []
        suggestions = []
        summary = ""
        
        section = None
        for line in lines:
            line = line.strip()
            if line.startswith("QUALITY:") or line.startswith("CALIDAD:"):
                quality = line.split(":", 1)[1].strip().upper()
                is_good = quality in ("GOOD", "BUENA")
            elif line.startswith("ISSUES:") or line.startswith("PROBLEMAS:"):
                section = "problems"
            elif line.startswith("SUGGESTIONS:") or line.startswith("SUGERENCIAS:"):
                section = "suggestions"
            elif line.startswith("SUMMARY:") or line.startswith("RESUMEN:"):
                summary = line.split(":", 1)[1].strip()
                section = None
            elif line.startswith("- ") or line.startswith("• "):
                item = line[2:].strip()
                if item.lower() not in ("ninguno", "none"):
                    if section == "problems":
                        issues.append(item)
                    elif section == "suggestions":
                        suggestions.append(item)
        
        return ReviewFeedback(
            is_good=is_good,
            issues=issues,
            suggestions=suggestions,
            summary=summary or "Review completed"
        )
