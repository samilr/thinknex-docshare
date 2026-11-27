# ADR-0013: RAG con pgvector, embeddings de Vertex AI y citas nativas de Claude

**Estado:** aceptada

## Contexto
La prueba es para un rol de **Senior AI Engineer orientado a RAG**. Se pidió que el sistema pueda
buscar y responder preguntas sobre los documentos, con fuentes verificables y sin romper los
permisos ni la privacidad. La infraestructura ya está en GCP: Cloud SQL Postgres 17, Cloud Run y
Secret Manager.

## Decisión
1. **Vectores en el mismo Postgres con `pgvector`:**
   - tablas `ai_index` y `ai_chunks`, índice HNSW por coseno y `tsvector` en español;
   - Cloud SQL incluye la extensión;
   - en local, una imagen propia sobre `postgres:17-alpine`.
2. **Embeddings con Vertex AI (`gemini-embedding-001`, 768 dimensiones):**
   - región `southamerica-east1` (no está en Santiago);
   - autorizado por IAM a la cuenta de servicio, sin otra clave;
   - `FakeEmbedder` determinista para tests y local sin GCP.
3. **Recuperación híbrida:**
   - similitud semántica + texto completo, fusionadas con **RRF** (k = 60);
   - **permisos y alcance en el SQL**, no en el prompt.
4. **Respuestas de Claude Sonnet 5.5** con bloques **`search_result` y citas nativas**:
   - las citas se traducen a documento y página, y se abren en el visor;
   - antes de enviar se redactan RUT, tarjetas y cuentas;
   - los `RESTRICTED` no se indexan.
5. **Indexación por eventos:**
   - outbox `ai_jobs` procesado tras cada cambio en la biblioteca;
   - job programado de respaldo y backfill;
   - sincronización idempotente por `sha256`.

## Alternativas descartadas
- **Base vectorial dedicada** (Vertex Vector Search, Pinecone, Qdrant): otra pieza que operar,
  pagar y sincronizar, y el filtro de permisos quedaría fuera de la transacción. Con miles de
  documentos, pgvector con HNSW sobra.
- **Solo búsqueda semántica:** falla con códigos, RUT, nombres propios y cifras exactas. Lo
  híbrido con RRF es robusto sin calibrar pesos.
- **Citas pidiendo "[1]" en el prompt:** el modelo puede inventar o descuadrar referencias. Las
  citas nativas apuntan a bloques reales del resultado.
- **Embeddings de Voyage AI:** buena calidad, pero otro proveedor y otra clave. Vertex queda dentro
  de GCP con IAM.
- **Re-ranking con LLM en cada pregunta:** más costo y latencia. Queda como mejora a medir con evals.

## Consecuencias
- El índice comparte la base con los datos de negocio: un backup los cubre a ambos y el filtro de
  permisos es una sola consulta SQL. Con mucho volumen se podría separar.
- Los embeddings se calculan en São Paulo (dentro del proyecto GCP). Los fragmentos que llegan a
  Anthropic van redactados.
- La calidad depende del texto extraíble: los escaneados requieren OCR (pendiente).
