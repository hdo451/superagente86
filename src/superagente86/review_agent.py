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
            self._model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self._model = None

    @property
    def enabled(self) -> bool:
        return self._model is not None

    def review_document_text(self, content: str) -> ReviewFeedback:
        """Review document content as text (cheaper, faster)"""
        if not self._model:
            return ReviewFeedback(
                is_good=True,
                issues=[],
                suggestions=[],
                summary="Review disabled (no API key)"
            )

        prompt = """Eres un revisor de documentos. Analiza el siguiente reporte de newsletters y evalúa:

1. ¿Es fácil de leer y entender?
2. ¿La estructura es clara?
3. ¿Hay información redundante o confusa?
4. ¿Los resúmenes son útiles?
5. ¿Falta algo importante?

Responde en español con este formato exacto:
CALIDAD: [BUENA/REGULAR/MALA]
PROBLEMAS:
- problema 1
- problema 2
SUGERENCIAS:
- sugerencia 1
- sugerencia 2
RESUMEN: [una línea resumiendo tu evaluación]

Si no hay problemas, escribe "Ninguno" en PROBLEMAS.

DOCUMENTO A REVISAR:
"""
        try:
            response = self._model.generate_content(prompt + content[:8000])
            return self._parse_response(response.text)
        except Exception as e:
            return ReviewFeedback(
                is_good=True,
                issues=[f"Error en revisión: {str(e)}"],
                suggestions=[],
                summary="No se pudo completar la revisión"
            )

    def review_document_image(self, image_bytes: bytes) -> ReviewFeedback:
        """Review document as image (visual analysis)"""
        if not self._model:
            return ReviewFeedback(
                is_good=True,
                issues=[],
                suggestions=[],
                summary="Review disabled (no API key)"
            )

        prompt = """Eres un revisor de diseño de documentos. Mira esta imagen de un reporte y evalúa:

1. ¿Es visualmente atractivo y fácil de escanear?
2. ¿La jerarquía visual es clara (títulos, secciones)?
3. ¿Hay demasiado texto junto?
4. ¿Los espacios en blanco son adecuados?
5. ¿Se distinguen bien las secciones?

Responde en español con este formato exacto:
CALIDAD: [BUENA/REGULAR/MALA]
PROBLEMAS:
- problema 1
- problema 2
SUGERENCIAS:
- sugerencia 1
- sugerencia 2
RESUMEN: [una línea resumiendo tu evaluación visual]

Si no hay problemas, escribe "Ninguno" en PROBLEMAS.
"""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            response = self._model.generate_content([prompt, image])
            return self._parse_response(response.text)
        except Exception as e:
            return ReviewFeedback(
                is_good=True,
                issues=[f"Error en revisión visual: {str(e)}"],
                suggestions=[],
                summary="No se pudo completar la revisión visual"
            )

    def _parse_response(self, text: str) -> ReviewFeedback:
        lines = text.strip().split("\n")
        
        is_good = True
        issues = []
        suggestions = []
        summary = ""
        
        section = None
        for line in lines:
            line = line.strip()
            if line.startswith("CALIDAD:"):
                quality = line.replace("CALIDAD:", "").strip().upper()
                is_good = quality == "BUENA"
            elif line.startswith("PROBLEMAS:"):
                section = "problems"
            elif line.startswith("SUGERENCIAS:"):
                section = "suggestions"
            elif line.startswith("RESUMEN:"):
                summary = line.replace("RESUMEN:", "").strip()
                section = None
            elif line.startswith("- ") or line.startswith("• "):
                item = line[2:].strip()
                if item.lower() != "ninguno":
                    if section == "problems":
                        issues.append(item)
                    elif section == "suggestions":
                        suggestions.append(item)
        
        return ReviewFeedback(
            is_good=is_good,
            issues=issues,
            suggestions=suggestions,
            summary=summary or "Revisión completada"
        )
