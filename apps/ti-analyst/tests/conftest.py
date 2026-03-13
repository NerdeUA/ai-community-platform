import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure required config fields are set before app import (X-01: no hardcoded defaults)
os.environ.setdefault("LITELLM_API_KEY", "test-key")
os.environ.setdefault("APP_INTERNAL_TOKEN", "test-internal-token")


@pytest.fixture
def client():
    with (
        patch("app.services.scheduler.start_scheduler"),
        patch("app.services.scheduler.stop_scheduler"),
    ):
        from app.main import app

        with TestClient(app) as c:
            yield c
