"""Tests de integración contra Postgres real (triggers, advisory locks, JSONB).

Requiere TEST_DATABASE_URL (por defecto la BD share_test del docker compose). Si no hay
conexión, los tests se marcan como skip en lugar de fallar.
"""

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError

from app.adapters.channels.base import ChannelRegistry, DeliveryResult, OutboundMessage
from app.adapters.storage import InMemoryBlobStorage
from app.container import Components
from app.core.config import Settings
from app.db.models import SimulatedMessage
from app.db.seed import seed_users
from app.db.session import session_factory
from app.domain.enums import Channel, Classification
from app.main import create_app
from app.sensitivity.checker import SensitivityChecker
from tests.helpers import FakeDocumentSource

DEFAULT_URL = "postgresql+psycopg://thinknex:thinknex-local-dev@localhost:5433/share_test"
DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
PASSWORD = "integration-password-1"
ADMIN_EMAIL = "admin@thinknex.example"
ADMIN_PASSWORD = "admin-password-1"
SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


class OkChannel:
    def send(self, message: OutboundMessage) -> DeliveryResult:
        return DeliveryResult(ok=True, provider_message_id="test")


@pytest.fixture(scope="session")
def database() -> str:
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    except OperationalError:
        pytest.skip(f"Postgres no disponible en {DATABASE_URL}")
    finally:
        engine.dispose()
    cfg = Config(os.path.join(SERVICE_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(SERVICE_ROOT, "app/db/migrations"))
    cfg.attributes["database_url"] = DATABASE_URL
    command.upgrade(cfg, "head")
    return DATABASE_URL


@pytest.fixture(scope="session")
def settings(database: str) -> Settings:
    return Settings(
        log_level="WARNING",
        database_url=database,
        jwt_secret=SecretStr("integration-jwt-secret-0123456789abcdef"),
        otp_secret=SecretStr("integration-otp-secret-0123456789abcdef"),
        cookie_secure=False,  # TestClient usa http://testserver
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        demo_users_enabled=True,
        demo_users_password=SecretStr(PASSWORD),
        dms_api_key=SecretStr("unused"),
        public_base_url="http://testserver",
        simulated_inbox_enabled=True,
    )


@pytest.fixture(scope="session")
def source() -> FakeDocumentSource:
    src = FakeDocumentSource()
    src.add("doc-public", Classification.PUBLIC, "Catalogo de productos 2026")
    src.add(
        "doc-pii",
        Classification.INTERNAL,
        "Cliente Maria, RUT 18.456.789-K",
        "fono +56 9 8765 4321",
    )
    src.add("doc-confidential", Classification.CONFIDENTIAL, "Contrato de servicios")
    src.add("doc-restricted", Classification.RESTRICTED, "Plan estrategico del directorio")
    src.add("doc-retention", Classification.PUBLIC, "Documento para probar retencion")
    return src


@pytest.fixture(scope="session")
def components(settings: Settings, source: FakeDocumentSource) -> Components:
    channels = ChannelRegistry({ch: OkChannel() for ch in Channel})
    factory = session_factory(settings.database_url)
    with factory() as db:
        seed_users(db, settings)
    return Components(
        session_factory=factory,
        source=source,
        storage=InMemoryBlobStorage(),
        channels=channels,
        checker=SensitivityChecker(None, llm_max_chars=1000),
    )


@pytest.fixture
def client(settings: Settings, components: Components) -> Iterator[TestClient]:
    with TestClient(create_app(settings, components)) as c:
        yield c


@dataclass
class Api:
    client: TestClient
    components: Components

    def headers(self, email: str) -> dict[str, str]:
        r = self.client.post("/api/v1/auth/token", data={"username": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def share(self, email: str = "ana@thinknex.example", **overrides: object) -> dict[str, object]:
        body: dict[str, object] = {
            "document_id": "doc-public",
            "recipient": {"name": "Pedro Externo", "email": "pedro@cliente.example"},
            "channel": "EMAIL",
            "reason": "Envío de catálogo solicitado",
        }
        body.update(overrides)
        r = self.client.post("/api/v1/shares", json=body, headers=self.headers(email))
        assert r.status_code == 201, r.text
        result: dict[str, object] = r.json()
        return result

    def last_message(self, kind: str) -> dict[str, str]:
        with self.components.session_factory() as db:
            msg = db.scalar(
                select(SimulatedMessage)
                .where(SimulatedMessage.kind == kind)
                .order_by(SimulatedMessage.created_at.desc())
                .limit(1)
            )
            assert msg is not None
            return {
                "channel": msg.channel,
                "kind": msg.kind,
                "body": msg.body,
                "to": msg.to_address,
            }

    def last_link_token(self) -> str:
        match = re.search(r"/s/([A-Za-z0-9_-]+)", self.last_message("LINK")["body"])
        assert match
        return match.group(1)

    def last_otp(self) -> str:
        match = re.search(r"\b(\d{6})\b", self.last_message("OTP")["body"])
        assert match
        return match.group(1)

    def unlock(self, token: str) -> str:
        assert self.client.post(f"/s/{token}/otp").status_code == 200
        r = self.client.post(f"/s/{token}/verify", json={"code": self.last_otp()})
        assert r.status_code == 200, r.text
        access: str = r.json()["access_token"]
        return access

    def audit(self, **params: str) -> list[dict[str, object]]:
        r = self.client.get(
            "/api/v1/audit", params=params, headers=self.headers("carla@thinknex.example")
        )
        assert r.status_code == 200, r.text
        items: list[dict[str, object]] = r.json()["items"]
        return items


@pytest.fixture
def api(client: TestClient, components: Components) -> Api:
    return Api(client, components)
