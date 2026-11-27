"""Un ADMIN actúa como otro usuario; todo queda auditado con impersonated_by."""

import pytest

from tests.integration.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Api

pytestmark = pytest.mark.integration
FETCH = {"X-Requested-With": "fetch"}


def _user_id(api: Api, admin: dict[str, str], email: str) -> str:
    users = api.client.get("/api/v1/admin/users", params={"limit": 100}, headers=admin).json()
    return next(u["id"] for u in users["items"] if u["email"] == email)


def test_admin_acts_as_user_and_returns(api: Api) -> None:
    login = api.client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ana_id = _user_id(api, admin, "ana@thinknex.example")

    r = api.client.post(
        "/api/v1/auth/impersonate", json={"user_id": ana_id}, headers={**admin, **FETCH}
    )
    assert r.status_code == 200, r.text
    session = r.json()
    assert session["user"]["email"] == "ana@thinknex.example"
    assert session["user"]["impersonator"]["email"] == ADMIN_EMAIL
    as_ana = {"Authorization": f"Bearer {session['access_token']}"}

    me = api.client.get("/api/v1/auth/me", headers=as_ana).json()
    assert me["impersonator"]["email"] == ADMIN_EMAIL
    assert api.client.get("/api/v1/admin/users", headers=as_ana).status_code == 403

    share = api.client.post(
        "/api/v1/shares",
        json={
            "document_id": "doc-public",
            "recipient": {"name": "Pedro", "email": "pedro@cliente.example"},
            "channel": "EMAIL",
            "reason": "Prueba como Ana",
        },
        headers=as_ana,
    )
    assert share.status_code == 201, share.text
    assert share.json()["shared_by"] == "ana@thinknex.example"
    created = api.audit(share_id=share.json()["id"], event_type="SHARE_CREATED")[0]
    assert created["actor"] == "Ana Rojas <ana@thinknex.example>"
    assert created["metadata"]["impersonated_by"] == ADMIN_EMAIL  # type: ignore[index]

    # La sesión suplantada se renueva conservando quién está detrás.
    refreshed = api.client.post("/api/v1/auth/refresh", headers=FETCH).json()
    assert refreshed["user"]["impersonator"]["email"] == ADMIN_EMAIL

    back = api.client.post("/api/v1/auth/impersonation/stop", headers=FETCH)
    assert back.status_code == 200, back.text
    assert back.json()["user"]["email"] == ADMIN_EMAIL
    assert back.json()["user"]["impersonator"] is None
    # La sesión suplantada ya no sirve para renovar.
    assert api.client.post("/api/v1/auth/impersonation/stop", headers=FETCH).status_code == 401

    started = api.audit(event_type="IMPERSONATION_STARTED")[0]
    assert started["metadata"]["target_email"] == "ana@thinknex.example"  # type: ignore[index]
    assert api.audit(event_type="IMPERSONATION_ENDED")[0]["actor"].startswith("Administrador")  # type: ignore[union-attr]


def test_impersonation_rules(api: Api) -> None:
    admin = api.admin_headers()
    admin_id = _user_id(api, admin, ADMIN_EMAIL)
    r = api.client.post(
        "/api/v1/auth/impersonate", json={"user_id": admin_id}, headers={**admin, **FETCH}
    )
    assert r.status_code == 422, "no puede actuar como sí mismo"
    carla_id = _user_id(api, admin, "carla@thinknex.example")
    carla = api.headers("carla@thinknex.example")
    r = api.client.post(
        "/api/v1/auth/impersonate", json={"user_id": carla_id}, headers={**carla, **FETCH}
    )
    assert r.status_code == 403, "solo un ADMIN"
    r = api.client.post("/api/v1/auth/impersonate", json={"user_id": carla_id}, headers=admin)
    assert r.status_code == 403, "exige el header anti-CSRF"
