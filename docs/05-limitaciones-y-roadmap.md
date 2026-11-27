# 5. Limitaciones y funcionalidades pendientes

## Limitaciones conocidas del prototipo

| Limitación | Impacto | Cómo se resolvería |
|---|---|---|
| Autenticación propia (usuarios y contraseñas en la plataforma) | Una base de usuarios más que administrar | IdP corporativo (OIDC: Entra ID o Google Workspace) con grupos mapeados a roles (ADR-0007) |
| WhatsApp y SMS simulados | No hay entrega real | Adaptadores para WhatsApp Business Cloud API (plantillas aprobadas) y un proveedor SMS, con la misma interfaz `ChannelAdapter` |
| El OTP llega por el mismo canal que el enlace | Si el canal está comprometido, ambos lo están | OTP por un segundo canal (email + SMS) o identidad federada para destinatarios recurrentes |
| Envío de la notificación síncrono en la request | Si el proveedor tarda, la request tarda | Outbox transaccional y worker (la tabla `notifications` ya existe) con reintentos y reenvío |
| Marca de agua solo en PDF | Otros formatos se entregan sin marca (queda auditado `watermarked: false`) | Conversión a PDF o visor en línea |
| Bandeja simulada guarda enlaces y OTP en claro | Solo aceptable en la demo | `SIMULATED_INBOX_ENABLED=false` en producción; tiene TTL de 7 días y solo la ve un ADMIN |
| Cadena de auditoría serializada con advisory lock | Limita la escritura concurrente de eventos (suficiente para cientos o miles al día) | Cadenas por partición (por día o por tenant) o anclaje periódico del hash en un almacenamiento WORM |
| Sin rate limiting por IP | Mitigado por los límites por share y el bloqueo de cuentas | Cloud Armor o un WAF delante de Cloud Run |
| Cloud SQL con IP pública (restringida al conector) | Superficie de red mayor que una IP privada | IP privada con Direct VPC egress |
| El snapshot no está cifrado a nivel de aplicación | Depende del cifrado en reposo del proveedor S3 | SSE-KMS en el bucket, o cifrado envolvente por documento |
| Portal propio, separado del DMS | El usuario cambia de sistema para compartir | Integrar un botón "Compartir" dentro del DMS que abra el asistente |

## Roadmap sugerido (por valor)

1. **SSO corporativo (OIDC) y autorización delegada al DMS**: verificar que quien comparte puede ver el
   documento (hoy es un supuesto, S4).
2. **Outbox y reenvío de notificaciones**: `POST /shares/{id}/resend` y worker con reintentos.
3. **Integración real de WhatsApp Business y SMS** con webhooks de estado de entrega (`delivered`,
   `read`) agregados a la auditoría.
4. **Flujo de aprobación** para `RESTRICTED` y `CONFIDENTIAL` hacia externos (en vez de solo advertir).
5. **Visor en línea** sin descarga para documentos sensibles.
6. **Reportes de auditoría** (export CSV y firmado) y alertas ante patrones anómalos: muchos
   `ACCESS_DENIED`, accesos desde países inesperados.
7. **Anclaje del hash de la cadena** (diario) en un almacenamiento inmutable (S3 Object Lock).

## Lo que deliberadamente NO se hizo

- **RAG sobre los documentos o agentes conversacionales.** No responden a la necesidad planteada.
  La IA se usó donde aporta un control de seguridad concreto (ADR-0005) y queda desactivada por
  defecto.
- **Microservicios, colas o Kubernetes.** Desproporcionados para el problema (ADR-0001). El despliegue
  usa Cloud Run, que escala a cero (ADR-0006).
