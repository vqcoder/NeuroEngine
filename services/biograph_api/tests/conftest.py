"""Integration test fixtures."""

from __future__ import annotations

import os

# Set required env vars before any app imports — importing app.main triggers
# get_settings() at module level, which now raises ValueError on missing config.
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("API_TOKEN_REQUIRED", "false")
os.environ.setdefault("WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE", "none")

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "integration.sqlite"
    database_url = os.getenv("TEST_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

    engine = create_engine(database_url, connect_args=connect_args, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
