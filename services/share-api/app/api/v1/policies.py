"""Política de compartición configurable: el ADMIN crea, edita, desactiva y elimina reglas."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import AdminDep, ContextDep, OversightDep, PolicyServiceDep
from app.services.policy_service import PolicyRuleIn, PolicyRuleOut

router = APIRouter(prefix="/admin/policies", tags=["policies"])


@router.get("", response_model=list[PolicyRuleOut])
def list_rules(_: OversightDep, service: PolicyServiceDep) -> list[PolicyRuleOut]:
    """Reglas vigentes y desactivadas. Las ve el ADMIN y también el AUDITOR (solo lectura)."""
    return [PolicyRuleOut.model_validate(r) for r in service.list()]


@router.post("", response_model=PolicyRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: PolicyRuleIn, user: AdminDep, service: PolicyServiceDep, ctx: ContextDep
) -> PolicyRuleOut:
    return PolicyRuleOut.model_validate(service.create(user, body, ctx))


@router.put("/{rule_id}", response_model=PolicyRuleOut)
def update_rule(
    rule_id: uuid.UUID,
    body: PolicyRuleIn,
    user: AdminDep,
    service: PolicyServiceDep,
    ctx: ContextDep,
) -> PolicyRuleOut:
    return PolicyRuleOut.model_validate(service.update(user, rule_id, body, ctx))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID, user: AdminDep, service: PolicyServiceDep, ctx: ContextDep
) -> None:
    service.delete(user, rule_id, ctx)
