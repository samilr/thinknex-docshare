# ADR-0014: Asistente agéntico con herramientas propias y acciones solo como propuestas

**Estado:** aceptada

## Contexto
Además de preguntar, se necesitaba un asistente presente en todo el portal y en cada documento, con
conversaciones guardadas. Debía poder operar la plataforma: buscar,
resumir, revisar envíos, políticas y auditoría, y preparar acciones como compartir o revocar.

## Decisión
1. **Bucle de tool use propio** sobre la Messages API (Claude Sonnet 5.5):
   - corre dentro de share-api;
   - herramientas tipadas sobre los servicios existentes, con la identidad y los permisos del
     usuario;
   - herramientas filtradas por rol;
   - máximo 8 pasos;
   - streaming SSE de texto, citas, pasos y propuestas.
2. **Las acciones nunca se ejecutan desde el modelo:**
   - `proponer_envio`, `proponer_revocacion` y `proponer_cambio_acceso` crean una propuesta
     auditada;
   - el usuario la confirma en la interfaz, que llama al endpoint normal (política, OTP,
     auditoría);
   - compartir abre el asistente de compartir completado, con su revisión de seguridad.
3. **Resultados de búsqueda como `search_result` citables** dentro de `tool_result`. El agente
   traduce los índices globales de cita a documento y página, también entre turnos.
4. **Conversaciones persistentes:**
   - `ai_conversations` y `ai_messages` guardan el transcript de la API y una vista para mostrar;
   - notas del sistema con el resultado de cada propuesta;
   - purga a los 30 días.
5. **Contexto de pantalla:** ruta y documento actual, más sugerencias según dónde está el usuario.

## Alternativas descartadas
- **Claude Managed Agents:**
  - aporta un sandbox alojado y sesiones gestionadas, pero las herramientas de este caso deben
    correr dentro de la aplicación, con los permisos del usuario y una pantalla de confirmación;
  - no se necesita ejecutar código;
  - los datos no deberían salir del perímetro.

  Queda como opción para un "agente auditor" programado, con un resumen nocturno de anomalías.
- **Permitir que el agente ejecute acciones directamente** con una confirmación en texto: un
  documento con prompt injection podría inducir un envío. La confirmación por clic en la interfaz es
  la frontera.
- **Framework de agentes de terceros** (LangChain y similares): más superficie y abstracción de la
  necesaria para ocho herramientas. El SDK oficial basta y da control total sobre el formato de las
  citas y el caché.

## Consecuencias
- Cada mensaje puede implicar varias llamadas al modelo. Se acota con el máximo de pasos, el caché,
  el presupuesto diario por usuario y el registro en `ai_usage`.
- El historial guarda el contenido devuelto por la API (incluido el thinking), así que la
  conversación puede continuarse sin reconstruir nada.
- Agregar una capacidad es agregar una herramienta tipada y su rol. Si cambia algo, se agrega como
  propuesta.
