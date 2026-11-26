# 1. Análisis

## 1.1 Necesidad de negocio

La organización ya tiene un sistema del que se obtienen documentos (en adelante, **DMS**). Por
necesidades del negocio esos documentos se comparten con otras personas, hoy sin control. Se
necesita:

1. **Compartir de manera segura**: que solo la persona destinataria pueda acceder, por un tiempo
   acotado, y que la organización pueda revocarlo.
2. **Trazabilidad**: registrar **quién** compartió, **cuándo** y **por qué medio**.

La segunda necesidad es la explícita. La primera es la que define el diseño: si el documento viaja
como adjunto, una vez enviado se pierde todo control y lo único que se puede registrar es el envío.

> **Idea central:** el documento nunca viaja por el canal. Viaja un **enlace a un "share"
> controlado**. El canal (email, WhatsApp, SMS) solo transporta la notificación y el código de
> verificación. Así se registra el envío **y cada acceso**, y se puede expirar, limitar y revocar.

## 1.2 Preguntas a la contraparte de negocio

Se enviaron agrupadas por WhatsApp. Si una pregunta no tuvo respuesta antes de la entrega, se usó
el **supuesto** indicado en la tabla, que siempre es la opción más conservadora y fácil de cambiar.

| # | Pregunta | Por qué importa | Supuesto si no hay respuesta |
|---|---|---|---|
| 1 | ¿Qué sistema entrega hoy los documentos? ¿Tiene API? ¿Qué formatos? | Define la integración | Existe una API REST con metadata, hash y clasificación. Mayoría PDF. Se simula con `document-api` |
| 2 | ¿Los destinatarios son internos, externos o ambos? ¿Tienen cuenta? | Define cómo se autentica al destinatario | Ambos. **Los externos no tienen cuenta**: se verifican con un OTP enviado a su propio canal |
| 3 | ¿Qué medios hay que soportar? | Define los adaptadores | Email, WhatsApp y SMS, y extensible. WhatsApp y SMS se simulan |
| 4 | ¿Qué significa "seguro" para el negocio? | Define los controles | Expiración, límite de accesos, revocación, verificación del destinatario y marca de agua |
| 5 | ¿Basta con registrar el envío, o también el acceso? | Alcance de la auditoría | Se registra todo: creación, notificación, apertura, OTP, descarga, denegaciones y revocación |
| 6 | ¿Cuánto tiempo se retiene el registro? ¿Quién lo consulta? | Retención y roles | Auditoría indefinida (sin contenido). Consulta solo el rol `AUDITOR` |
| 7 | ¿Hay documentos que nunca se pueden compartir? ¿Se requiere aprobación? | Política | Se usa la clasificación del DMS: `RESTRICTED` nunca sale a externos. Sin flujo de aprobación (queda en roadmap) |
| 8 | ¿Normativa aplicable? ¿Volumen esperado? | Cumplimiento y dimensionamiento | Ley 21.719 de protección de datos personales (Chile). Volumen bajo a medio (cientos al día) |
| 9 | ¿Existe SSO/IdP corporativo? | Autenticación interna | Sí (OIDC). En el prototipo se simula con un login de desarrollo que emite JWT |

## 1.3 Supuestos adicionales

- **S1. Interno vs. externo**: un destinatario es interno si su email pertenece al dominio
  corporativo (`INTERNAL_EMAIL_DOMAINS`). Un teléfono no prueba pertenencia, así que se trata como
  externo.
- **S2. Inmutabilidad**: lo compartido debe ser exactamente lo que el destinatario descarga, aunque
  el documento cambie en el DMS. Por eso se toma un **snapshot** al compartir (ver ADR-0002).
- **S3.** El DMS publica el `sha256` de cada documento. Si no lo hiciera, se calcularía al leerlo.
- **S4.** Quien comparte ya tiene permiso para ver el documento en el DMS. La autorización de
  lectura es responsabilidad del DMS (fuera de alcance).
- **S5.** El canal del destinatario es razonablemente confiable: el OTP llega al mismo medio que el
  enlace. Esto es una limitación conocida (ver riesgos).

## 1.4 Riesgos

| Riesgo | Impacto | Mitigación en la solución |
|---|---|---|
| Enlace reenviado a un tercero | Acceso no autorizado | OTP al canal original, límite de accesos y marca de agua con el nombre del destinatario |
| Destinatario equivocado | Fuga de información | Precheck antes de enviar, revocación inmediata y expiración corta por defecto (72 h) |
| Fuerza bruta del OTP | Acceso no autorizado | 5 intentos y el share pasa a `LOCKED`. Máximo 5 códigos por share. OTP almacenado como HMAC |
| Manipulación de la auditoría | Pérdida de evidencia | Trigger que impide UPDATE/DELETE/TRUNCATE y cadena de hashes verificable |
| Token del enlace en logs o en el header Referer | Filtración de la credencial | Rutas `/s/***` redactadas en logs, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. En BD solo se guarda el hash |
| Datos personales en la auditoría o en el LLM | Incumplimiento de la Ley 21.719 | La auditoría guarda contactos enmascarados y conteos, nunca valores. Al LLM solo llega texto redactado |
| Previsualizadores de enlaces (bots de email o WhatsApp) | Consumo indebido de accesos | El GET de la página no consume accesos. Solo la descarga, tras el OTP, los consume |
| Canal del destinatario comprometido | El OTP llega al atacante | **Limitación aceptada**. Mitigable en el futuro con OTP por un canal distinto o identidad federada |
| DMS caído o contenido alterado en tránsito | Share inconsistente | Se verifica el sha256 al leer del DMS (502 si no coincide) y nuevamente al descargar el snapshot |

## 1.5 Alcance y prioridades

**Prioridad 1 (prototipo ejecutable)**
- Compartir un documento del DMS por email, WhatsApp o SMS, con expiración y límite de accesos.
- Acceso del destinatario: enlace, OTP y descarga con marca de agua.
- Revocación y vencimiento.
- Auditoría completa append-only con verificación de integridad y consulta por rol auditor.
- Política de sensibilidad (clasificación × datos personales × destinatario).

**Prioridad 2 (incluido, opcional)**
- Clasificación de sensibilidad asistida por LLM (Claude), detrás de un flag.

**Fuera de alcance (ver [05-limitaciones-y-roadmap.md](05-limitaciones-y-roadmap.md))**
- Frontend completo para usuarios internos (se usa Swagger).
- Integración real con WhatsApp Business o un proveedor SMS (se simula).
- SSO real, flujo de aprobación y visor en línea sin descarga.
