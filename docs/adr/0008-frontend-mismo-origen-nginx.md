# ADR-0008: Portal React servido en el mismo origen que la API (nginx como proxy)

**Estado:** aceptada

## Contexto
El portal (SPA) y la API son servicios distintos en Cloud Run, con dominios distintos. Usar una
cookie de refresh `SameSite=Strict` entre dominios distintos no funciona, y abrir CORS con
credenciales amplía la superficie de ataque.

## Decisión
- El contenedor `web` (nginx sin privilegios) sirve la SPA y hace de **reverse proxy** de `/api/*` y
  `/s/*` hacia share-api, verificando TLS. Para el navegador existe **un solo origen**.
- Los headers de seguridad de la SPA (CSP estricta, HSTS, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`) los pone nginx. Las respuestas proxeadas conservan los de share-api; la
  página del destinatario tiene su propia CSP con nonce.
- Los enlaces `/s/{token}` no se registran en el access log de nginx.
- **Stack:** React 19, Vite, TypeScript estricto, Mantine, TanStack Query, React Router, y un cliente
  tipado generado desde el OpenAPI (`npm run gen:api`). Las páginas se cargan de forma diferida
  (code splitting).

## Alternativas descartadas
- **CORS con credenciales:** más configuración y más riesgo.
- **Load Balancer con enrutamiento por ruta:** cuesta ~US$18/mes, desproporcionado para la demo.
- **Firebase Hosting con rewrites:** otra plataforma más que administrar.

## Consecuencias
- Agrega un salto de red (nginx → share-api), de unos pocos milisegundos.
- En local, el mismo esquema funciona con `docker compose` (`:8080`) o con el proxy de Vite (`:5173`).
