# SEIA RAG — Explorador de Expedientes Ambientales 📄⛏️

Este repositorio contiene la aplicación de **Búsqueda Semántica y RAG (Retrieval-Augmented Generation)** diseñada para explorar, consultar y evaluar resoluciones y expedientes técnicos del **Sistema de Evaluación de Impacto Ambiental (SEIA)** de Chile.

La aplicación está optimizada específicamente para auditar un portafolio de **91 megaproyectos mineros**, procesando documentos complejos como **RCAs (Resoluciones de Calificación Ambiental)**, **ICEs (Informes Consolidados de Evaluación)** e **ICSARAs**.

👉 **URL de la Aplicación en Vivo:** [seia-rag-dashboard.streamlit.app](https://seia-rag-dashboard.streamlit.app/)

---

## 🚀 Arquitectura y Características Clave

1. **Enrutamiento Inteligente de Consultas (Query Router):**
   El agente clasifica dinámicamente cada consulta en tres categorías:
   * **🔍 Específica:** Búsqueda dirigida a un expediente o megaproyecto particular utilizando índices de metadatos.
   * **📊 Global:** Consultas transversales (*spanning*) que requieren consolidar información agregada de todo el portafolio.
   * **❌ Preguntas Fuera de Tema (Out-of-Topic):** Detección y filtrado automático de consultas no relacionadas con el SEIA o minería para proteger el sistema ante abusos y optimizar costos de API.

2. **Base de Datos Vectorial de Alto Rendimiento (LanceDB):**
   * Almacenamiento vectorial indexado con embeddings de OpenAI.
   * Recuperación híbrida ultrarrápida compatible con metadatos específicos del SEIA.

3. **Dashboard de Evaluación (LLM-as-a-Judge):**
   * Pestaña dedicada a la evaluación del desempeño del RAG bajo un conjunto de pruebas (*test set*) balanceado.
   * Métricas de recuperación automatizadas: **MRR** (Mean Reciprocal Rank) y **nDCG** (Normalized Discounted Cumulative Gain).
   * Evaluación de respuesta asistida por un modelo Juez LLM (escala de 1 a 5) en dimensiones de **Exactitud Factual (Accuracy)**, **Completitud (Completeness)** y **Relevancia (Relevance)**.

4. **Arquitectura Escalable en la Nube:**
   * La base de datos vectorial (~2.2 GB descomprimida) está alojada de forma externa y gratuita en un **Hugging Face Dataset**.
   * Al arrancar en Streamlit Community Cloud, la app descarga y descomprime automáticamente el zip verificado por hash SHA-256 en el disco del servidor, eliminando los límites de espacio de GitHub y optimizando el almacenamiento.

---

## 🗄️ Esquema de Datos y Metadatos (LanceDB)

Cada fragmento de texto en la base de datos vectorial de LanceDB está estructurado con metadatos específicos que garantizan precisión y trazabilidad:

* `proyecto`: Nombre oficial del megaproyecto minero.
* `empresa`: Titular o compañía minera responsable de la faena.
* `region`: Región de Chile donde se localiza el proyecto.
* `estado`: Estado de la Calificación Ambiental en el SEIA (Aprobado, Rechazado, Desistido).
* `numero_rca` / `fecha_rca`: Identificador único y fecha de emisión del permiso ambiental.
* `archivo_origen` / `chunk_index`: Nombre del documento original (RCA, ICE, etc.) e índice del fragmento.

### 💡 Utilización de Metadatos en el RAG
1. **Contexto de Consulta Segura (Prompt Enrichment):** Anteponemos los metadatos como cabeceras a cada fragmento enviado al LLM, evitando la mezcla de datos o alucinaciones cruzadas entre proyectos.
2. **Trazabilidad de Fuentes:** Los metadatos alimentan directamente las tarjetas de **Fuentes de Documentos Clave** que se muestran en el dashboard para validación del usuario.

---

## 🛠️ Stack Tecnológico

* ⚡ **Streamlit** — Frontend interactivo y diseño premium adaptado.
* 🗄️ **LanceDB** — Base de datos vectorial persistente y consultas en caliente.
* 🤖 **OpenAI API (GPT-4o-mini)** — Generador y evaluador de respuestas estructuradas.
* 📦 **Hugging Face Datasets** — Repositorio remoto para la base de datos pesada.
* 🐍 **Python 3.12** — Lógica e integración del agente.

---

## 💻 Ejecución Local

Para correr este proyecto en tu máquina local:

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/barrerafdo/seia-rag-dashboard.git
   cd seia-rag-dashboard
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar credenciales (.env):**
   Crea un archivo `.env` en la raíz del proyecto con tu clave de OpenAI:
   ```env
   OPENAI_API_KEY=tu_sk_proj_de_openai
   ```

4. **Iniciar la aplicación:**
   ```bash
   streamlit run app.py
   ```

---

## 👤 Autor

* **Fernando Barrera G.**
* **Rol:** Data Scientist · LLM Engineer · RAG Specialist
* **Contacto:** [barrera.fdo@outlook.com](mailto:barrera.fdo@outlook.com)
