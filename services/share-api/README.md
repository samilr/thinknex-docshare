# share-api — compartición segura y auditable

Servicio principal de la solución. Documentación completa en [`docs/`](../../docs/).

```
app/
├── api/            # HTTP: v1 (interno, JWT + roles), public (/s/{token}), health
├── services/       # casos de uso: share, access, audit (hash chain), retention, notifications
├── sensitivity/    # detectores, política ALLOW/WARN/BLOCK, clasificador LLM opcional
├── adapters/       # DMS (HTTP), storage (S3), canales (SMTP, mocks), marca de agua
├── db/             # modelos SQLAlchemy, migraciones Alembic, seed de usuarios demo
├── core/           # config, seguridad (JWT/OTP/hash), errores RFC 7807, logging JSON
├── container.py    # composition root (los tests inyectan fakes)
└── jobs/gc.py      # retención: python -m app.jobs.gc
```

```bash
uv sync
uv run pytest -q                       # unit; integración requiere TEST_DATABASE_URL (make test)
uv run ruff check . && uv run mypy app
```
