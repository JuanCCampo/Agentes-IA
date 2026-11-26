"""Configuración central de Veedor IA (todo se puede cambiar con variables de entorno)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga simple de .env (sin dependencias extra). Las variables reales del sistema tienen prioridad.
_env = BASE_DIR / ".env"
if _env.exists():
    for _linea in _env.read_text(encoding="utf-8").splitlines():
        _linea = _linea.split("#", 1)[0].strip()
        if "=" in _linea:
            _k, _v = _linea.split("=", 1)
            if _v.strip():
                os.environ.setdefault(_k.strip(), _v.strip())
DB_PATH = Path(os.getenv("VEEDOR_DB", BASE_DIR / "data" / "veedor.db"))

# Fuente de datos: "secop" (datos reales de datos.gov.co) o "demo" (generador sintético)
FUENTE = os.getenv("VEEDOR_FUENTE", "secop").lower()
SECOP_URL = os.getenv(
    "SECOP_URL", "https://www.datos.gov.co/resource/jbjy-vk9h.json"  # SECOP II - Contratos Electrónicos
)
SECOP_DEPARTAMENTO = os.getenv("SECOP_DEPARTAMENTO", "Bolívar")
SECOP_APP_TOKEN = os.getenv("SECOP_APP_TOKEN", "")  # opcional, evita límites de tasa

# Claude
MODELO = os.getenv("VEEDOR_MODELO", "claude-opus-5-5")
USAR_IA = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")) and \
    os.getenv("VEEDOR_SIN_IA", "0") != "1"

# Intervalos de cada agente (segundos)
INTERVALOS = {
    "recolector": int(os.getenv("INT_RECOLECTOR", "60")),
    "auditor": int(os.getenv("INT_AUDITOR", "10")),
    "investigador": int(os.getenv("INT_INVESTIGADOR", "45")),
    "redactor": int(os.getenv("INT_REDACTOR", "30")),
    "supervisor": int(os.getenv("INT_SUPERVISOR", "15")),
}
LOTE_AUDITOR = int(os.getenv("LOTE_AUDITOR", "5"))  # contratos por ciclo
UMBRAL_ALERTA = int(os.getenv("UMBRAL_ALERTA", "60"))  # puntaje que genera alerta
BOLETIN_CADA_MIN = int(os.getenv("BOLETIN_CADA_MIN", "30"))
