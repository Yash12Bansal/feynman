"""Shared test fixtures."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from feynman.main import app


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
