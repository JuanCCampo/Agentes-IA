"""🧭 Supervisor: vigila a los demás agentes y los revive si se caen o se cuelgan."""
import time

from .base import Agente, contar


class Supervisor(Agente):
    nombre = "supervisor"
    emoji = "🧭"
    descripcion = "Monitorea la salud del equipo y reinicia agentes caídos"

    def __init__(self, intervalo: int, orquestador):
        super().__init__(intervalo)
        self.orq = orquestador

    def ciclo(self) -> str:
        problemas = []
        for a in self.orq.agentes.values():
            if a is self or a.pausado:
                continue
            muerto = a.tarea is None or a.tarea.done()
            # "colgado": lleva más de 5 intervalos (mín. 5 min) sin latido
            colgado = a.ultimo_latido and time.time() - a.ultimo_latido > max(300, 5 * a.intervalo) \
                and a.estado == "trabajando"
            if muerto or colgado:
                problemas.append(a.nombre)
                self.log("reinicio", f"Reinicié a {a.emoji} {a.nombre} ({'caído' if muerto else 'colgado'})")
                self.orq.reiniciar(a.nombre)
            elif a.errores_seguidos >= 3:
                problemas.append(a.nombre)
                self.log("aviso", f"{a.nombre} acumula {a.errores_seguidos} errores seguidos")
        pendientes = contar("SELECT COUNT(*) FROM contratos WHERE estado_analisis='pendiente'")
        if pendientes > 200:
            self.log("aviso", f"Cola del auditor alta: {pendientes} contratos pendientes")
        return "Equipo sano ✅" if not problemas else f"Atendí: {', '.join(problemas)}"
