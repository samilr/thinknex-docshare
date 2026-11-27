# Decisiones de arquitectura (ADR)

Cada ADR registra una decisión con su contexto, las alternativas descartadas y sus consecuencias.
Formato: [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Si una decisión cambia de fondo, se agrega una ADR nueva que la reemplaza o la complementa.

| ADR | Decisión | Estado |
|---|---|---|
| [0001](0001-monolito-modular.md) | Monolito modular + DMS simulado como servicio aparte | aceptada |
| [0002](0002-snapshot-inmutable.md) | Snapshot inmutable direccionado por contenido | aceptada |
| [0003](0003-enlace-otp.md) | Enlace de un solo destinatario + OTP por el mismo canal | aceptada |
| [0004](0004-auditoria-hash-chain.md) | Auditoría append-only con cadena de hashes | aceptada |
| [0005](0005-ia-proporcional.md) | IA proporcional, chequeo de sensibilidad antes de compartir | aceptada |
| [0006](0006-gcp-cloud-run.md) | GCP con Cloud Run, Cloud SQL y Terraform | aceptada |
| [0007](0007-auth-propia-refresh-rotativo.md) | Autenticación propia con roles y refresh token rotativo | aceptada (para la demo; en producción se delega a un IdP) |
| [0008](0008-frontend-mismo-origen-nginx.md) | Portal React servido en el mismo origen que la API (nginx como proxy) | aceptada |
| [0009](0009-dms-persistente-y-explorador.md) | Sistema documental persistente y explorador tipo SharePoint | aceptada |
| [0010](0010-enlaces-y-permisos.md) | Enlaces de ThinkNex Docs, permisos y visor del destinatario | aceptada (complementa ADR-0002 y ADR-0003) |
| [0011](0011-politica-configurable.md) | Política de compartición configurable por el ADMIN | aceptada (reemplaza la matriz fija descrita en ADR-0005 y docs/02) |
| [0012](0012-actuar-como-usuario.md) | Un ADMIN puede actuar como otro usuario (suplantación auditada) | aceptada |
| [0013](0013-rag-pgvector-vertex.md) | RAG con pgvector, embeddings de Vertex AI y citas nativas de Claude | aceptada |
| [0014](0014-asistente-agentico.md) | Asistente agéntico con herramientas propias y acciones solo como propuestas | aceptada |
