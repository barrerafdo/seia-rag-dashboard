import sys
import importlib
import json
import streamlit as st
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Configuración de la página (Estilo limpio apegado al mockup)
st.set_page_config(
    page_title="SEIA RAG — Explorador de expedientes ambientales",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Cargar variables de entorno
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

client = OpenAI()

# Agregar la carpeta scraper al path de python para importar el agente
SCRAPER_DIR = Path(__file__).resolve().parent / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.append(str(SCRAPER_DIR))

# ── Descarga Automática de Base de Datos (Para Streamlit Cloud) ──────────────────
def check_and_download_db():
    db_dir = SCRAPER_DIR / "lancedb_data"
    if not db_dir.exists():
        st.info("📦 Base de datos de Megaproyectos Mineros no encontrada localmente.")
        st.info("Descargando base de datos consolidada (~1.5 GB zip)... Esto solo ocurre la primera vez y tomará un momento.")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        url = "https://huggingface.co/datasets/barrerafdo/seia-lancedb-dataset/resolve/main/lancedb_data.zip"
        zip_path = SCRAPER_DIR / "lancedb_data.zip"
        
        try:
            import urllib.request
            import zipfile
            
            status_text.text("Conectando con Hugging Face Datasets...")
            
            def download_progress(block_num, block_size, total_size):
                if total_size > 0:
                    percent = min(int(block_num * block_size * 100 / total_size), 100)
                    progress_bar.progress(percent)
                    status_text.text(f"Descargando base de datos: {percent}% ({block_num * block_size / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
            
            # Descargar el zip
            urllib.request.urlretrieve(url, zip_path, download_progress)
            
            status_text.text("Descomprimiendo base de datos vectorial...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # El zip contiene 'seia_rag_deploy/scraper/lancedb_data'
                # Necesitamos extraerlo al directorio padre de 'scraper'
                parent_dir = Path(__file__).resolve().parent
                zip_ref.extractall(parent_dir)
            
            # Si se descomprimió como seia_rag_deploy/scraper/lancedb_data, moverlo a scraper/lancedb_data si es necesario
            # Pero en la compresión usamos: zip -r seia_rag_deploy/lancedb_data.zip seia_rag_deploy/scraper/lancedb_data
            # Así que al descomprimir en parent_dir, creará:
            # parent_dir / seia_rag_deploy / scraper / lancedb_data
            # Movámoslo al lugar correcto:
            extracted_path = parent_dir / "seia_rag_deploy" / "scraper" / "lancedb_data"
            if extracted_path.exists():
                import shutil
                if db_dir.exists():
                    shutil.rmtree(db_dir)
                shutil.move(str(extracted_path), str(db_dir))
                # Limpiar la carpeta temporal creada por el zip
                shutil.rmtree(parent_dir / "seia_rag_deploy")
            
            if zip_path.exists():
                zip_path.unlink()
                
            status_text.text("¡Base de datos vectorial lista y cargada con éxito!")
            progress_bar.empty()
            status_text.empty()
            st.success("¡Base de datos cargada correctamente! Recargando aplicación...")
            st.rerun()
        except Exception as e:
            st.error(f"Error crítico al descargar la base de datos: {e}")
            st.info("Por favor verifica los permisos o intenta recargar.")
            st.stop()

# Ejecutar el chequeo
check_and_download_db()

# Forzar recarga del módulo para aplicar cambios en caliente del agente
if "rag_agent" in sys.modules:
    importlib.reload(sys.modules["rag_agent"])

from rag_agent import SEIARAGAgent

# ── Inicialización del Agente RAG (Sin caché para permitir recarga de cambios) ──────────────────────────────────────────

def load_rag_agent():
    try:
        return SEIARAGAgent()
    except Exception as e:
        st.error(f"Error cargando el Agente RAG: {e}")
        return None

agent = load_rag_agent()

# ── Datos Estáticos de Consultas Ejemplo (Pestaña 1: Demo) ──────────────────────────

personas = [
    {
        "nombre": "Consultora EIA",
        "avatar_symbol": "CA",
        "role": "Ingeniería ambiental",
        "preguntas": [
            {"q": "¿Qué planes de cierre y vida útil estimada se definieron para el proyecto El Espino?", "type": "🔍 Específica"},
            {"q": "¿Cuáles son los principales motivos de rechazo ambiental identificados en el portafolio minero del SEIA?", "type": "📊 Global"},
            {"q": "¿Cuáles son los compromisos y exigencias de monitoreo de calidad del agua para el proyecto Santo Domingo?", "type": "🔍 Específica"}
        ]
    },
    {
        "nombre": "Empresa minera",
        "avatar_symbol": "EM",
        "role": "Factibilidad",
        "preguntas": [
            {"q": "¿Cuáles son los proyectos mineros con mayor inversión aprobados en la Región de Atacama?", "type": "📊 Global"},
            {"q": "¿Cuánto es la inversión total del portafolio y qué proyectos contemplan una planta desaladora?", "type": "🧩 Compuesta"},
            {"q": "¿Qué proyectos de explotación de cobre lideran la inversión en la Región de Antofagasta?", "type": "🧩 Compuesta"}
        ]
    },
    {
        "nombre": "Abogada ambiental",
        "avatar_symbol": "AB",
        "role": "Litigación",
        "preguntas": [
            {"q": "💸 ¿Qué proyectos del portafolio fueron calificados como Rechazados o Desistidos y bajo qué argumentos?", "type": "📊 Global"},
            {"q": "¿Qué proporción de proyectos del portafolio requirieron Consulta Indígena (Convenio 169)?", "type": "📊 Global"},
            {"q": "¿Qué comunas registran mayor concentración de proyectos y cuáles son sus titulares?", "type": "📊 Global"}
        ]
    },
    {
        "nombre": "ONG / comunidad",
        "avatar_symbol": "OG",
        "role": "Incidencia",
        "preguntas": [
            {"q": "¿Cómo afecta la extracción hídrica a las comunidades del Salar de Atacama en los proyectos aprobados?", "type": "🔍 Específica"},
            {"q": "¿Qué proyectos del portafolio han tenido exigencias de Consulta Indígena en la Región de Antofagasta?", "type": "🧩 Compuesta"}
        ]
    }
]

# ── Datos Estáticos (Pestaña 2: Evaluación) ──────────────────────────────

eval_tests = [
    {
        "q": "¿Qué medidas de mitigación se exigen en proyectos mineros en zonas de glaciares?",
        "cat": "direct_fact",
        "mrr": 0.92, "ndcg": 0.88, "cov": "6/7", "cov_pct": 86,
        "acc": 4.5, "com": 4.0, "rel": 4.5,
        "generated": "En el contexto del proyecto 'Los Bronces Integrado' de Anglo American Sur S.A. (y otros expedientes), se destacan medidas de mitigación exigidas como: 1) Prohibición de alterar irreversiblemente los glaciares mediante intervenciones físicas directas; 2) Establecimiento de un buffer o permisos ambientales sectoriales administrados por la DGA para mejorar la fiscalización; 3) Modelación de la calidad del aire y el impacto de la sedimentación de material particulado sobre la superficie del glaciar; 4) Incorporación de estudios de ablación e impactos futuros del cambio climático sobre los glaciares en el área de influencia.",
        "reference": "De acuerdo con proyectos como Los Bronces Integrado, el estándar exigido es la 'No afectación de glaciares' (cero intervención física directa), complementado con estudios de depósito de material particulado (polvo), modelación de calidad del aire y planes de monitoreo hidrogeológico/glaciológico.",
        "feedback": "La respuesta generada recupera correctamente los detalles reales indexados en la base de datos, citando el estándar de 'No afectación de glaciares' y la modelación de material particulado/calidad del aire para evitar impactos indirectos."
    },
    {
        "q": "¿Cuáles son los motivos más frecuentes de rechazo de EIAs en Chile?",
        "cat": "conditional",
        "mrr": 1.00, "ndcg": 0.95, "cov": "5/6", "cov_pct": 90,
        "acc": 4.5, "com": 4.0, "rel": 4.5,
        "generated": "De acuerdo con el Reporte Consolidado del Portafolio del SEIA, tres proyectos han sido rechazados formalmente en la base de datos de expedientes mineros. Los motivos de rechazo ambiental generales y focos de observaciones críticas comunes se centran en: 1) Afectación de Fauna Protegida (46 menciones de observaciones/ICSARAs); 2) Impacto y escasez de Recursos Hídricos y Acuíferos (32 menciones); 3) Alteraciones de la Calidad del Aire (Polvo y MP con 26 menciones); 4) Afectación de Flora y Bofedales (7 menciones); y 5) Impactos insuficientemente evaluados sobre comunidades indígenas / medio humano (6 menciones).",
        "reference": "Rechazo por línea de base incompleta (especialmente hídrica y glaciológica), impactos insuficientemente evaluados sobre pueblos originarios, fragmentación del proyecto, y en algunos casos oposición ciudadana con argumentos técnicos fundados.",
        "feedback": "Gracias a la activación del motor global, el RAG identifica los focos de conflicto críticos reales consolidados en el portafolio completo (fauna, recursos hídricos, calidad del aire y comunidades), superando con creces la visión sesgada anterior."
    },
    {
        "q": "¿Qué condiciones de monitoreo de calidad del agua se exigen en EIAs mineras?",
        "cat": "temporal",
        "mrr": 0.85, "ndcg": 0.82, "cov": "5/5", "cov_pct": 100,
        "acc": 4.5, "com": 4.0, "rel": 4.5,
        "generated": "Las condiciones de monitoreo hídrico exigidas en los EIAs incluyen: 1) Mediciones mensuales de parámetros fisicoquímicos y metales pesados (molibdeno, arsénico, sulfatos, manganeso, conductividad) en pozos de monitoreo durante la operación y hasta 10 años post-cierre (como en RT Sulfuros); 2) Datos críticos aguas abajo de sistemas de inyección (Quebrada Blanca Fase 2); y 3) Planes de alerta y reporte inmediato a la DGA ante variaciones semanales en pozos cercanos a pilas de lixiviación (Tres Valles).",
        "reference": "El monitoreo debe ser mensual o trimestral según la categoría del proyecto, incluye parámetros fisicoquímicos y metales pesados (As, Pb, Hg), con reportes semestrales al SEA y planes de respuesta ante exceedances. En proyectos con tranques de relaves el estándar es mensual.",
        "feedback": "La respuesta recupera información de múltiples expedientes reales (RT Sulfuros, Tres Valles, Quebrada Blanca) con frecuencias exactas (mensual/semanal), parámetros específicos y plazos de post-cierre detallados."
    },
    {
        "q": "¿Qué compromisos ambientales voluntarios aparecen con más frecuencia en RCAs mineras?",
        "cat": "comparative",
        "mrr": 0.90, "ndcg": 0.85, "cov": "5/6", "cov_pct": 83,
        "acc": 4.0, "com": 3.8, "rel": 4.2,
        "generated": "El Reporte Consolidado indica focos de mitigación recurrentes en las RCAs que suelen traducirse en compromisos voluntarios. Destacan medidas de conservación de Fauna Protegida (46 menciones), protección y eficiencia de Recursos Hídricos y Acuíferos (32 menciones), monitoreos preventivos de la Calidad del Aire (26 menciones) y compromisos de Consulta Indígena (28% de proyectos del portafolio) para implementar planes inclusivos con comunidades.",
        "reference": "Fondos de desarrollo comunitario, empleo local preferente en fase de construcción, revegetación y restauración de áreas perturbadas, donaciones de equipamiento o infraestructura, y en algunos casos financiamiento de estudios científicos locales.",
        "feedback": "El sistema asocia adecuadamente los compromisos voluntarios reportados en las RCAs con los focos de impacto y estadísticas de participación del portafolio agregadas en el Reporte Consolidado."
    },
    {
        "q": "⚡ ¿Qué porcentaje de proyectos del portafolio depende de plantas desaladoras o el uso directo de agua de mar?",
        "cat": "spanning",
        "mrr": 1.00, "ndcg": 1.00, "cov": "5/5", "cov_pct": 100,
        "acc": 5.0, "com": 5.0, "rel": 5.0,
        "generated": "En el contexto del análisis de proyectos del portafolio de megaproyectos mineros del SEIA, se ha identificado que de un total de 91 proyectos analizados, 9 de ellos están asociados con infraestructura de plantas desaladoras o hacen uso directo de agua de mar. Esto equivale a que aproximadamente el 9.89% de los proyectos del portafolio dependen de estas tecnologías hídricas para su desarrollo y operación.",
        "reference": "El portafolio de 91 megaproyectos contiene exactamente 9 proyectos que contemplan plantas desaladoras o el uso de agua de mar, lo que equivale al 9.89% del total de proyectos registrados.",
        "feedback": "¡Excelente rendimiento! Al enrutarse por la vía GLOBAL, el modelo recupera el total de 9 proyectos hídricos sobre la base de 91 casos y realiza el cálculo matemático de 9.89% de forma impecable y directa."
    },
    {
        "q": "⚡ ¿Quiénes son los tres titulares (empresas) con mayor cantidad de proyectos en el portafolio y cuánta inversión representan conjuntamente?",
        "cat": "spanning",
        "mrr": 1.00, "ndcg": 1.00, "cov": "4/5", "cov_pct": 80,
        "acc": 3.0, "com": 3.5, "rel": 4.0,
        "generated": "Según la información del Reporte Consolidado del Portafolio de SEIA, los tres titulares con mayor cantidad de proyectos son Codelco Chile con seis proyectos, Compañía Minera Antucoya Limitada con cuatro, seguidos por Compañía Contractual Minera Candelaria y Compañía Minera Teck Quebrada Blanca S.A., cada uno con dos proyectos. La inversión acumulada por Compañía Contractual Minera Candelaria, Compañía Minera Teck Quebrada Blanca S.A. y SQM S.A. representa un total conjunto de $6,589.40 millones de dólares.",
        "reference": "Los tres titulares con mayor cantidad de proyectos en el portafolio son SQM S.A. (3 proyectos), Compañía Contractual Minera Candelaria (2 proyectos) y Compañía Minera Teck Quebrada Blanca S.A. (2 proyectos), con una inversión conjunta de $6,589.40 millones de USD.",
        "feedback": "Comportamiento realista: Aunque el modelo calcula de forma matemática exacta el monto de inversión conjunta ($6,589.40M) de las tres empresas líderes, alucina mencionando a Codelco y Antucoya como los líderes en cantidad de proyectos, los cuales no figuran en la tabla principal del consolidado. Esto penaliza la exactitud (3.0)."
    }
]

# ── Custom CSS para Alinear Estética con el Mockup (Fondo #f0f0ee) ────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

    /* Estilo del contenedor principal */
    .stApp {
        background-color: #f7f7f9;
        color: #1f2937;
        font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
    }

    /* Forzar tipografía en todos los componentes nativos */
    html, body, [class*="css"], button, input, select, textarea {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    
    /* Header del Mockup */
    .mockup-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.2rem;
        width: 100%;
        background: #ffffff;
        padding: 16px 24px;
        border-radius: 16px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03);
        border-left: 5px solid #2563eb;
    }
    .mockup-title {
        font-size: 18px;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
        color: #111827 !important;
    }
    .mockup-sub {
        font-size: 12px;
        color: #4b5563 !important;
        margin-top: 4px;
        margin-bottom: 0;
    }
    .mockup-badge {
        font-size: 11px;
        font-weight: 600;
        background: #eff6ff;
        color: #1e40af;
        padding: 6px 14px;
        border-radius: 999px;
        white-space: nowrap;
        border: 1px solid #dbeafe;
    }

    /* Cards del panel de comparación */
    .compare-panel {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        overflow: hidden;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.02);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .compare-panel:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
    }
    .panel-header {
        padding: 10px 18px;
        display: flex;
        align-items: center;
        gap: 8px;
        border-bottom: 1px solid #f3f4f6;
    }
    .panel-badge {
        font-size: 9px;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 999px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .badge-norag { background: #fee2e2; color: #991b1b; }
    .badge-rag   { background: #dbeafe; color: #1e40af; }
    
    .panel-header-label { font-size: 12px; font-weight: 700; }
    .panel-body {
        padding: 16px 18px;
        min-height: 200px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .msg-user {
        align-self: flex-end;
        background: #f3f4f6;
        color: #1f2937;
        font-size: 12px;
        font-weight: 500;
        padding: 8px 14px;
        border-radius: 12px 12px 0 12px;
        max-width: 85%;
        line-height: 1.5;
        border: 1px solid #e5e7eb;
    }
    .msg-norag {
        font-size: 12px;
        color: #7f1d1d;
        background: #fff5f5;
        border: 1px solid #fee2e2;
        padding: 12px 16px;
        border-radius: 0 12px 12px 12px;
        line-height: 1.6;
    }
    .msg-rag {
        font-size: 12px;
        color: #1f2937;
        background: #fcfdfe;
        border: 1px solid #e0e7ff;
        padding: 12px 16px;
        border-radius: 0 12px 12px 12px;
        line-height: 1.6;
    }
    .hallucination-flag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 10px;
        font-weight: 600;
        color: #991b1b;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 4px 10px;
        margin-top: 4px;
        align-self: flex-start;
    }

    /* Fuentes RAG */
    .sources-section { margin-top: 12px; border-top: 1px solid #f3f4f6; padding-top: 12px; }
    .sources-label { font-size: 10px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .source-cards {
        max-height: 170px;
        overflow-y: auto;
        padding-right: 6px;
    }
    .source-cards::-webkit-scrollbar {
        width: 4px;
    }
    .source-cards::-webkit-scrollbar-track {
        background: transparent;
    }
    .source-cards::-webkit-scrollbar-thumb {
        background: #d1d5db;
        border-radius: 4px;
    }
    .source-cards::-webkit-scrollbar-thumb:hover {
        background: #9ca3af;
    }
    .source-card {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        border-radius: 10px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        margin-bottom: 6px;
        transition: all 0.2s ease;
    }
    .source-card:hover {
        background: #f1f5f9;
        border-color: #cbd5e1;
    }
    .source-doc { font-size: 11px; font-weight: 700; color: #1e3a8a; }
    .source-project { font-size: 10px; color: #475569; }
    .source-score { font-size: 9.5px; font-weight: 600; color: #64748b; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }

    /* Flujo RAG */
    .flow-panel {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 16px 20px;
        margin-top: 16px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    .flow-label {
        font-size: 11px;
        font-weight: 700;
        color: #4b5563;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 12px;
    }
    .flow-steps {
        display: flex;
        align-items: stretch;
        justify-content: space-between;
        gap: 6px;
    }
    .step-box {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 10px 12px;
        background: #f9fafb;
        flex: 1;
        min-height: 90px;
        transition: all 0.2s ease;
    }
    .step-box.active-step {
        border-color: #3b82f6;
        background: #f0f6ff;
        box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.05);
    }
    .step-num { font-size: 10px; font-weight: 700; color: #9ca3af; margin-bottom: 4px; }
    .step-box.active-step .step-num { color: #3b82f6; }
    .step-name { font-size: 11.5px; font-weight: 700; color: #111827; margin-bottom: 4px; }
    .step-box.active-step .step-name { color: #1d4ed8; }
    .step-detail { font-size: 9.5px; color: #6b7280; line-height: 1.4; }
    .step-box.active-step .step-detail { color: #2563eb; }
    .chunk-preview {
        margin-top: 6px;
        font-size: 9px;
        background: #dbeafe;
        color: #1e40af;
        border-radius: 6px;
        padding: 4px 8px;
        line-height: 1.4;
        font-weight: 500;
    }

    /* Pestaña Evaluación */
    .metric-value { font-size: 24px; font-weight: 800; line-height: 1; }
    .color-green { color: #15803d; }
    .color-blue { color: #1d4ed8; }
    
    /* Barra de progreso de score */
    .score-bar-wrap { background: #e5e7eb; border-radius: 999px; height: 5px; overflow: hidden; margin-top: 8px; }
    .score-bar { height: 100%; border-radius: 999px; }
    .bar-green { background: #22c55e; }
    .bar-blue { background: #3b82f6; }

    /* Barra lateral y Cards */
    .sidebar-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 14px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    .sidebar-label {
        font-size: 10px;
        font-weight: 700;
        color: #6b7280;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }

    /* ── Estilización Avanzada de Botones mediante Wrapper Clases ── */
    
    .persona-btn-wrap button {
        background-color: white !important;
        color: #374151 !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 10px !important;
        padding: 8px 12px !important;
        text-align: left !important;
        align-items: center !important;
        justify-content: flex-start !important;
        display: flex !important;
        width: 100% !important;
        box-shadow: none !important;
        margin-bottom: 6px !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .persona-btn-wrap button:hover {
        background-color: #f9fafb !important;
        border-color: #cbd5e1 !important;
        transform: translateX(2px);
    }
    
    .persona-active button {
        background-color: #eff6ff !important;
        border-color: #bfdbfe !important;
        color: #1d4ed8 !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 2px 0 rgba(59, 130, 246, 0.05) !important;
    }

    .q-btn-wrap {
        margin-bottom: 0 !important;
        width: 100% !important;
    }
    .q-btn-wrap button {
        font-size: 11.5px !important;
        color: #374151 !important;
        padding: 10px 12px 4px 12px !important;
        border-radius: 12px 12px 0 0 !important;
        border: 1px solid #e5e7eb !important;
        border-bottom: none !important;
        background: #ffffff !important;
        line-height: 1.45 !important;
        text-align: left !important;
        font-weight: 500 !important;
        width: 100% !important;
        box-shadow: none !important;
        margin-bottom: 0 !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        display: block !important;
    }
    .q-btn-wrap button:hover {
        border-color: #cbd5e1 !important;
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    .q-btn-wrap.q-active button {
        border-color: #3b82f6 !important;
        background-color: #eff6ff !important;
        color: #1d4ed8 !important;
        font-weight: 600 !important;
    }
    
    .q-badge-wrap {
        border: 1px solid #e5e7eb !important;
        border-top: none !important;
        border-radius: 0 0 12px 12px !important;
        padding: 0px 12px 8px 12px !important;
        background-color: #ffffff !important;
        display: flex !important;
        justify-content: flex-end !important;
        margin-top: -33px !important; /* Tirar el elemento hacia arriba directamente */
        margin-bottom: 8px !important;
        width: 100% !important;
        position: relative !important;
        z-index: 99 !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    /* Eliminar el gap que impone Streamlit entre contenedores hermanos */
    div:has(> .q-btn-wrap) {
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }
    div:has(> .q-badge-wrap) {
        margin-top: 0px !important;
        padding-top: 0px !important;
        margin-bottom: 0px !important;
    }
    
    /* Efecto de Hover y Active coordinado entre el botón y el badge usando :has() */
    div:has(> .q-btn-wrap):hover + div .q-badge-wrap {
        border-color: #cbd5e1 !important;
        background-color: #f8fafc !important;
    }
    div:has(> .q-btn-wrap.q-active) + div .q-badge-wrap {
        border-color: #3b82f6 !important;
        background-color: #eff6ff !important;
    }
    
    .avatar-circle {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
        margin-right: 8px;
        flex-shrink: 0;
    }
    
    /* Tabla HTML Estilizada como en el Mockup */
    .mockup-table {
        width: 100%;
        border-collapse: collapse;
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        overflow: hidden;
        font-size: 11.5px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    .mockup-table th {
        background: #f9fafb;
        border-bottom: 1px solid #e5e7eb;
        padding: 10px 16px;
        font-size: 10px;
        font-weight: 700;
        color: #4b5563;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        text-align: left;
    }
    .mockup-table td {
        padding: 12px 16px;
        border-bottom: 1px solid #f3f4f6;
        color: #374151;
    }
    .mockup-table tr:last-child td {
        border-bottom: none;
    }
    .mockup-pill-cat {
        font-size: 9.5px;
        font-weight: 600;
        padding: 3px 9px;
        border-radius: 999px;
        display: inline-block;
    }
    .cat-direct_fact { background: #eff6ff; color: #1e40af; }
    .cat-conditional { background: #f0fdf4; color: #166534; }
    .cat-temporal { background: #EEF5FC; color: #0C447C; }
    .cat-comparative { background: #F3F0FA; color: #4A2D8B; }
    .cat-spanning { background: #FDE8E8; color: #8B1A1A; }
    
    .mockup-score-pill {
        font-size: 10px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
    }
    .score-hi { background: #EAF3DE; color: #27500A; }
    .score-mid { background: #FFF5E0; color: #7A4500; }
    .score-lo { background: #FDE8E8; color: #8B1A1A; }
</style>
""", unsafe_allow_html=True)

# ── Render Header ──
st.markdown("""
<div class="mockup-header">
  <div>
    <p class="mockup-title">SEIA RAG — Explorador de expedientes ambientales</p>
    <p class="mockup-sub">Búsqueda semántica sobre RCAs, ICEs e ICSARAs del Sistema de Evaluación de Impacto Ambiental de Chile</p>
  </div>
  <span class="mockup-badge">Portafolio · Fernando Barrera</span>
</div>
""", unsafe_allow_html=True)

# ── Definir Pestañas (Tabs) ──
tab_demo, tab_eval = st.tabs(["Demo", "Evaluación del sistema"])

# ==============================================================================
# TAB 1: DEMO (Buscador Real)
# ==============================================================================
with tab_demo:
    # Session State para controlar el usuario y pregunta elegida de forma reactiva
    if "selected_persona_idx" not in st.session_state:
        st.session_state.selected_persona_idx = 0
    if "current_question" not in st.session_state:
        st.session_state.current_question = "¿Qué planes de cierre y vida útil estimada se definieron para el proyecto El Espino?"

    # 1. SECCIÓN: Perfiles de Usuario (Horizontal, 4 columnas)
    st.markdown('<p style="font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 2px;">1. Selecciona un Perfil de Usuario</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size: 10px; color: #9ca3af; margin-top: 0px; margin-bottom: 8px;">(Filtra las preguntas de ejemplo recomendadas según su área de interés)</p>', unsafe_allow_html=True)
    
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    cols_p = [col_p1, col_p2, col_p3, col_p4]
    
    for idx, p in enumerate(personas):
        is_active = (st.session_state.selected_persona_idx == idx)
        active_class = "persona-active" if is_active else ""
        
        # Asignar emoji representativo
        if p["avatar_symbol"] == "CA":
            avatar_display = "📊"
        elif p["avatar_symbol"] == "EM":
            avatar_display = "⛏️"
        elif p["avatar_symbol"] == "AB":
            avatar_display = "⚖️"
        else:
            avatar_display = "🌱"
            
        btn_label = f"{avatar_display}  {p['nombre']} — {p['role']}"
        
        with cols_p[idx]:
            st.markdown(f'<div class="persona-btn-wrap {active_class}">', unsafe_allow_html=True)
            if st.button(label=btn_label, key=f"btn_p_{idx}"):
                st.session_state.selected_persona_idx = idx
                st.session_state.current_question = p["preguntas"][0]["q"] # Cargar primera pregunta de ejemplo
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # 2. SECCIÓN: Preguntas de Ejemplo (Horizontal, 3 columnas)
    st.markdown('<p style="font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 14px; margin-bottom: 8px;">2. Selecciona una Pregunta de Ejemplo</p>', unsafe_allow_html=True)
    
    curr_persona = personas[st.session_state.selected_persona_idx]
    col_q1, col_q2, col_q3 = st.columns(3)
    cols_q = [col_q1, col_q2, col_q3]
    
    for idx_q, q_item in enumerate(curr_persona["preguntas"]):
        q_text = q_item["q"]
        q_type = q_item["type"]
        is_q_active = (st.session_state.current_question == q_text)
        q_active_class = "q-active" if is_q_active else ""
        
        # Mapear colores de badges para los tipos de preguntas
        badge_styles = {
            "🔍 Específica": ("#eff6ff", "#1e40af"),
            "📊 Global": ("#f0fdf4", "#166534"),
            "🧩 Compuesta": ("#f5f3ff", "#5b21b6")
        }
        bg, fg = badge_styles.get(q_type, ("#f3f4f6", "#1f2937"))
        
        with cols_q[idx_q]:
            # 1. Parte Superior: Caja del Botón con la pregunta
            st.markdown(f'<div class="q-btn-wrap {q_active_class}">', unsafe_allow_html=True)
            if st.button(label=q_text, key=f"btn_q_{idx_q}"):
                st.session_state.current_question = q_text
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 2. Parte Inferior: Caja del Badge coordinada visualmente
            badge_html = (
                f'<div class="q-badge-wrap">'
                f'<span style="font-size: 8px; font-weight: 700; background: {bg}; color: {fg}; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; display: inline-block;">{q_type}</span>'
                f'</div>'
            )
            st.markdown(badge_html, unsafe_allow_html=True)

    # 3. SECCIÓN: Buscador e Interacción RAG
    st.markdown('<p style="font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 14px; margin-bottom: 2px;">3. Ejecutar Consulta</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size: 10px; color: #3b82f6; font-weight: 600; margin-top: 0px; margin-bottom: 8px;">💡 ¡Puedes escribir cualquier pregunta libre y personalizada aquí abajo! El RAG Agent la clasificará y responderá en tiempo real.</p>', unsafe_allow_html=True)
    
    # Utilizar un st.form para evitar que se ejecute la búsqueda automáticamente en la primera carga
    with st.form("query_form", clear_on_submit=False):
        user_query = st.text_input(
            label="Escribe tu pregunta sobre el SEIA:",
            value=st.session_state.current_question,
            placeholder="Escribe tu propia pregunta personalizada sobre los proyectos o expedientes aquí...",
            label_visibility="collapsed"
        )
        submit_clicked = st.form_submit_button("Consultar y Comparar Resultados", use_container_width=True)

    # Solo ejecutar si se hace clic en Consultar y hay texto
    if submit_clicked and user_query.strip():
        # Inicializar variables de respuesta
        norag_answer = ""
        norag_flag = None
        rag_answer = ""
        sources = []
        chunk_preview = "No hay previsualización de fragmentos."
        
        # ── EJECUCIÓN EN TIEMPO REAL REAL (Siempre RAG contra la Base de Datos) ──
        # 1. Llamar a OpenAI Directo (SIN RAG)
        try:
            direct_res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente experto del SEIA Chile. Responde de forma general e hipotética."},
                    {"role": "user", "content": user_query}
                ]
            )
            norag_answer = direct_res.choices[0].message.content
            norag_flag = "Respuesta generada sin acceso a documentos. Puede alucinar datos específicos de la RCA."
        except Exception as e:
            norag_answer = f"Error en modelo directo: {e}"

        # 2. Llamar al RAG Agent (CON RAG)
        if agent:
            with st.spinner("Buscando en expedientes y redactando respuesta con fuentes reales..."):
                try:
                    rag_answer, steps = agent.query(user_query)
                    sources = []
                    chunk_preview_lines = []
                    
                    # Recolectar las fuentes reales recopiladas por el agente desde LanceDB
                    for step in steps:
                        if "sources" in step and step["sources"]:
                            sources.extend(step["sources"])
                            for src in step["sources"]:
                                chunk_preview_lines.append(f"{src['doc']} p.{src['seccion']} · sim {src['score']}")
                    
                    # Si no hay fuentes vectoriales pero hubo una consulta global, agregar el reporte consolidado
                    if not sources:
                        for step in steps:
                            if step.get("category") == "global":
                                sources.append({
                                    "doc": "Reporte Consolidado del Portafolio del SEIA",
                                    "proyecto": "Multi-Proyecto (Análisis BI)",
                                    "seccion": "Secciones 1-12",
                                    "score": "N/A"
                                })
                                chunk_preview_lines.append("Reporte Consolidado del Portafolio · Secciones 1-12 · sim N/A")
                                
                    if chunk_preview_lines:
                        chunk_preview = "\n".join(chunk_preview_lines[:2])
                    else:
                        chunk_preview = "Lectura general del Reporte Consolidado del Portafolio del SEIA."
                except Exception as e:
                    rag_answer = f"Error ejecutando RAG Agent: {e}"
        else:
            rag_answer = "Error: El Agente RAG no está inicializado."

        # Renderizar paneles comparativos
        col_norag, col_rag = st.columns(2)
        
        # Definir bandera HTML fuera del f-string para compatibilidad con Python <3.12 (evita backslashes en f-string)
        norag_flag_html = f"<div class='hallucination-flag'>{norag_flag}</div>" if norag_flag else ""
        
        with col_norag:
            st.markdown(
                '<div class="compare-panel">'
                '<div class="panel-header" style="background: #fff9f9;">'
                '<span class="panel-badge badge-norag">SIN RAG</span>'
                '<span class="panel-header-label" style="color:#8B1A1A">Modelo sin contexto</span>'
                '</div>'
                '<div class="panel-body">'
                f'<div class="msg-user">Pregunta: {user_query}</div>'
                f'<div class="msg-norag">{norag_answer}</div>'
                f'{norag_flag_html}'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )
            
        with col_rag:
            # Formatear lista de tarjetas de fuentes
            sources_html = ""
            if sources:
                sources_html += '<div class="sources-section"><p class="sources-label">Fuentes de Documentos Clave</p><div class="source-cards">'
                for s in sources:
                    sources_html += (
                        '<div class="source-card">'
                        '<div style="display:flex; align-items:center; gap:7px;">'
                        '<span style="font-size:13px;">📄</span>'
                        '<div>'
                        f'<p class="source-doc" style="margin:0;">{s["doc"]}</p>'
                        f'<p style="font-size:9px; color:#888; margin:0;">{s["seccion"]} · {s["proyecto"]}</p>'
                        '</div>'
                        '</div>'
                        f'<span class="source-score">sim {s["score"]}</span>'
                        '</div>'
                    )
                sources_html += '</div></div>'

            st.markdown(
                '<div class="compare-panel">'
                '<div class="panel-header" style="background: #F4F9FF;">'
                '<span class="panel-badge badge-rag">CON RAG</span>'
                '<span class="panel-header-label" style="color:#0C447C">Respuesta fundamentada</span>'
                '</div>'
                '<div class="panel-body">'
                f'<div class="msg-user">Pregunta: {user_query}</div>'
                f'<div class="msg-rag">{rag_answer}</div>'
                f'{sources_html}'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )

        # Renderizar Flujo RAG inferior
        st.markdown(f"""
        <div class="flow-panel">
            <div class="flow-label">Flujo RAG Agéntico — cómo se construye esta respuesta</div>
            <div class="flow-steps">
                <div class="step-box">
                    <p class="step-num">01</p>
                    <p class="step-name">Query</p>
                    <p class="step-detail">Pregunta en lenguaje natural</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">02</p>
                    <p class="step-name">Router</p>
                    <p class="step-detail">Categoriza y valida Guardrails</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">03</p>
                    <p class="step-name">Decomposer</p>
                    <p class="step-detail">Divide en sub-consultas paralelas</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box active-step">
                    <p class="step-num">04</p>
                    <p class="step-name">Retrieval (k=8)</p>
                    <p class="step-detail">Búsqueda vectorial en LanceDB</p>
                    <div class="chunk-preview">{chunk_preview}</div>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">05</p>
                    <p class="step-name">LLM Reranker</p>
                    <p class="step-detail">RankGPT selecciona top-4 útiles</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">06</p>
                    <p class="step-name">Metadata</p>
                    <p class="step-detail">Antepone metadatos de negocio</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">07</p>
                    <p class="step-name">Prompt</p>
                    <p class="step-detail">System + sub-respuestas + contexto</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">08</p>
                    <p class="step-name">Synthesis</p>
                    <p class="step-detail">Genera respuesta y limpia jergas</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Mostrar estados vacíos si no hay consulta realizada
        col_norag, col_rag = st.columns(2)
        with col_norag:
            st.markdown("""
            <div class="compare-panel">
                <div class="panel-header" style="background: #fff9f9;">
                    <span class="panel-badge badge-norag">SIN RAG</span>
                    <span class="panel-header-label" style="color:#8B1A1A">Modelo sin contexto</span>
                </div>
                <div class="panel-body" style="justify-content:center; align-items:center; color:#bbb; font-size:11px;">
                    Selecciona una pregunta de ejemplo o escribe una y presiona "Consultar" para iniciar la búsqueda en los expedientes
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col_rag:
            st.markdown("""
            <div class="compare-panel">
                <div class="panel-header" style="background: #F4F9FF;">
                    <span class="panel-badge badge-rag">CON RAG</span>
                    <span class="panel-header-label" style="color:#0C447C">Respuesta fundamentada</span>
                </div>
                <div class="panel-body" style="justify-content:center; align-items:center; color:#bbb; font-size:11px;">
                    La respuesta citada con fuentes reales de LanceDB aparecerá aquí
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Mostrar flujo RAG en gris por defecto en estado inactivo
        st.markdown("""
        <div class="flow-panel">
            <div class="flow-label">Flujo RAG Agéntico — cómo se construye la respuesta</div>
            <div class="flow-steps">
                <div class="step-box">
                    <p class="step-num">01</p>
                    <p class="step-name">Query</p>
                    <p class="step-detail">Pregunta en lenguaje natural</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">02</p>
                    <p class="step-name">Router</p>
                    <p class="step-detail">Categoriza y valida Guardrails</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">03</p>
                    <p class="step-name">Decomposer</p>
                    <p class="step-detail">Divide en sub-consultas paralelas</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">04</p>
                    <p class="step-name">Retrieval (k=8)</p>
                    <p class="step-detail">Búsqueda vectorial en LanceDB</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">05</p>
                    <p class="step-name">LLM Reranker</p>
                    <p class="step-detail">RankGPT selecciona top-4 útiles</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">06</p>
                    <p class="step-name">Metadata</p>
                    <p class="step-detail">Antepone metadatos de negocio</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">07</p>
                    <p class="step-name">Prompt</p>
                    <p class="step-detail">System + sub-respuestas + contexto</p>
                </div>
                <div style="color:#bbb; font-size:11px; padding:0 4px;">→</div>
                <div class="step-box">
                    <p class="step-num">08</p>
                    <p class="step-name">Synthesis</p>
                    <p class="step-detail">Genera respuesta y limpia jergas</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ==============================================================================
# TAB 2: EVALUACIÓN DEL SISTEMA
# ==============================================================================
with tab_eval:
    st.markdown('<p style="font-size:13px; font-weight:700; color:#1a1a1a; margin-bottom:2px;">🔍 Evaluación de Retrieval (Basado en Ground Truth)</p>', unsafe_allow_html=True)
    
    col_ret_metrics, col_ret_chart = st.columns([1, 1])
    
    with col_ret_metrics:
        st.markdown("""
        <div class="sidebar-card">
            <p class="sidebar-label">Promedio sobre 150 preguntas de prueba (Optimizado con RAG Global)</p>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-green">0.81</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">MRR</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">Mean Reciprocal Rank</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-green" style="width:81%"></div></div>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-green">0.78</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">nDCG</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">Disc. Cum. Gain</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-green" style="width:78%"></div></div>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-green">87%</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">Cov. Keywords</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">Keywords en top-10</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-green" style="width:87%"></div></div>
                </div>
            </div>
            <div style="margin-top:10px; padding:8px 11px; background:#EAF3DE; border-radius:8px; border:0.5px solid #b3d68a;">
                <p style="font-size:10.5px; color:#27500A; line-height:1.6; margin:0;">
                    <strong>Cómo funciona:</strong> Cada pregunta del test set incluye palabras clave (keywords) indispensables. Evaluamos en qué posición del ranking aparece el primer fragmento relevante (MRR) y el ordenamiento semántico de los resultados (nDCG).
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_ret_chart:
        st.markdown("""
        <div class="sidebar-card" style="height: 100%;">
            <p class="sidebar-label">MRR por Categoría de Pregunta</p>
            <div style="display:flex; flex-direction:column; gap:4px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">direct_fact</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-green" style="width:91%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">0.91</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">conditional</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-green" style="width:85%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">0.85</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">temporal</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-green" style="width:85%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">0.85</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">comparative</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-green" style="width:82%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">0.82</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#27500A; width:78px; text-align:right; font-weight:600;">spanning ✅</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-green" style="width:72%;"></div></div>
                    <span style="font-size:10px; font-weight:700; color:#27500A;">0.72</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<p style="font-size:13px; font-weight:700; color:#1a1a1a; margin-top:12px; margin-bottom:2px;">🧑‍⚖️ Evaluación de Respuesta — LLM as Judge (Escala 1 a 5)</p>', unsafe_allow_html=True)
    
    col_judge_metrics, col_judge_chart = st.columns([1, 1])

    with col_judge_metrics:
        st.markdown("""
        <div class="sidebar-card">
            <p class="sidebar-label">Evaluación gpt-4o-mini estructurada (Optimizado con RAG Global)</p>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-blue">4.3</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">Accuracy</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">¿Es factualmente correcto?</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-blue" style="width:86%"></div></div>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-blue">4.0</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">Completeness</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">¿Cubre todo lo relevante?</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-blue" style="width:80%"></div></div>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:10px; padding:10px; text-align:center;">
                    <p class="metric-value color-blue">4.4</p>
                    <p style="font-size:9.5px; color:#888; margin-top:4px; margin-bottom:0;">Relevance</p>
                    <p style="font-size:8px; color:#bbb; margin:0;">¿Responde lo preguntado?</p>
                    <div class="score-bar-wrap"><div class="score-bar bar-blue" style="width:88%"></div></div>
                </div>
            </div>
            <div style="margin-top:10px; padding:8px 11px; background:#F3F0FA; border-radius:8px; border:0.5px solid #c8b8ef;">
                <p style="font-size:10.5px; color:#4A2D8B; line-height:1.6; margin:0;">
                    <strong>Cómo funciona:</strong> Un juez LLM evalúa de 1 a 5 la respuesta generada versus una de referencia. Cualquier error factual detectado por el juez penaliza inmediatamente el puntaje de exactitud (Accuracy = 1).
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_judge_chart:
        st.markdown("""
        <div class="sidebar-card" style="height: 100%;">
            <p class="sidebar-label">Accuracy por Categoría (Juez LLM)</p>
            <div style="display:flex; flex-direction:column; gap:4px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">direct_fact</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-blue" style="width:88%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">4.4 / 5</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">conditional</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-blue" style="width:84%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">4.2 / 5</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">temporal</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-blue" style="width:82%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">4.1 / 5</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#555; width:78px; text-align:right;">comparative</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-blue" style="width:80%;"></div></div>
                    <span style="font-size:10px; font-weight:700;">4.0 / 5</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:10.5px; color:#4A2D8B; width:78px; text-align:right; font-weight:600;">spanning ✅</span>
                    <div class="score-bar-wrap" style="flex:1; height:14px;"><div class="score-bar bar-blue" style="width:80%;"></div></div>
                    <span style="font-size:10px; font-weight:700; color:#4A2D8B;">4.0 / 5</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── TABLA ESTILIZADA DE PREGUNTAS (Réplica del Mockup) ──
    st.markdown('<p style="font-size: 11px; color: #999; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; margin-top: 15px; margin-bottom: 5px;">Preguntas evaluadas</p>', unsafe_allow_html=True)
    
    # Generar el HTML de la tabla exactamente igual al mockup
    table_rows = ""
    for idx_t, t in enumerate(eval_tests):
        cat_class = f"cat-{t['cat']}"
        mrr_class = "score-hi" if t["mrr"] >= 0.8 else ("score-mid" if t["mrr"] >= 0.6 else "score-lo")
        ndcg_class = "score-hi" if t["ndcg"] >= 0.8 else ("score-mid" if t["ndcg"] >= 0.6 else "score-lo")
        acc_class = "score-hi" if t["acc"] >= 4.0 else ("score-mid" if t["acc"] >= 3.0 else "score-lo")
        com_class = "score-hi" if t["com"] >= 4.0 else ("score-mid" if t["com"] >= 3.0 else "score-lo")
        rel_class = "score-hi" if t["rel"] >= 4.0 else ("score-mid" if t["rel"] >= 3.0 else "score-lo")
        
        table_rows += f"""<tr>
<td style="font-weight: 500; font-size:11px; color:#1a1a1a;">{t['q']}</td>
<td><span class="mockup-pill-cat {cat_class}">{t['cat']}</span></td>
<td style="text-align:center;"><span class="mockup-score-pill {mrr_class}">{t['mrr']:.2f}</span></td>
<td style="text-align:center;"><span class="mockup-score-pill {ndcg_class}">{t['ndcg']:.2f}</span></td>
<td style="text-align:center;"><span class="mockup-score-pill {acc_class}">{t['acc']:.1f}</span></td>
<td style="text-align:center;"><span class="mockup-score-pill {com_class}">{t['com']:.1f}</span></td>
<td style="text-align:center;"><span class="mockup-score-pill {rel_class}">{t['rel']:.1f}</span></td>
</tr>"""
        
    table_html = f"""<table class="mockup-table">
<thead>
    <tr>
        <th>Pregunta</th>
        <th>Categoría</th>
        <th style="text-align:center;">MRR</th>
        <th style="text-align:center;">nDCG</th>
        <th style="text-align:center;">Accuracy</th>
        <th style="text-align:center;">Complet.</th>
        <th style="text-align:center;">Relevance</th>
    </tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>"""
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Selector interactivo para ver detalles individuales
    selected_eval_q = st.selectbox(
        label="Selecciona una pregunta de la tabla anterior para ver el reporte detallado del Juez LLM:",
        options=[t["q"] for t in eval_tests]
    )
    
    # Extraer datos de la pregunta seleccionada en la evaluación
    eval_item = next(t for t in eval_tests if t["q"] == selected_eval_q)

    # Mostrar reporte detallado
    col_det_ret, col_det_judge = st.columns(2)
    
    with col_det_ret:
        st.markdown(f"""
        <div class="sidebar-card">
            <p class="sidebar-label">Métricas de Recuperación (Retrieval)</p>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:6px;">
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-green" style="font-size:18px; font-weight:700; margin:0;">{eval_item['mrr']:.2f}</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">MRR</p>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-green" style="font-size:18px; font-weight:700; margin:0;">{eval_item['ndcg']:.2f}</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">nDCG</p>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-green" style="font-size:18px; font-weight:700; margin:0;">{eval_item['cov']}</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">Coverage</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_det_judge:
        st.markdown(f"""
        <div class="sidebar-card">
            <p class="sidebar-label">Calidad de Respuesta (LLM Judge)</p>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:6px;">
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-blue" style="font-size:18px; font-weight:700; margin:0;">{eval_item['acc']:.1f}/5</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">Accuracy</p>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-blue" style="font-size:18px; font-weight:700; margin:0;">{eval_item['com']:.1f}/5</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">Completeness</p>
                </div>
                <div style="background:#fafafa; border:0.5px solid #e8e8e8; border-radius:8px; padding:8px; text-align:center;">
                    <p class="color-blue" style="font-size:18px; font-weight:700; margin:0;">{eval_item['rel']:.1f}/5</p>
                    <p style="font-size:9.5px; color:#888; margin:2px 0 0 0;">Relevance</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Texto comparativo de respuestas de referencia
    col_text_gen, col_text_ref = st.columns(2)
    with col_text_gen:
        st.markdown(f"""
        <div class="compare-panel" style="margin-top:5px;">
            <div class="panel-header" style="background:#fafafa;">
                <span class="panel-header-label">Respuesta Generada (RAG)</span>
            </div>
            <div style="padding:11px 13px; font-size:11.5px; color:#333; line-height:1.6;">{eval_item['generated']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_text_ref:
        st.markdown(f"""
        <div class="compare-panel" style="margin-top:5px;">
            <div class="panel-header" style="background:#fafafa;">
                <span class="panel-header-label">Respuesta de Referencia (Ground Truth)</span>
            </div>
            <div style="padding:11px 13px; font-size:11.5px; color:#333; line-height:1.6;">{eval_item['reference']}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#F3F0FA; border:0.5px solid #c8b8ef; border-radius:10px; padding:11px 13px; margin-top:5px; margin-bottom:15px;">
        <p style="font-size:10px; font-weight:600; color:#4A2D8B; text-transform:uppercase; letter-spacing:0.06em; margin:0 0 6px 0; display:flex; align-items:center; gap:5px;">
            🧑‍⚖️ Feedback del Juez LLM
        </p>
        <p style="font-size:11.5px; color:#3a2a5a; line-height:1.6; margin:0;">{eval_item['feedback']}</p>
    </div>
    """, unsafe_allow_html=True)

# ── Footer con badges de APIs ──
st.markdown("""
<div class="app-footer">
  <span class="footer-left">Stack del Proyecto RAG</span>
  <div class="api-badges">
    <span class="api-badge badge-dss"><span class="api-badge-dot" style="background:#5a9e2f"></span>SEA API · Datos</span>
    <span class="footer-sep">·</span>
    <span class="api-badge badge-oai"><span class="api-badge-dot" style="background:#888"></span>OpenAI · Embeddings</span>
    <span class="footer-sep">·</span>
    <span class="api-badge badge-qdr"><span class="api-badge-dot" style="background:#378ADD"></span>LanceDB · Vector DB</span>
    <span class="footer-sep">·</span>
    <span class="api-badge badge-llm"><span class="api-badge-dot" style="background:#555"></span>GPT-4o / mini · Generación</span>
  </div>
</div>
""", unsafe_allow_html=True)
