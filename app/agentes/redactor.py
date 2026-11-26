"""✍️ Redactor: convierte hallazgos técnicos en alertas ciudadanas y publica boletines."""
import json
from datetime import datetime, timedelta, timezone

from .. import db, llm
from ..config import BOLETIN_CADA_MIN, UMBRAL_ALERTA
from .base import Agente

SISTEMA = """Eres el Agente Redactor de Veedor IA, plataforma ciudadana de veeduría de la
contratación pública en Colombia. Escribes para ciudadanos, periodistas y veedurías.
- Tono: claro, sobrio, sin sensacionalismo. Nunca afirmes que hay corrupción: habla de
  "señales de riesgo" que "merecen revisión".
- Usa cifras en pesos colombianos con separador de miles (ej. $1.250.000.000).
- No inventes datos que no estén en la información recibida."""

ESQ_ALERTA = llm.objeto({"titulo": {"type": "string", "description": "Máx. 90 caracteres"},
                         "mensaje": {"type": "string", "description": "2 a 4 frases"}})
ESQ_BOLETIN = llm.objeto({"titulo": {"type": "string"},
                          "contenido": {"type": "string", "description": "Markdown, máx. 250 palabras"}})


def _pesos(v) -> str:
    return f"${(v or 0):,.0f}".replace(",", ".")


class Redactor(Agente):
    nombre = "redactor"
    emoji = "✍️"
    descripcion = "Escribe alertas ciudadanas y boletines periódicos"

    def _redactar(self, contexto: dict, plantilla: dict) -> dict:
        try:
            return llm.pedir_json(SISTEMA, "Redacta una alerta ciudadana a partir de:\n" +
                                  json.dumps(contexto, ensure_ascii=False, indent=1),
                                  ESQ_ALERTA, esfuerzo="low")
        except llm.IANoDisponible:
            return plantilla

    def alertas_contratos(self) -> int:
        filas = db.q("""SELECT c.* FROM contratos c
                        LEFT JOIN alertas a ON a.origen='contrato' AND a.ref=c.id
                        WHERE c.puntaje >= ? AND a.id IS NULL ORDER BY c.puntaje DESC LIMIT 3""",
                     (UMBRAL_ALERTA,))
        for c in filas:
            banderas = json.loads(c["banderas"] or "[]")
            texto = self._redactar(
                {k: c[k] for k in ["entidad", "objeto", "modalidad", "proveedor", "valor",
                                   "fecha_firma", "fecha_fin", "puntaje", "resumen"]} | {"banderas": banderas},
                {"titulo": f"Riesgo {c['puntaje']}/100 en contrato de {c['entidad'][:50]}",
                 "mensaje": f"{c['entidad']} firmó con {c['proveedor']} un contrato por {_pesos(c['valor'])} "
                            f"({c['modalidad']}). Señales: " +
                            "; ".join(b["descripcion"] for b in banderas[:3]) + "."})
            self._publicar("contrato", c["id"], c["nivel"], texto)
        return len(filas)

    def alertas_hallazgos(self) -> int:
        filas = db.q("""SELECT h.* FROM hallazgos h
                        LEFT JOIN alertas a ON a.origen='hallazgo' AND a.ref=h.clave
                        WHERE a.id IS NULL ORDER BY h.puntaje DESC LIMIT 3""")
        for h in filas:
            texto = self._redactar({"tipo": h["tipo"], "titulo": h["titulo"], "detalle": h["detalle"]},
                                   {"titulo": h["titulo"] if len(h["titulo"]) <= 90 else h["titulo"][:87].rsplit(" ", 1)[0] + "…", "mensaje": h["detalle"]})
            self._publicar("hallazgo", h["clave"], "alto" if h["puntaje"] >= 60 else "medio", texto)
        return len(filas)

    def _publicar(self, origen, ref, nivel, texto):
        if db.ex("INSERT OR IGNORE INTO alertas (origen,ref,nivel,titulo,mensaje,publicada,creado) "
                 "VALUES (?,?,?,?,?,1,?)", (origen, ref, nivel, texto["titulo"], texto["mensaje"], db.ahora())):
            self.log("alerta", f"🚨 {texto['titulo']}", {"origen": origen, "ref": ref, "nivel": nivel})

    def boletin(self) -> bool:
        ult = db.q1("SELECT creado FROM boletines ORDER BY id DESC LIMIT 1")
        if ult and datetime.fromisoformat(ult["creado"]) > datetime.now(timezone.utc) - timedelta(minutes=BOLETIN_CADA_MIN):
            return False
        stats = db.q1("""SELECT COUNT(*) total, SUM(estado_analisis='analizado') analizados,
                                SUM(nivel='alto') altos, SUM(nivel='medio') medios,
                                COALESCE(SUM(valor),0) valor, COALESCE(SUM(CASE WHEN nivel='alto' THEN valor END),0) valor_alto
                         FROM contratos""")
        if not stats["analizados"]:
            return False
        alertas = db.q("SELECT titulo, mensaje FROM alertas ORDER BY id DESC LIMIT 6")
        top_ent = db.q("""SELECT entidad, COUNT(*) n, ROUND(AVG(puntaje)) prom FROM contratos
                          WHERE puntaje IS NOT NULL GROUP BY entidad ORDER BY prom DESC LIMIT 3""")
        try:
            b = llm.pedir_json(SISTEMA, "Escribe el boletín ciudadano con estos datos:\n" + json.dumps(
                {"estadisticas": stats, "ultimas_alertas": alertas, "entidades_mayor_riesgo_promedio": top_ent},
                ensure_ascii=False, indent=1), ESQ_BOLETIN, esfuerzo="medium")
        except llm.IANoDisponible:
            lineas = [f"- **{stats['total']}** contratos vigilados, **{stats['analizados']}** analizados.",
                      f"- **{stats['altos'] or 0}** con riesgo alto, que suman {_pesos(stats['valor_alto'])}.",
                      f"- Valor total observado: {_pesos(stats['valor'])}.", "", "**Últimas alertas:**"]
            lineas += [f"- {a['titulo']}" for a in alertas]
            if top_ent:
                lineas += ["", "**Entidades con mayor riesgo promedio:**"]
                lineas += [f"- {e['entidad']} ({e['n']} contratos, promedio {e['prom']:.0f})" for e in top_ent]
            b = {"titulo": f"Boletín Veedor IA · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                 "contenido": "\n".join(lineas)}
        db.ex("INSERT INTO boletines (titulo,contenido,creado) VALUES (?,?,?)",
              (b["titulo"], b["contenido"], db.ahora()))
        self.log("boletin", f"📰 Publiqué: {b['titulo']}")
        return True

    def ciclo(self) -> str:
        n = self.alertas_contratos() + self.alertas_hallazgos()
        self.boletin()
        return f"{n} alertas redactadas en este ciclo"
