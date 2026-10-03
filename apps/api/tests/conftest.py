import pytest


@pytest.fixture(autouse=True)
def _no_network_price_refresh(monkeypatch):
    """Endpoints refresh live prices by default; tests must never reach Yahoo/AMFI. Tests that exercise
    refreshing override these with their own fake."""
    async def noop(*args, **kwargs):
        return {}

    for path in ("routers.insights.refresh_for_user", "routers.networth.refresh_for_user"):
        module, attr = path.rsplit(".", 1)
        monkeypatch.setattr(f"{module}.{attr}", noop)
