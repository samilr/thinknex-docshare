# ADR-0011: Política de compartición configurable por el ADMIN

**Estado:** aceptada (reemplaza la matriz fija descrita en ADR-0005 y docs/02)

## Contexto
La política era una matriz fija en el código (clasificación × datos personales × interno o
externo). El administrador necesita crear, modificar y eliminar
políticas. El ejemplo concreto: un documento que solo contiene un email pedía confirmación al
compartirlo hacia afuera, y la organización quería relajar esa regla sin desplegar código.

## Decisión
1. **Reglas en la base de datos** (`policy_rules`, migración `0005`). Cada regla tiene:
   - acción: **Advertir** (pide confirmación) o **Bloquear**;
   - el mensaje que verá quien comparte;
   - condiciones, donde una lista vacía significa "cualquiera":
     - clasificaciones del documento;
     - destinatario interno, externo o cualquiera;
     - tipos de datos detectados (aplica si hay al menos uno);
     - canales;
     - quién abre el enlace (persona específica o cualquiera con el enlace).
2. **Evaluación:** se evalúan todas las reglas activas y **gana la más restrictiva**. Si ninguna
   aplica, el envío se permite. La migración siembra cuatro reglas equivalentes a la matriz
   original, así que el comportamiento no cambia hasta que el ADMIN lo decida.
3. **Fuera de las reglas, y fijos:**
   - la IA solo puede advertir (ADR-0005);
   - un documento que no se pudo analizar pide confirmación;
   - "cualquiera con el enlace" se bloquea si el contenido no se pudo analizar o la IA lo
     evaluó como de sensibilidad alta. El resto de lo que bloquea esos enlaces son reglas
     editables sembradas por la migración `0006` ("Enlace para cualquiera con datos personales"
     y "… con documentos confidenciales");
   - la edición por destinatarios no se permite sobre documentos RESTRICTED.
4. **Gobierno:**
   - solo el ADMIN modifica;
   - el AUDITOR puede leer;
   - cada alta, cambio o baja queda en la auditoría encadenada (`POLICY_CREATED`,
     `POLICY_UPDATED`, `POLICY_DELETED`) con quién, cuándo y el valor anterior y nuevo;
   - cada evaluación registra qué reglas aplicaron (`matched_rules` en `SENSITIVITY_CHECKED`).
5. **Reclasificar un documento** también cambia qué reglas aplican, por eso solo puede hacerlo un
   ADMIN y queda auditado (`DOCUMENT_RECLASSIFIED`).

## Alternativas descartadas
- **Motor de reglas genérico (OPA/Rego, CEL):** potente, pero exige escribir código de política. Un
  formulario con condiciones cubre los casos del negocio y es auditable campo a campo.
- **Orden de prioridad (la primera regla gana):** más flexible para excepciones, pero difícil de
  razonar: el resultado depende del orden. "Gana la más restrictiva" es predecible: para relajar se
  edita o desactiva la regla que molesta.

## Consecuencias
- Un ADMIN puede dejar la organización sin controles (por ejemplo, eliminando todas las reglas). Se
  acepta: es su rol, y queda trazado en la auditoría con el detalle de lo eliminado.
- La política vigente en un momento dado se reconstruye desde la auditoría.
