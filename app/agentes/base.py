"""Clase base: un agente es un bucle infinito que ejecuta `ciclo()` cada N segundos."""
import asyncio
import time
import traceback

from .. import bus, db


class Agente:
    nombre = "agente"
    emoji = "🤖"
    descripcion = ""

    def __init__(self, intervalo: int):
        self.intervalo = intervalo
        self.estado = "detenido"      # trabajando | esperando | pausado | error | detenido
        self.pausado = False
        self.ciclos = 0
        self.errores_seguidos = 0
        self.ultimo_latido = 0.0
        self.ultimo_mensaje = ""
        self.tarea: asyncio.Task | None = None

    # --- a implementar por cada agente (síncrono, corre en un hilo) ---
    def ciclo(self) -> str | None:
        raise NotImplementedError

    # --- utilidades ---
    def log(self, tipo: str, mensaje: str, datos: dict | None = None) -> None:
        self.ultimo_mensaje = mensaje
        bus.publicar(self.nombre, tipo, mensaje, datos)

    def info(self) -> dict:
        return {
            "nombre": self.nombre, "emoji": self.emoji, "descripcion": self.descripcion,
            "estado": self.estado, "ciclos": self.ciclos, "intervalo": self.intervalo,
            "ultimo_latido": self.ultimo_latido, "ultimo_mensaje": self.ultimo_mensaje,
            "errores_seguidos": self.errores_seguidos,
        }

    async def correr(self) -> None:
        self.log("inicio", f"{self.emoji} {self.nombre} en línea")
        while True:
            self.ultimo_latido = time.time()
            if self.pausado:
                self.estado = "pausado"
                await asyncio.sleep(2)
                continue
            self.estado = "trabajando"
            try:
                resultado = await asyncio.to_thread(self.ciclo)
                self.ciclos += 1
                self.errores_seguidos = 0
                if resultado:
                    self.ultimo_mensaje = resultado
                self.estado = "esperando"
                espera = self.intervalo
            except Exception as e:  # el agente nunca muere: registra y reintenta con backoff
                self.errores_seguidos += 1
                self.estado = "error"
                self.log("error", f"{type(e).__name__}: {e}",
                         {"traza": traceback.format_exc()[-1500:]})
                espera = min(self.intervalo * 2 ** self.errores_seguidos, 600)
            self.ultimo_latido = time.time()
            await asyncio.sleep(espera)


def contar(sql: str, params=()) -> int:
    fila = db.q1(sql, params)
    return list(fila.values())[0] if fila else 0
