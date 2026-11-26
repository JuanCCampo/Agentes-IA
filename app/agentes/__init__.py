"""Orquestador: crea, arranca y reinicia el equipo de agentes."""
import asyncio

from ..config import INTERVALOS
from .auditor import Auditor
from .investigador import Investigador
from .recolector import Recolector
from .redactor import Redactor
from .supervisor import Supervisor


class Orquestador:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.agentes = {
            "recolector": Recolector(INTERVALOS["recolector"]),
            "auditor": Auditor(INTERVALOS["auditor"]),
            "investigador": Investigador(INTERVALOS["investigador"]),
            "redactor": Redactor(INTERVALOS["redactor"]),
        }
        self.agentes["supervisor"] = Supervisor(INTERVALOS["supervisor"], self)

    def _lanzar(self, nombre: str) -> None:
        a = self.agentes[nombre]
        if a.tarea and not a.tarea.done():
            a.tarea.cancel()
        a.tarea = self.loop.create_task(a.correr(), name=nombre)

    def iniciar(self) -> None:
        self.loop = asyncio.get_running_loop()
        for nombre in self.agentes:
            self._lanzar(nombre)

    def reiniciar(self, nombre: str) -> None:
        """Seguro de llamar desde cualquier hilo."""
        self.loop.call_soon_threadsafe(self._lanzar, nombre)

    async def detener(self) -> None:
        for a in self.agentes.values():
            if a.tarea:
                a.tarea.cancel()
        await asyncio.gather(*(a.tarea for a in self.agentes.values() if a.tarea), return_exceptions=True)
