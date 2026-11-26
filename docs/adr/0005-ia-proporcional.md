# ADR-0005: IA proporcional, chequeo de sensibilidad antes de compartir

**Estado:** aceptada

## Contexto
El cargo está orientado a RAG, pero el problema no es de recuperación de información. Incorporar IA
solo tiene sentido si mejora un objetivo del negocio: compartir **de forma segura**.

## Decisión
Antes de compartir se evalúa la sensibilidad en dos capas:

1. **Reglas deterministas (siempre activas):** RUT con dígito verificador, email, teléfono
   chileno, tarjeta (Luhn) y cuenta bancaria. Son explicables, sin costo y no envían datos fuera.
2. **LLM opcional** (`SENSITIVITY_LLM_ENABLED`, Claude Haiku 5.5 con salida estructurada y esfuerzo
   bajo): detecta sensibilidad que las reglas no ven (estrategia, temas legales o de salud).
   - Recibe el texto **ya redactado** (`[RUT]`, `[EMAIL]`, …) y truncado a
     `SENSITIVITY_LLM_MAX_CHARS`. El reporte indica si hubo truncamiento.
   - El prompt trata el documento como dato, no como instrucciones (defensa ante prompt injection).
   - Solo puede elevar `ALLOW` a `WARN` hacia externos. **Nunca bloquea.**
   - Ante timeout, rate limit o rechazo, degrada a "solo reglas" sin interrumpir el flujo.

La decisión final (`ALLOW`, `WARN` o `BLOCK`) la toma una política explícita y testeada
(`app/sensitivity/policy.py`).

## Alternativas descartadas
- RAG o un asistente sobre los documentos: no resuelve la necesidad.
- Decisión 100 % por LLM: no determinista, difícil de auditar y con falsos positivos bloqueantes.

## Consecuencias
Con la IA desactivada (por defecto) la solución es completa. Activarla requiere evaluar con el
área legal el envío de texto, aunque esté redactado, a un proveedor externo.
