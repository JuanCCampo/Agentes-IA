"""Bus de eventos en memoria: los agentes publican, el dashboard escucha por SSE."""
import asyncio

from . import db

_suscriptores: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None


def iniciar(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _entregar(ev: dict) -> None:
    for cola in list(_suscriptores):
        try:
            cola.put_nowait(ev)
        except asyncio.QueueFull:
            pass


def suscribir() -> asyncio.Queue:
    cola: asyncio.Queue = asyncio.Queue(maxsize=200)
    _suscriptores.add(cola)
    return cola


def desuscribir(cola: asyncio.Queue) -> None:
    _suscriptores.discard(cola)


def publicar(agente: str, tipo: str, mensaje: str, datos: dict | None = None) -> None:
    """Se puede llamar desde cualquier hilo (los agentes trabajan en hilos)."""
    ev = db.registrar_evento(agente, tipo, mensaje, datos)
    if _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(_entregar, ev)
