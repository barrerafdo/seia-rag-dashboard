import os
from pathlib import Path

# --- SEIA CONFIG ---
BASE_URL = "https://seia.sea.gob.cl"
API_BASE_URL = "https://api.buscadorambiental.dss.cl"

# --- FILTROS DE BÚSQUEDA ---
ANIO_DESDE = 1994
ANIO_HASTA = 2030
LIMIT_SCAN = 5000  # Tamaño del lote por defecto
MAX_PROJECTS = 500  # Máximo de proyectos de minería a encontrar

# --- DIRECTORIOS ---
BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "dataset_rag"

# --- DOCUMENTOS PRIORITARIOS ---
PRIORITY_KEYWORDS = [
    "ESTUDIO DE IMPACTO", "ADENDA", "ICE", "INFORME CONSOLIDADO",
    "RESOLUCIÓN EXENTA", "ICSARA", "OBSERVACIONES", "RCA", "EXTRACTO"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
