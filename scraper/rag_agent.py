import os
import time
import json
import lancedb
from pathlib import Path
from typing import List, Tuple, Dict
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# Cargar variables de entorno
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

client = OpenAI()
LANCEDB_DIR = Path(__file__).resolve().parent / "lancedb_data"
TABLE_NAME = "seia_chunks"
GOLDEN_DOC_PATH = Path(__file__).resolve().parent / "Documento_Dorado_SEIA.md"

# ── Esquemas Pydantic para Estructurar Datos ─────────────────────────────

class SubQuery(BaseModel):
    query: str
    category: str  # "global", "especifico" o "fuera_de_tema"

class DecomposedQueries(BaseModel):
    sub_queries: List[SubQuery]
    is_compound: bool

class RerankedIndices(BaseModel):
    selected_indices: List[int] # Lista de los índices seleccionados más relevantes (rango 0 a 7). Debe tener entre 2 y 6 elementos.

class SEIARAGAgent:
    def __init__(self):
        # Conectar a LanceDB
        if not LANCEDB_DIR.exists():
            raise FileNotFoundError(f"No se encontró el directorio de LanceDB en '{LANCEDB_DIR}'. Asegúrate de correr la ingesta primero.")
        self.db = lancedb.connect(str(LANCEDB_DIR))
        self.tbl = self.db.open_table(TABLE_NAME)
        
        # Cargar Documento Dorado en memoria
        if not GOLDEN_DOC_PATH.exists():
            raise FileNotFoundError(f"No se encontró el Documento Dorado en '{GOLDEN_DOC_PATH}'. Asegúrate de correr el generador primero.")
        with open(GOLDEN_DOC_PATH, "r", encoding="utf-8") as f:
            self.golden_doc_content = f.read()

    def decompose_query(self, user_query: str) -> DecomposedQueries:
        """
        Analiza la consulta del usuario y decide si es compuesta.
        Devuelve una lista de sub-consultas atómicas clasificadas como global o específica.
        """
        prompt = f"""Analiza la consulta del usuario y decide si es compuesta (contiene más de una pregunta o combina datos agregados y específicos).
        
        Descompón la consulta en una lista de sub-consultas independientes sin perder el contexto de la pregunta original (no elimines términos de alcance como regiones, portafolio o palabras clave). Clasifica cada sub-consulta en una de estas categorías basándote en la siguiente regla crítica de decisión:
        
        1. 'global': Si la consulta involucra MÚLTIPLES PROYECTOS, REGIONES COMPLETAS (ej: Atacama, Antofagasta, Coquimbo), TENDENCIAS GENERALES, ESTADÍSTICAS AGREGADAS (promedios, sumas, conteos) o análisis transversal de todo el portafolio del SEIA (por ejemplo, motivos de rechazo más comunes, número de proyectos aprobados, sumas de inversión, etc.). Estas consultas se responden leyendo el Reporte Consolidado del Portafolio.
        2. 'especifico': Si la consulta se refiere estrictamente a UN SOLO PROYECTO INDIVIDUAL EN PARTICULAR (ej: El Espino, Santo Domingo, Pascua Lama, Cerro Casale, etc.), requiriendo detalles de su RCA, planes de cierre de esa faena, sus medidas de mitigación específicas o sus condiciones particulares de monitoreo. Estas consultas se responden buscando en la base de datos vectorial de expedientes.
        3. 'fuera_de_tema': Si la consulta no tiene relación alguna con proyectos mineros, variables ambientales, trámites del SEIA, o la inversión del portafolio de Chile (ej: clima, chistes, poemas, recetas de cocina, deportes, programación, historia universal, etc.).
        
        CONSULTA DEL USUARIO: '{user_query}'"""

        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un enrutador y descomponeador de consultas de alta precisión para un sistema RAG corporativo."},
                    {"role": "user", "content": prompt}
                ],
                response_format=DecomposedQueries,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Error en descomposición de consulta: {e}")
            # Fallback a una sola consulta específica
            return DecomposedQueries(
                sub_queries=[SubQuery(query=user_query, category="especifico")],
                is_compound=False
            )

    def execute_global_query(self, query_text: str) -> str:
        """
        Responde a una sub-consulta global leyendo todo el Documento Dorado.
        """
        system_prompt = (
            "Eres un consultor experto del SEIA Chile.\n"
            "Responde a la pregunta basándote estrictamente en el siguiente Reporte Consolidado del Portafolio "
            "de megaproyectos mineros del SEIA. Cita cifras exactas, tablas y regiones según corresponda."
        )
        user_prompt = f"""REPORTE CONSOLIDADO DEL PORTAFOLIO:
{self.golden_doc_content}

PREGUNTA GLOBAL:
{query_text}"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error ejecutando consulta global: {e}"

    def execute_specific_query_with_sources(self, query_text: str) -> Tuple[str, List[Dict]]:
        """
        Responde a una sub-consulta específica realizando búsqueda vectorial en LanceDB (k=8)
        y aplicando un Rerank agéntico basado en LLM (RankGPT) para seleccionar los 4 mejores.
        """
        # 1. Generar embedding de la sub-consulta
        try:
            res = client.embeddings.create(
                input=query_text.replace("\n", " "),
                model="text-embedding-3-small"
            )
            query_embedding = res.data[0].embedding
        except Exception as e:
            return f"Error generando embedding para la sub-consulta: {e}", []

        # 2. Buscar en LanceDB con límites dinámicos según el tipo de consulta
        # Si pide listados ("cuáles proyectos", "qué plantas", etc.), ampliamos la cobertura
        is_list_query = any(word in query_text.lower() for word in ["proyectos", "cuáles", "cuales", "lista", "quiénes", "quienes", "todos", "todas", "qué desaladoras", "que desaladoras"])
        limit_search = 25 if is_list_query else 15
        limit_rerank = 10 if is_list_query else 6

        try:
            results = self.tbl.search(query_embedding).limit(limit_search).to_list()
        except Exception as e:
            return f"Error buscando en LanceDB: {e}", []

        if not results:
            return "No se encontraron fragmentos relevantes en los expedientes para responder la pregunta.", []

        # 3. Reranker dinámico basado en LLM (RankGPT) o Bypass para Listados
        if is_list_query:
            # Para consultas de listados (múltiples proyectos), queremos máxima cobertura.
            # Bypasseamos el Reranker restrictivo para evitar pérdida de proyectos y tomamos los 12 mejores resultados directamente.
            selected_results = results[:12]
        else:
            selected_results = results[:6] # Fallback por defecto (primeros 6)
            if len(results) > 4:
                rerank_prompt = f"Analiza los siguientes {len(results)} fragmentos recuperados para responder la pregunta: '{query_text}'.\n\n"
                for idx, item in enumerate(results):
                    rerank_prompt += f"--- FRAGMENTO INDICE {idx} ---\n"
                    rerank_prompt += f"Proyecto: {item['proyecto']} | Texto: {item['text'][:450]}...\n\n"
                    
                rerank_prompt += (
                    "Tu tarea es seleccionar los índices de los fragmentos que aporten información útil, directa y "
                    "no redundante para responder la pregunta. Puedes seleccionar entre 2 y 6 fragmentos según sea necesario. "
                    "Excluye los fragmentos redundantes o irrelevantes."
                )
                
                try:
                    rerank_comp = client.beta.chat.completions.parse(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Eres un selector de contenido experto encargado de ordenar y filtrar fragmentos para un sistema RAG de forma dinámica."},
                            {"role": "user", "content": rerank_prompt}
                        ],
                        response_format=RerankedIndices,
                    )
                    selected_indices = rerank_comp.choices[0].message.parsed.selected_indices
                    temp_results = []
                    for idx in selected_indices:
                        if 0 <= idx < len(results):
                            temp_results.append(results[idx])
                    if temp_results:
                        selected_results = temp_results[:6]
                except Exception as e:
                    print(f"Error en Reranker LLM dinámico: {e}. Usando top-6 por defecto.")
                    selected_results = results[:6]

        # 4. Formatear fragmentos de contexto y extraer fuentes
        context_parts = []
        sources = []
        for item in selected_results:
            context_header = (
                f"[Proyecto: {item['proyecto']} | Titular: {item['empresa']} | Región: {item['region']} | "
                f"Calificación: {item['estado']} | RCA N°: {item['numero_rca']} ({item['fecha_rca']})]\n"
            )
            full_chunk = f"{context_header}Texto del Expediente:\n{item['text']}"
            context_parts.append(full_chunk)

            # Formatear el tipo de documento del nombre del archivo origen
            fn = item.get("archivo_origen", "Expediente")
            if fn.endswith(".txt"):
                fn = fn[:-4]
            doc_type = "RCA" if "RCA" in fn or "rca" in fn else ("EIA" if "EIA" in fn or "eia" in fn else "Expediente")

            sources.append({
                "doc": f"{doc_type} — {item['proyecto']}",
                "proyecto": item.get("empresa", "Titular"),
                "seccion": f"Parte {item.get('chunk_index', 0) + 1}",
                "score": f"{1.0 - item.get('_distance', 0.0):.2f}"
            })

        context_str = "\n\n---\n\n".join(context_parts)

        # 5. Generar respuesta
        system_prompt = (
            "Eres un consultor experto del SEIA Chile.\n"
            "Responde a la pregunta basándote estrictamente en los siguientes fragmentos recuperados de los expedientes.\n"
            "Si no hay suficiente información, indícalo claramente. Cita el proyecto y los datos técnicos."
        )
        user_prompt = f"""CONTEXTO DE EXPEDIENTES RECUPERADOS:
{context_str}

PREGUNTA ESPECÍFICA:
{query_text}"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content, sources
        except Exception as e:
            return f"Error generando respuesta específica: {e}", []

    def execute_sub_query(self, sub_query: SubQuery) -> Dict:
        """
        Ejecuta una sub-consulta en su motor correspondiente.
        """
        start_time = time.time()
        print(f"→ Ejecutando [{sub_query.category.upper()}]: '{sub_query.query}'")
        
        sources = []
        if sub_query.category == "fuera_de_tema":
            answer = (
                "Soy un asistente de inteligencia especializado exclusivamente en el portafolio de proyectos "
                "mineros del SEIA (Chile). Por favor, realiza una consulta dentro de este ámbito (proyectos mineros, "
                "inversiones, variables de impacto ambiental, comunas afectadas, obras de infraestructura o RCAs)."
            )
        elif sub_query.category == "global":
            answer = self.execute_global_query(sub_query.query)
        else:
            answer, sources = self.execute_specific_query_with_sources(sub_query.query)
            
        elapsed = time.time() - start_time
        return {
            "query": sub_query.query,
            "category": sub_query.category,
            "answer": answer,
            "sources": sources,
            "time_seconds": elapsed
        }

    def synthesize_answers(self, original_query: str, sub_results: List[Dict]) -> str:
        """
        Combina las respuestas de las sub-consultas en una respuesta final consolidada.
        """
        results_summary = ""
        for i, res in enumerate(sub_results):
            results_summary += (
                f"--- Sub-pregunta {i+1} ({res['category']}): {res['query']} ---\n"
                f"Respuesta parcial obtenida:\n{res['answer']}\n\n"
            )

        system_prompt = (
            "Eres un consultor experto ambiental y de negocios del SEIA (Chile).\n"
            "Tu misión es redactar una respuesta unificada, fluida, coherente y profesional a la pregunta original del usuario, "
            "utilizando como insumos las respuestas parciales obtenidas de las distintas sub-consultas realizadas.\n\n"
            "REGLAS:\n"
            "- No repitas títulos de 'Sub-pregunta 1' en tu respuesta final, integra la información de forma fluida.\n"
            "- Mantén el rigor técnico, cita cifras de inversión y nombres de proyectos tal cual aparecen en los insumos.\n"
            "- Responde en español formal chileno/profesional.\n"
            "- IMPORTANTE: No utilices nunca términos de implementación interna como 'Documento Dorado', 'reporte de markdown', 'RAG', 'chunks', 'LanceDB' ni 'base de datos vectorial'. En su lugar, refiérete al 'Reporte Consolidado del Portafolio del SEIA' o la 'base de datos de expedientes ambientales'."
        )

        user_prompt = f"""PREGUNTA ORIGINAL DEL USUARIO:
'{original_query}'

INSUMOS DE RESPUESTAS PARCIALES:
{results_summary}"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # Usamos GPT-4o para una síntesis final de calidad ejecutiva
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error en síntesis final de respuestas: {e}"

    def query(self, user_query: str) -> Tuple[str, List[Dict]]:
        """
        Método principal del Agente RAG.
        Descompone la consulta, las ejecuta en paralelo y sintetiza la respuesta.
        """
        print(f"🔍 Recibiendo consulta: '{user_query}'")
        
        # 1. Descomposición
        decomposed = self.decompose_query(user_query)
        print(f"⚡ Es compuesta: {decomposed.is_compound} | Sub-consultas generadas: {len(decomposed.sub_queries)}")
        
        # Interceptar preguntas fuera de tema inmediatamente (Guardrails)
        if any(sq.category == "fuera_de_tema" for sq in decomposed.sub_queries):
            refusal = (
                "Soy un asistente de inteligencia especializado exclusivamente en el portafolio de proyectos "
                "mineros del SEIA (Chile). Solo puedo responder preguntas relacionadas con proyectos mineros, "
                "inversión, comunas impactadas, obras de infraestructura, variables ambientales o trámites del portafolio. "
                "Por favor, realiza una consulta dentro de este ámbito."
            )
            return refusal, [{"query": user_query, "category": "fuera_de_tema", "answer": refusal, "time_seconds": 0.0}]
        
        # 2. Ejecución paralela
        sub_results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Enviar tareas a los hilos concurrentes
            futures = [executor.submit(self.execute_sub_query, sq) for sq in decomposed.sub_queries]
            for fut in futures:
                try:
                    sub_results.append(fut.result())
                except Exception as e:
                    print(f"Error en ejecución de hilo: {e}")

        # 3. Síntesis
        if len(sub_results) == 1:
            # Si solo hubo una pregunta, devolvemos la respuesta directa para evitar tokens de síntesis innecesarios
            final_answer = sub_results[0]["answer"]
        else:
            print("🧠 Sintetizando respuestas parciales...")
            final_answer = self.synthesize_answers(user_query, sub_results)

        return final_answer, sub_results

# Código de pruebas de consola
if __name__ == "__main__":
    import sys
    agent = SEIARAGAgent()
    
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = "¿Cuál es la inversión total en la región de Atacama y qué obras contempla el proyecto Santo Domingo?"
        
    ans, steps = agent.query(q)
    
    print("\n" + "="*50)
    print("📋 PASOS EJECUTADOS POR EL AGENTE:")
    print("="*50)
    for i, s in enumerate(steps):
        print(f"\n[{i+1}] ({s['category'].upper()}) Q: {s['query']}")
        print(f"    Respuesta parcial (primeras 150 letras): {s['answer'][:150]}...")
        
    print("\n" + "="*50)
    print("💬 RESPUESTA CONSOLIDADA FINAL:")
    print("="*50)
    print(ans)
    print("="*50 + "\n")
