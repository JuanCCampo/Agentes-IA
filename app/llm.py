"""Envoltorio mínimo sobre la API de Claude (SDK oficial de Anthropic).

Todos los agentes piden respuestas en JSON con esquema (structured outputs), así
el código nunca tiene que "adivinar" el formato de la respuesta.
Si no hay credenciales, USAR_IA es False y los agentes trabajan sólo con reglas.
"""
import json
import logging

import anthropic

from .config import MODELO, USAR_IA

log = logging.getLogger("veedor.llm")
_cliente: anthropic.Anthropic | None = None


class IANoDisponible(Exception):
    pass


def cliente() -> anthropic.Anthropic:
    global _cliente
    if not USAR_IA:
        raise IANoDisponible("Sin ANTHROPIC_API_KEY: modo sólo-reglas")
    if _cliente is None:
        _cliente = anthropic.Anthropic(max_retries=3, timeout=120)
    return _cliente


def pedir_json(sistema: str, usuario: str, esquema: dict, esfuerzo: str = "low",
               max_tokens: int = 4000) -> dict:
    """Llama a Claude y devuelve un dict validado contra `esquema`."""
    resp = cliente().beta.messages.create(
        model=MODELO,
        max_tokens=max_tokens,
        system=sistema,
        messages=[{"role": "user", "content": usuario}],
        output_config={"effort": esfuerzo,
                       "format": {"type": "json_schema", "schema": esquema}},
        # Si el modelo principal declina, la API reintenta con un modelo de respaldo.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise IANoDisponible("La IA declinó la solicitud")
    if resp.stop_reason == "max_tokens":
        raise IANoDisponible("Respuesta truncada (max_tokens)")
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(texto)


def objeto(props: dict, requeridos: list[str] | None = None) -> dict:
    """Ayudante para escribir esquemas JSON más cortos."""
    return {"type": "object", "properties": props,
            "required": requeridos or list(props), "additionalProperties": False}
