# ADR-0007: Autenticación propia con roles y refresh token rotativo

**Estado:** aceptada (para la demo; en producción se delega a un IdP)

## Contexto
El portal necesita usuarios, roles y administración. Los evaluadores deben poder entrar sin
cuentas en un tenant corporativo.

## Decisión
- **Usuarios en la BD** con contraseña **argon2id**, política mínima, contraseña temporal con
  cambio obligatorio y bloqueo de 15 minutos tras 5 intentos fallidos. Si el usuario no existe, se
  ejecuta igual un hash ficticio, para que el tiempo de respuesta no revele si la cuenta existe.
- **Roles combinables:**

  | Rol | Puede |
  |---|---|
  | SHARER | Compartir y revocar sus envíos |
  | AUDITOR | Leer la auditoría y todos los envíos |
  | ADMIN | Usuarios, todos los envíos, bandeja y retención |

  **Separación de funciones:** el ADMIN no lee la auditoría por defecto, porque sus propias
  acciones quedan registradas allí.
- **Sesión:**
  - Access token JWT de 15 minutos, que el cliente guarda **solo en memoria**.
  - Refresh token opaco en una cookie `httpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`.
  - El refresh se **rota en cada uso**. Si llega un refresh ya rotado, se revoca toda la familia
    (la sesión) y se audita `TOKEN_REUSE_DETECTED`.
  - Como defensa adicional contra CSRF, `refresh` y `logout` exigen el header
    `X-Requested-With: fetch`.
- **Autorización siempre en el servidor:** usuario y roles se leen de la BD en cada request, así que
  desactivar a alguien corta su acceso de inmediato. El frontend solo oculta lo que no corresponde.
- **Protección contra quedarse sin administradores:** la API impide quitarse a sí mismo el rol
  ADMIN o desactivarse, y exige que siempre quede al menos un ADMIN activo.

## Camino a producción
Reemplazar el login por **OIDC (Microsoft Entra ID o Google Workspace)** y mapear grupos a roles.
El resto de la API no cambia: solo depende de identificar al usuario y sus roles.

## Consecuencias
- Hay una base de usuarios más que administrar (aceptable en la demo).
- Dos pestañas que refresquen exactamente al mismo tiempo pueden disparar la detección de
  reutilización. El cliente serializa los refresh para evitarlo.
