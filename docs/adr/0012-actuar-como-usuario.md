# ADR-0012: Un ADMIN puede actuar como otro usuario (suplantación auditada)

**Estado:** aceptada

## Contexto
Para probar la plataforma se necesitaba entrar con varias cuentas (emisora, auditora y
administrador). El administrador necesita asumir la identidad de otro usuario y hacer todo
como él desde un solo perfil.

## Decisión
- **Inicio:** `POST /api/v1/auth/impersonate` (solo ADMIN, con el header anti-CSRF). Cierra la
  sesión del administrador y emite una sesión del usuario elegido:
  - el access token lleva el claim `act` (RFC 8693) con el id del administrador;
  - el refresh token guarda `impersonator_id` (migración `0007`);
  - la sesión dura como máximo 8 horas y se renueva conservando quién está detrás.
- **Durante:** la API trata la sesión como el usuario suplantado: mismos roles y permisos. Si el
  administrador deja de estar activo o pierde el rol ADMIN, la sesión deja de servir de inmediato.
- **Límites:**
  - no se puede actuar como otro ADMIN ni como uno mismo;
  - desde una sesión suplantada no hay acceso a la administración, porque el usuario suplantado
    no es ADMIN.
- **Fin:** `POST /api/v1/auth/impersonation/stop` revoca la sesión suplantada y abre una sesión
  nueva del administrador.
- **Auditoría:**
  - `IMPERSONATION_STARTED` e `IMPERSONATION_ENDED` registran al administrador y al usuario;
  - cada evento hecho durante la suplantación queda a nombre del usuario, con
    `impersonated_by` = email del administrador. La pantalla Auditoría lo muestra como "vía …".
- **Portal:**
  - *Usuarios → Actuar como este usuario*;
  - mientras dura, un aviso fijo muestra "Actuando como …" con el botón **Volver a mi cuenta**.

## Consecuencias
- La responsabilidad queda trazada: nada de lo hecho por el administrador se confunde con una
  acción del usuario real, aunque la API lo trate como él.
- Un usuario con contraseña temporal puede suplantarse sin forzar el cambio de su contraseña.
