import uuid

import pytest

from tests.integration.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Api

pytestmark = pytest.mark.integration
FETCH = {"X-Requested-With": "fetch"}


def admin_headers(api: Api) -> dict[str, str]:
    r = api.client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_email() -> str:
    return f"nuevo-{uuid.uuid4().hex[:6]}@demo-corp.example"


def test_admin_user_lifecycle(api: Api) -> None:
    admin = admin_headers(api)
    email = new_email()
    r = api.client.post(
        "/api/v1/admin/users",
        json={"email": email, "name": "Nueva Persona", "roles": ["SHARER"]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    user_id, temporary = r.json()["user"]["id"], r.json()["temporary_password"]
    assert r.json()["user"]["must_change_password"] is True

    dup = api.client.post(
        "/api/v1/admin/users",
        json={"email": email, "name": "x", "roles": ["SHARER"]},
        headers=admin,
    )
    assert dup.status_code == 409

    login = api.client.post("/api/v1/auth/login", json={"email": email, "password": temporary})
    assert login.json()["user"]["must_change_password"] is True

    r = api.client.patch(
        f"/api/v1/admin/users/{user_id}", json={"roles": ["SHARER", "AUDITOR"]}, headers=admin
    )
    assert r.status_code == 200 and r.json()["roles"] == ["AUDITOR", "SHARER"]
    updated = api.audit(event_type="USER_UPDATED")[0]
    assert updated["metadata"]["changes"]["roles"]["to"] == ["AUDITOR", "SHARER"]  # type: ignore[index]

    r = api.client.post(f"/api/v1/admin/users/{user_id}/reset-password", headers=admin)
    second = r.json()["temporary_password"]
    assert second != temporary
    bad = api.client.post("/api/v1/auth/login", json={"email": email, "password": temporary})
    assert bad.status_code == 401

    api.client.post("/api/v1/auth/login", json={"email": email, "password": second})
    refresh_cookie = api.client.cookies.get("refresh_token")
    r = api.client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=admin)
    assert r.json()["is_active"] is False
    api.client.cookies.clear()
    r = api.client.post(
        "/api/v1/auth/refresh", headers={**FETCH, "Cookie": f"refresh_token={refresh_cookie}"}
    )
    assert r.status_code == 401, "desactivar revoca las sesiones"


def test_admin_cannot_lock_themselves_out(api: Api) -> None:
    admin = admin_headers(api)
    me = api.client.get("/api/v1/auth/me", headers=admin).json()
    r = api.client.patch(
        f"/api/v1/admin/users/{me['id']}", json={"roles": ["SHARER"]}, headers=admin
    )
    assert r.status_code == 409
    r = api.client.patch(
        f"/api/v1/admin/users/{me['id']}", json={"is_active": False}, headers=admin
    )
    assert r.status_code == 409


def test_admin_endpoints_require_admin(api: Api) -> None:
    for email in ("ana@demo-corp.example", "carla@demo-corp.example"):
        headers = api.headers(email)
        assert api.client.get("/api/v1/admin/users", headers=headers).status_code == 403
        assert api.client.get("/api/v1/admin/inbox", headers=headers).status_code == 403


def test_share_visibility_by_role(api: Api) -> None:
    share = api.share()  # ana
    sid = share["id"]
    bruno, carla, admin = (
        api.headers("bruno@demo-corp.example"),
        api.headers("carla@demo-corp.example"),
        admin_headers(api),
    )
    mine = api.client.get("/api/v1/shares", headers=bruno).json()
    assert all(item["id"] != sid for item in mine["items"])
    assert api.client.get("/api/v1/shares?scope=all", headers=bruno).status_code == 403
    assert api.client.get(f"/api/v1/shares/{sid}", headers=bruno).status_code == 404

    all_for_auditor = api.client.get("/api/v1/shares?scope=all&limit=100", headers=carla).json()
    assert any(item["id"] == sid for item in all_for_auditor["items"])
    assert api.client.get(f"/api/v1/shares/{sid}", headers=carla).status_code == 200
    assert api.client.post(f"/api/v1/shares/{sid}/revoke", headers=carla).status_code == 403

    r = api.client.post(f"/api/v1/shares/{sid}/revoke", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "REVOKED"
    revoked = api.audit(event_type="SHARE_REVOKED", share_id=str(sid))[0]
    assert revoked["metadata"]["by_owner"] is False  # type: ignore[index]


def test_share_filters_and_timeline(api: Api) -> None:
    share = api.share(channel="SMS", recipient={"name": "Fono", "phone": "+56 9 5555 6666"})
    ana = api.headers("ana@demo-corp.example")
    page = api.client.get("/api/v1/shares?channel=SMS&status=ACTIVE", headers=ana).json()
    assert page["total"] >= 1 and all(i["channel"] == "SMS" for i in page["items"])
    timeline = api.client.get(f"/api/v1/shares/{share['id']}/timeline", headers=ana).json()
    assert [e["event_type"] for e in timeline][:2] == ["SHARE_CREATED", "NOTIFICATION_SENT"]
    assert timeline[0]["actor"] == "Ana Rojas <ana@demo-corp.example>"


def test_inbox_and_stats(api: Api) -> None:
    share = api.share()
    admin = admin_headers(api)
    inbox = api.client.get(f"/api/v1/admin/inbox?share_id={share['id']}", headers=admin).json()
    assert inbox["total"] == 1 and "/s/" in inbox["items"][0]["body"]

    mine = api.client.get("/api/v1/stats", headers=api.headers("ana@demo-corp.example")).json()
    assert mine["scope"] == "mine" and mine["shares_total"] >= 1 and mine["users_active"] is None
    assert len(mine["accesses_by_day"]) == 7
    overall = api.client.get("/api/v1/stats", headers=api.headers("carla@demo-corp.example")).json()
    assert overall["scope"] == "all" and overall["users_active"] >= 4
    assert overall["shares_total"] >= mine["shares_total"]


def test_admin_can_run_retention(api: Api) -> None:
    r = api.client.post("/api/v1/admin/retention/run", headers=admin_headers(api))
    assert r.status_code == 200
    assert set(r.json()) == {"expired_shares", "purged_snapshots", "purged_inbox_messages"}
