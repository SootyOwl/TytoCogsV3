"""Keep normal tests independent of live services and private credentials."""

import os
import socket

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Allow tests marked live to contact external services (may incur API charges).",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip = pytest.mark.skip(reason="Live service check: opt in with --live")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)


@pytest.fixture
def require_credentials():
    def require(*names):
        values = {name: os.environ.get(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            pytest.skip("Missing credentials: " + ", ".join(missing))
        return values

    return require


@pytest.fixture(autouse=True)
def block_unit_test_network(request, monkeypatch):
    if request.node.get_closest_marker("live") and request.config.getoption("--live"):
        return

    def blocked(*args, **kwargs):
        raise RuntimeError(
            "Network access is disabled in ordinary tests; mock the request "
            "or mark this test live and opt in with --live."
        )

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)
