# ADR-0003: Enlace de un solo destinatario + OTP por el mismo canal

**Estado:** aceptada

## Contexto
Los destinatarios externos no tienen cuenta. Hay que verificar que quien accede es el destinatario,
sin exigirle registro.

## Decisión
1. El canal transporta un enlace `/s/{token}` con un token de 256 bits. En la BD solo se guarda su
   `sha256`, y el token nunca se devuelve a quien comparte.
2. Para descargar, el destinatario pide un OTP de 6 dígitos que llega a su mismo contacto. Se
   guarda como HMAC ligado al share, con TTL de 10 min, 5 intentos (luego `LOCKED`) y 5 códigos
   por share.
3. El OTP correcto entrega un JWT de descarga de 5 min (`typ=download`, `sub=share_id`).
4. Cada descarga consume un acceso con un `UPDATE ... WHERE access_count < max_accesses` atómico.

## Alternativas descartadas
- **Enlace mágico sin OTP:** quien reciba un reenvío accede al documento.
- **Cuentas para los destinatarios externos:** fricción alta para un acceso puntual y otra base de
  identidades que administrar.
- **Adjuntar el archivo cifrado y enviar la clave por otro medio:** el archivo sale igual, no se
  puede revocar y no hay registro de acceso.
- **OTP por un segundo canal:** más seguro, pero exige dos datos de contacto por destinatario.
  Queda en el roadmap.

## Consecuencias
- Un enlace reenviado no basta: el tercero no recibe el OTP.
- Los previsualizadores automáticos no consumen accesos, porque el GET es de solo lectura.
- Limitación: si el canal del destinatario está comprometido, el atacante recibe enlace y OTP.
  Queda documentado en el roadmap (segundo canal o identidad federada).
