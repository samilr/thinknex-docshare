# ADR-0012: Un ADMIN puede actuar como otro usuario (suplantación auditada)

**Estado:** aceptada

## Contexto
Soporte y QA necesitan reproducir lo que ve y puede hacer un usuario concreto (emisora, auditora)
sin conocer su contraseña. Iniciar sesión con varias cuentas no escala, y reiniciar contraseñas
ajenas rompe la trazabilidad.

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

## Alternativas descartadas
- **Compartir o reiniciar la contraseña del usuario:** la auditoría no distingue al administrador
  del usuario real.
- **Modo "ver como" de solo lectura:** no permite probar acciones como compartir o revocar.
- **Token del administrador con los roles del usuario:** mezcla identidades. Los permisos por
  dueño (mis envíos, mis documentos) dejarían de funcionar.

## Consecuencias
- La responsabilidad queda trazada: nada de lo hecho por el administrador se confunde con una
  acción del usuario real, aunque la API lo trate como él.
- Un usuario con contraseña temporal puede suplantarse sin forzar el cambio de su contraseña.
