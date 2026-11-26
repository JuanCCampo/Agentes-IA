"""🧮 Auditor: analiza cada contrato nuevo y le asigna un puntaje de riesgo (0-100).

Dos capas:
1. Reglas deterministas (siempre funcionan, son explicables y baratas).
2. Claude revisa el contrato + las reglas + el historial del proveedor y emite
   el puntaje final con una explicación en lenguaje ciudadano.
"""
import json
from datetime import date

from .. import db, llm
from ..config import LOTE_AUDITOR
from .base import Agente

UMBRAL_MINIMA_CUANTIA = 100_000_000  # aproximado; en la realidad depende del presupuesto de la entidad
OBJETOS_VAGOS = ["apoyo a la gestión", "apoyo a la gestion", "servicios varios", "actividades varias"]


def nivel_de(puntaje: int) -> str:
    return "alto" if puntaje >= 60 else "medio" if puntaje >= 30 else "bajo"


def _dias(a: str | None, b: str | None) -> int | None:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def reglas(c: dict, historial: dict) -> list[dict]:
    """Devuelve las banderas rojas activadas: [{codigo, descripcion, peso}]."""
    b = []
    valor = c.get("valor") or 0
    modalidad = (c.get("modalidad") or "").lower()
    objeto = (c.get("objeto") or "").lower().strip()
    dias = _dias(c.get("fecha_inicio"), c.get("fecha_fin"))

    def add(codigo, desc, peso):
        b.append({"codigo": codigo, "descripcion": desc, "peso": peso})

    if "directa" in modalidad and valor >= 500_000_000:
        add("DIRECTA_ALTO_VALOR", "Contratación directa por más de $500 millones, sin competencia", 30)
    elif "directa" in modalidad and "servicios" not in (c.get("tipo") or "").lower():
        add("DIRECTA_NO_SERVICIOS", "Contratación directa para algo distinto a prestación de servicios", 15)
    if dias is not None and dias < 15 and valor >= 200_000_000:
        add("PLAZO_EXPRES", f"Plazo de sólo {dias} días para un contrato de alto valor", 25)
    if dias is not None and dias < 0:
        add("FECHAS_INCOHERENTES", "La fecha de fin es anterior a la de inicio", 10)
    if 0.9 * UMBRAL_MINIMA_CUANTIA <= valor < UMBRAL_MINIMA_CUANTIA:
        add("JUSTO_BAJO_UMBRAL", "Valor justo por debajo del umbral de mínima cuantía", 20)
    if len(objeto) < 35 or any(v == objeto or objeto.startswith(v) and len(objeto) < 45 for v in OBJETOS_VAGOS):
        add("OBJETO_VAGO", "El objeto del contrato es genérico o poco específico", 15)
    doc = c.get("doc_proveedor") or ""
    if doc.isdigit() and len(doc) <= 10 and not doc.startswith(("8", "9")) and valor >= 300_000_000:
        add("PERSONA_NATURAL_ALTO", "Persona natural con un contrato de más de $300 millones", 15)
    if historial["contratos_misma_entidad"] >= 3:
        add("PROVEEDOR_RECURRENTE",
            f"El proveedor ya tiene {historial['contratos_misma_entidad']} contratos con esta entidad", 15)
    if not c.get("proveedor"):
        add("SIN_PROVEEDOR", "No se reporta proveedor adjudicado", 10)
    return b


def historial_proveedor(c: dict) -> dict:
    fila = db.q1("""SELECT COUNT(*) n, COALESCE(SUM(valor),0) total FROM contratos
                    WHERE doc_proveedor=? AND nit_entidad=? AND id<>?""",
                 (c.get("doc_proveedor"), c.get("nit_entidad"), c["id"]))
    fila2 = db.q1("SELECT COUNT(*) n FROM contratos WHERE doc_proveedor=? AND id<>?",
                  (c.get("doc_proveedor"), c["id"]))
    return {"contratos_misma_entidad": fila["n"], "valor_misma_entidad": fila["total"],
            "contratos_totales": fila2["n"]}


SISTEMA = """Eres el Agente Auditor de Veedor IA, una plataforma ciudadana que vigila la
contratación pública en Colombia (SECOP II). Evalúas el riesgo de un contrato
siguiendo buenas prácticas de control (Ley 80 de 1993, Ley 1150 de 2007, guías de
Colombia Compra Eficiente y alertas de la Contraloría).

Reglas de comportamiento:
- Un puntaje alto NO es una acusación: indica que el contrato merece revisión ciudadana.
- Basa tu juicio sólo en los datos entregados; si falta información dilo, no inventes.
- Las banderas automáticas pueden ser falsos positivos: confírmalas o descártalas con criterio.
- Escribe el resumen en español claro, para un ciudadano sin formación jurídica (máx. 3 frases).
- Escala: 0-29 bajo, 30-59 medio, 60-100 alto."""

ESQUEMA = llm.objeto({
    "puntaje": {"type": "integer", "description": "Riesgo de 0 a 100"},
    "resumen": {"type": "string"},
    "banderas": {"type": "array", "items": llm.objeto({
        "codigo": {"type": "string"}, "descripcion": {"type": "string"},
        "peso": {"type": "integer"}})},
    "recomendacion": {"type": "string", "description": "Qué debería verificar un ciudadano o veedor"},
})


class Auditor(Agente):
    nombre = "auditor"
    emoji = "🧮"
    descripcion = "Califica el riesgo de cada contrato con reglas + IA"

    def analizar(self, c: dict) -> dict:
        hist = historial_proveedor(c)
        banderas = reglas(c, hist)
        base = min(100, sum(x["peso"] for x in banderas))
        resultado = {"puntaje": base, "banderas": banderas, "motor": "reglas",
                     "resumen": "; ".join(x["descripcion"] for x in banderas) or
                                "No se detectaron señales de riesgo con las reglas automáticas.",
                     "recomendacion": ""}
        try:
            datos = {k: c.get(k) for k in ["entidad", "ciudad", "objeto", "tipo", "modalidad", "estado",
                                           "proveedor", "doc_proveedor", "valor", "fecha_firma",
                                           "fecha_inicio", "fecha_fin"]}
            ia = llm.pedir_json(
                SISTEMA,
                "Contrato:\n" + json.dumps(datos, ensure_ascii=False, indent=1) +
                "\n\nHistorial del proveedor en nuestra base:\n" + json.dumps(hist) +
                f"\n\nBanderas automáticas (puntaje base {base}):\n" +
                json.dumps(banderas, ensure_ascii=False, indent=1) +
                "\n\nDevuelve tu evaluación final.",
                ESQUEMA, esfuerzo="low")
            ia["puntaje"] = max(0, min(100, int(ia["puntaje"])))
            resultado = {**ia, "motor": "ia"}
        except llm.IANoDisponible:
            pass
        return resultado

    def ciclo(self) -> str:
        pendientes = db.q("SELECT * FROM contratos WHERE estado_analisis='pendiente' "
                          "ORDER BY valor DESC LIMIT ?", (LOTE_AUDITOR,))
        if not pendientes:
            return "Sin contratos pendientes"
        for c in pendientes:
            try:
                r = self.analizar(c)
            except Exception as e:
                db.ex("UPDATE contratos SET estado_analisis='error' WHERE id=?", (c["id"],))
                self.log("error", f"No pude analizar {c['id']}: {e}")
                continue
            nivel = nivel_de(r["puntaje"])
            resumen = r["resumen"] + (f"\n\nQué revisar: {r['recomendacion']}" if r.get("recomendacion") else "")
            db.ex("""UPDATE contratos SET estado_analisis='analizado', puntaje=?, nivel=?,
                     resumen=?, banderas=? WHERE id=?""",
                  (r["puntaje"], nivel, resumen, json.dumps(r["banderas"], ensure_ascii=False), c["id"]))
            self.log("analisis",
                     f"{c['id']} → riesgo {r['puntaje']} ({nivel}) · {(c['entidad'] or '')[:40]} · motor {r['motor']}",
                     {"contrato": c["id"], "puntaje": r["puntaje"], "nivel": nivel})
        return f"Analicé {len(pendientes)} contratos"
