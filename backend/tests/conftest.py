import pytest

from app.config import settings
from app.models.db import init_db

ADMIN_HEADERS = {"X-Admin-Token": "test-admin"}


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin")
    init_db()
    yield