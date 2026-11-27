# 5. Limitaciones y funcionalidades pendientes

## Limitaciones conocidas del prototipo

| Limitación | Impacto | Cómo se resolvería |
|---|---|---|
| Autenticación propia (usuarios y contraseñas en la plataforma) | Una base de usuarios más que administrar | IdP corporativo (OIDC: Entra ID o Google Workspace) con grupos mapeados a roles (ADR-0007) |
| WhatsApp y SMS simulados | No hay entrega real | Adaptadores para WhatsApp Business Cloud API (plantillas aprobadas) y un proveedor SMS, con la misma interfaz `ChannelAdapter` |
| El OTP llega por el mismo canal que el enlace | Si el canal está comprometido, ambos lo están | OTP por un segundo canal (email + SMS) o identidad federada para destinatarios recurrentes |
| Envío de la notificación síncrono en la request | Si el proveedor tarda, la request tarda | Outbox transaccional y worker (la tabla `notifications` ya existe) con reintentos y reenvío |
| Marca de agua de la descarga solo en PDF | Otros formatos se descargan sin marca (queda auditado `watermarked: false`); en el visor, PDF e imágenes siempre llevan marca | Conversión a PDF al compartir |
| Visor protegido solo para PDF, imágenes y texto | Word y Excel se muestran como "vista previa no disponible" (con *Solo ver* no hay forma de abrirlos) | Conversión a PDF en el servidor (LibreOffice headless en un job) antes de renderizar |
| La vista protegida no evita capturas de pantalla | Ningún visor web puede impedirlo | La marca de agua con identidad, fecha y referencia deja trazabilidad visible en cada página (ADR-0010) |
| "Cualquiera con el enlace" no identifica a la persona | La auditoría registra IP y user agent, no una identidad | Limitado por política a documentos sin datos sensibles; para lo demás, persona específica |
| Edición por destinatario = subir una versión completa | No hay coedición en línea | Integración con un editor (Office Online / WOPI) sobre el archivo vivo |
| Bandeja simulada guarda enlaces y OTP en claro | Solo aceptable en la demo | `SIMULATED_INBOX_ENABLED=false` en producción; tiene TTL de 7 días y solo la ve un ADMIN |
| Cadena de auditoría serializada con advisory lock | Limita la escritura concurrente de eventos (suficiente para cientos o miles al día) | Cadenas por partición (por día o por tenant) o anclaje periódico del hash en un almacenamiento WORM |
| Sin rate limiting por IP | Mitigado por los límites por share y el bloqueo de cuentas | Cloud Armor o un WAF delante de Cloud Run |
| Cloud SQL con IP pública (restringida al conector) | Superficie de red mayor que una IP privada | IP privada con Direct VPC egress |
| El snapshot no está cifrado a nivel de aplicación | Depende del cifrado en reposo del proveedor S3 | SSE-KMS en el bucket, o cifrado envolvente por documento |
| Portal propio, separado del DMS | El usuario cambia de sistema para compartir | Integrar un botón "Compartir" dentro del DMS que abra el asistente |
| IA: PDF escaneados e imágenes sin OCR | Quedan `EMPTY` en el índice: el asistente no puede citarlos | OCR con visión de Claude Haiku o Document AI en el indexador |
| IA: calidad sin evals automatizadas | La calidad se verificó con pruebas y E2E reales, no con métricas | Conjunto de preguntas de oro: recall@k, exactitud de citas, fidelidad (juez LLM), rechazo y fuga de permisos = 0 ([08-ia.md](08-ia.md#811-pendiente)) |
| IA: las respuestas pueden equivocarse | Un resumen puede omitir matices | Citas obligatorias que abren la página fuente, aviso en el chat y acciones solo como propuestas confirmadas |
| IA: embeddings en São Paulo | Los textos salen de Santiago (dentro del mismo proyecto GCP) | Cambiar `VERTEX_LOCATION` cuando el modelo esté en `southamerica-west1` |
| IA: el visor del destinatario aún no tiene preguntas | Solo los usuarios internos usan el asistente | Preguntas acotadas al snapshot compartido, con una opción por envío (planificado) |

## Roadmap sugerido (por valor)

1. **SSO corporativo (OIDC) y autorización delegada al DMS**: verificar que quien comparte puede ver el
   documento (hoy es un supuesto, S4).
2. **Outbox y reenvío de notificaciones**: `POST /shares/{id}/resend` y worker con reintentos.
3. **Integración real de WhatsApp Business y SMS** con webhooks de estado de entrega (`delivered`,
   `read`) agregados a la auditoría.
4. **Flujo de aprobación** para `RESTRICTED` y `CONFIDENTIAL` hacia externos (en vez de solo advertir).
5. **IA, siguientes pasos** ([08-ia.md](08-ia.md#811-pendiente)):
   - preguntas del destinatario sobre su documento;
   - sugerencia de clasificación al subir;
   - políticas desde lenguaje natural;
   - explicación de la auditoría con anomalías;
   - evals de RAG y OCR.
6. **Reportes de auditoría** (export CSV y firmado) y alertas ante patrones anómalos: muchos
   `ACCESS_DENIED`, accesos desde países inesperados.
7. **Anclaje del hash de la cadena** (diario) en un almacenamiento inmutable (S3 Object Lock).

## Lo que deliberadamente NO se hizo

- **IA que decide sola.**
  - En la primera versión la IA solo se usó como control de seguridad (ADR-0005).
  - Después se agregaron RAG con citas y un asistente agéntico (ADR-0013, ADR-0014), con una regla
    fija: la IA nunca ejecuta acciones. Propone, y un humano confirma por los endpoints normales.
  - Tampoco se usa la IA para bloquear: solo advierte.
- **Microservicios, colas o Kubernetes.** Desproporcionados para el problema (ADR-0001). El despliegue
  usa Cloud Run, que escala a cero (ADR-0006).
