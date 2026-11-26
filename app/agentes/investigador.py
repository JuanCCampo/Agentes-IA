"""🕵️ Investigador: cruza contratos entre sí para encontrar patrones que un
contrato aislado no muestra (fraccionamiento, concentración de proveedores)."""
import json

from .. import db
from .auditor import UMBRAL_MINIMA_CUANTIA
from .base import Agente


def _fmt(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


class Investigador(Agente):
    nombre = "investigador"
    emoji = "🕵️"
    descripcion = "Busca patrones entre contratos: fraccionamiento y concentración"

    def _guardar(self, clave, tipo, titulo, detalle, contratos, puntaje) -> bool:
        nuevo = db.ex("""INSERT OR IGNORE INTO hallazgos (clave,tipo,titulo,detalle,contratos,puntaje,creado)
                         VALUES (?,?,?,?,?,?,?)""",
                      (clave, tipo, titulo, detalle, json.dumps(contratos), puntaje, db.ahora()))
        if not nuevo:  # ya existía: actualiza la lista de contratos (el patrón pudo crecer)
            db.ex("UPDATE hallazgos SET detalle=?, contratos=?, puntaje=? WHERE clave=?",
                  (detalle, json.dumps(contratos), puntaje, clave))
        else:
            self.log("hallazgo", titulo, {"clave": clave, "puntaje": puntaje})
        return bool(nuevo)

    def fraccionamiento(self) -> int:
        """Mismo proveedor + misma entidad + ≥3 contratos bajo el umbral en 30 días
        cuya suma sí supera el umbral → posible partición para evitar licitar."""
        grupos = db.q("""
            SELECT nit_entidad, entidad, doc_proveedor, proveedor,
                   COUNT(*) n, SUM(valor) total, GROUP_CONCAT(id) ids,
                   MIN(fecha_firma) desde, MAX(fecha_firma) hasta
            FROM contratos
            WHERE valor < ? AND doc_proveedor IS NOT NULL
              AND fecha_firma >= date('now','-30 day')
            GROUP BY nit_entidad, doc_proveedor
            HAVING n >= 3 AND total >= ?""", (UMBRAL_MINIMA_CUANTIA, UMBRAL_MINIMA_CUANTIA))
        nuevos = 0
        for g in grupos:
            ids = g["ids"].split(",")
            puntaje = min(100, 50 + 8 * g["n"])
            nuevos += self._guardar(
                f"FRAC:{g['nit_entidad']}:{g['doc_proveedor']}", "fraccionamiento",
                f"Posible fraccionamiento: {g['n']} contratos de {g['proveedor']} con {g['entidad']}",
                f"Entre {g['desde']} y {g['hasta']} la entidad firmó {g['n']} contratos con el mismo "
                f"proveedor, cada uno por debajo de {_fmt(UMBRAL_MINIMA_CUANTIA)}, que suman "
                f"{_fmt(g['total'])}. Partir un contrato grande en varios pequeños puede servir para "
                f"evitar procesos competitivos.", ids, puntaje)
        return nuevos

    def concentracion(self) -> int:
        """Un proveedor que se queda con ≥40% del valor contratado por una entidad."""
        filas = db.q("""
            WITH tot AS (SELECT nit_entidad, SUM(valor) t, COUNT(*) n FROM contratos GROUP BY nit_entidad)
            SELECT c.nit_entidad, c.entidad, c.doc_proveedor, c.proveedor, COUNT(*) n,
                   SUM(c.valor) v, tot.t, tot.n nent, GROUP_CONCAT(c.id) ids
            FROM contratos c JOIN tot USING(nit_entidad)
            WHERE c.doc_proveedor IS NOT NULL
            GROUP BY c.nit_entidad, c.doc_proveedor
            HAVING tot.n >= 6 AND n >= 2 AND v >= 0.4 * tot.t""")
        nuevos = 0
        for f in filas:
            pct = round(100 * f["v"] / f["t"]) if f["t"] else 0
            nuevos += self._guardar(
                f"CONC:{f['nit_entidad']}:{f['doc_proveedor']}", "concentracion",
                f"Concentración: {f['proveedor']} tiene el {pct}% de lo contratado por {f['entidad']}",
                f"De {f['nent']} contratos registrados de la entidad (por {_fmt(f['t'])}), "
                f"{f['n']} son de este proveedor y suman {_fmt(f['v'])} ({pct}%).",
                f["ids"].split(","), min(100, 30 + pct // 2))
        return nuevos

    def ciclo(self) -> str:
        n = self.fraccionamiento() + self.concentracion()
        msg = f"Cruce de contratos terminado: {n} hallazgos nuevos"
        if not n:
            self.log("latido", msg)
        return msg
