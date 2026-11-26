"""🛰️ Recolector: trae contratos nuevos de SECOP II (o del generador demo)."""
from .. import db, fuentes
from ..config import FUENTE
from .base import Agente

CAMPOS = ["id", "entidad", "nit_entidad", "departamento", "ciudad", "objeto", "tipo",
          "modalidad", "estado", "proveedor", "doc_proveedor", "valor", "fecha_firma",
          "fecha_inicio", "fecha_fin", "url", "fuente"]


class Recolector(Agente):
    nombre = "recolector"
    emoji = "🛰️"
    descripcion = "Consulta SECOP II y guarda los contratos nuevos"

    def __init__(self, intervalo: int):
        super().__init__(intervalo)
        self.fuente = FUENTE
        self.fallos_secop = 0

    def _traer(self) -> list[dict]:
        if self.fuente == "secop":
            try:
                datos = fuentes.obtener_secop(limite=50)
                self.fallos_secop = 0
                return datos
            except Exception as e:
                self.fallos_secop += 1
                self.log("aviso", f"SECOP no respondió ({type(e).__name__}). Intento {self.fallos_secop}/3")
                if self.fallos_secop >= 3:
                    self.fuente = "demo"
                    self.log("aviso", "Cambio a fuente DEMO para no detener la plataforma")
                return []
        return fuentes.generar_demo()

    def ciclo(self) -> str:
        contratos = self._traer()
        nuevos = 0
        for c in contratos:
            valores = [c.get(k) for k in CAMPOS] + [db.ahora()]
            if db.ex(f"INSERT OR IGNORE INTO contratos ({','.join(CAMPOS)},creado) "
                     f"VALUES ({','.join('?' * (len(CAMPOS) + 1))})", valores):
                nuevos += 1
        msg = f"Revisé {len(contratos)} contratos en {self.fuente.upper()}: {nuevos} nuevos"
        self.log("recoleccion" if nuevos else "latido", msg, {"nuevos": nuevos})
        return msg
