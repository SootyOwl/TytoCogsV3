"""Exercise test selection and credential handling in isolated pytest runs."""

from pathlib import Path

pytest_plugins = ["pytester"]


def install_policy(pytester):
    policy = Path(__file__).parents[1] / "conftest.py"
    pytester.makeconftest(policy.read_text() if policy.exists() else "")
    pytester.makeini("[pytest]\nmarkers = live: external service check\n")


def test_live_checks_require_opt_in(pytester):
    install_policy(pytester)
    pytester.makepyfile("""
        import pytest
        @pytest.mark.live
        def test_live():
            raise AssertionError("Live service check ran without opt-in")
        def test_unit():
            pass
    """)
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1, skipped=1)


def test_explicit_live_checks_run(pytester):
    install_policy(pytester)
    pytester.makepyfile("""
        import pytest
        @pytest.mark.live
        def test_live():
            pass
    """)
    pytester.runpytest_subprocess("--live", "-m", "live", "-q").assert_outcomes(
        passed=1
    )


def test_credentials_skip_absent_or_empty_values(pytester, monkeypatch):
    install_policy(pytester)
    monkeypatch.delenv("TEST_SERVICE_KEY", raising=False)
    monkeypatch.setenv("TEST_EMPTY_KEY", "  ")
    monkeypatch.setenv("TEST_PRESENT_KEY", "example")
    pytester.makepyfile("""
        def test_missing(require_credentials):
            require_credentials("TEST_SERVICE_KEY")
            raise AssertionError("Missing credential did not skip")
        def test_empty(require_credentials):
            require_credentials("TEST_EMPTY_KEY")
            raise AssertionError("Empty credential did not skip")
        def test_present(require_credentials):
            assert require_credentials("TEST_PRESENT_KEY") == {"TEST_PRESENT_KEY": "example"}
    """)
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1, skipped=2)


def test_unit_checks_cannot_open_network_connections(pytester):
    install_policy(pytester)
    pytester.makepyfile("""
        import socket
        import pytest
        def test_network_blocked():
            with socket.socket() as connection:
                with pytest.raises(RuntimeError, match="Network access is disabled"):
                    connection.connect(("127.0.0.1", 9))
    """)
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1)
