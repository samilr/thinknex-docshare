import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User
from tests.integration.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Api

pytestmark = pytest.mark.integration
FETCH = {"X-Requested-With": "fetch"}
PWD = "Valid-password-123"


def make_user(api: Api, *, roles: list[str], must_change: bool = False, active: bool = True) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@demo-corp.example"
    with api.components.session_factory() as db, db.begin():
        db.add(
            User(
                email=email,
                name="Usuario Test",
                roles=roles,
                password_hash=hash_password(PWD),
                must_change_password=must_change,
                is_active=active,
            )
        )
    return email


def login(api: Api, email: str, password: str = PWD) -> dict[str, object]:
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body: dict[str, object] = r.json()
    return body


def bearer(session: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def refresh_with(api: Api, token: str) -> int:
    api.client.cookies.clear()
    r = api.client.post(
        "/api/v1/auth/refresh", headers={**FETCH, "Cookie": f"refresh_token={token}"}
    )
    return r.status_code


def test_login_sets_httponly_refresh_cookie(api: Api) -> None:
    email = make_user(api, roles=["SHARER"])
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie
    me = api.client.get("/api/v1/auth/me", headers=bearer(r.json())).json()
    assert me["email"] == email and me["roles"] == ["SHARER"]


def test_bootstrap_admin_exists(api: Api) -> None:
    session = login(api, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert session["user"]["roles"] == ["ADMIN"]  # type: ignore[index]


def test_wrong_password_locks_account(api: Api) -> None:
    email = make_user(api, roles=["SHARER"])
    for _ in range(5):
        r = api.client.post("/api/v1/auth/login", json={"email": email, "password": "nope-nope-1"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Usuario o contraseña inválidos"
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 401, "bloqueada aunque la contraseña sea correcta"
    with api.components.session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None and user.locked_until is not None
    assert api.audit(event_type="USER_LOCKED", actor_id=str(user.id))


def test_unknown_user_gets_same_error_and_is_audited(api: Api) -> None:
    r = api.client.post(
        "/api/v1/auth/login", json={"email": "nadie@demo-corp.example", "password": "x-1234567"}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña inválidos"
    failed = api.audit(event_type="USER_LOGIN_FAILED")
    assert failed[0]["metadata"]["email"] == "n***@demo-corp.example"  # type: ignore[index]


def test_refresh_rotation_and_reuse_detection(api: Api) -> None:
    email = make_user(api, roles=["SHARER"])
    api.client.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    first = api.client.cookies.get("refresh_token")
    assert first

    assert api.client.post("/api/v1/auth/refresh").status_code == 403, "requiere X-Requested-With"
    r = api.client.post("/api/v1/auth/refresh", headers=FETCH)
    assert r.status_code == 200
    second = api.client.cookies.get("refresh_token")
    assert second and second != first

    assert refresh_with(api, first) == 401, "token rotado reutilizado"
    assert refresh_with(api, second) == 401, "la familia completa quedó revocada"
    assert api.audit(event_type="TOKEN_REUSE_DETECTED")


def test_logout_revokes_refresh(api: Api) -> None:
    email = make_user(api, roles=["SHARER"])
    api.client.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    token = api.client.cookies.get("refresh_token")
    assert token
    assert api.client.post("/api/v1/auth/logout", headers=FETCH).status_code == 204
    assert refresh_with(api, token) == 401


def test_must_change_password_flow(api: Api) -> None:
    email = make_user(api, roles=["SHARER"], must_change=True)
    session = login(api, email)
    assert session["user"]["must_change_password"] is True  # type: ignore[index]
    assert api.client.get("/api/v1/shares", headers=bearer(session)).status_code == 403
    assert api.client.get("/api/v1/auth/me", headers=bearer(session)).status_code == 200

    weak = api.client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PWD, "new_password": "corta"},
        headers=bearer(session),
    )
    assert weak.status_code == 422
    r = api.client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PWD, "new_password": "Otra-clave-segura-9"},
        headers=bearer(session),
    )
    assert r.status_code == 200
    assert api.client.get("/api/v1/shares", headers=bearer(r.json())).status_code == 200
    login(api, email, "Otra-clave-segura-9")


def test_deactivated_user_loses_access_immediately(api: Api) -> None:
    email = make_user(api, roles=["SHARER"])
    session = login(api, email)
    with api.components.session_factory() as db, db.begin():
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_active = False
    assert api.client.get("/api/v1/shares", headers=bearer(session)).status_code == 401
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 401
