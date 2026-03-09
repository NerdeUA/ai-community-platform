from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with (
        patch("app.services.scheduler.start_scheduler"),
        patch("app.services.scheduler.stop_scheduler"),
    ):
        from app.main import app

        with TestClient(app) as c:
            yield c
