import pytest

pytest_plugins = []

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
