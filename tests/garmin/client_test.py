"""Unit tests for garmin.client.GarminClient. pytest only.

garth's network calls and the interactive prompts are all monkeypatched -- no
real login happens.
"""

import sys

import garth
import pytest

from garmin.client import GarminClient


class DummyClient:
    """Stands in for a garth client; records connectapi calls."""

    def __init__(self, raises=False):
        self.raises = raises
        self.calls = []

    def connectapi(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if self.raises:
            raise RuntimeError("boom")
        return {"ok": True}


@pytest.fixture
def session_dir(tmp_path):
    return tmp_path / "garth_session"


@pytest.fixture
def gc(session_dir):
    return GarminClient(session_dir=session_dir)


def _stub_login(gc, monkeypatch):
    """Replace login with a recorder; return its call list."""
    calls = []
    monkeypatch.setattr(gc, "login", lambda: calls.append(True))
    return calls


class TestLogin:
    def test_authenticates_and_saves(self, gc, session_dir, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "  me@example.com  ")
        monkeypatch.setattr("getpass.getpass", lambda _: "pw")
        logged = {}
        monkeypatch.setattr(garth, "login", lambda e, p: logged.update(email=e, password=p))
        saved = {}
        monkeypatch.setattr(garth, "save", lambda d: saved.update(dir=d))

        gc.login()

        assert logged == {"email": "me@example.com", "password": "pw"}  # input stripped
        assert saved["dir"] == session_dir
        assert session_dir.exists()  # mkdir(parents=True) ran


class TestEnsure:
    def test_resumes_valid_session(self, gc, session_dir, monkeypatch):
        session_dir.mkdir(parents=True)
        (session_dir / "oauth2_token.json").write_text("{}")
        sentinel = DummyClient()  # probe succeeds
        monkeypatch.setattr(garth, "client", sentinel)
        resumed = {}
        monkeypatch.setattr(garth, "resume", lambda d: resumed.update(dir=d))
        login_calls = _stub_login(gc, monkeypatch)

        result = gc.ensure()

        assert result is sentinel
        assert resumed["dir"] == session_dir
        assert sentinel.calls[0][0] == "/userprofile-service/userprofile/user-settings"  # probed
        assert login_calls == []  # did not re-login

    def test_logs_in_when_no_token(self, gc, monkeypatch):
        sentinel = DummyClient()
        monkeypatch.setattr(garth, "client", sentinel)
        login_calls = _stub_login(gc, monkeypatch)

        result = gc.ensure()

        assert result is sentinel
        assert login_calls == [True]

    def test_logs_in_when_probe_fails(self, gc, session_dir, monkeypatch):
        session_dir.mkdir(parents=True)
        (session_dir / "oauth2_token.json").write_text("{}")
        monkeypatch.setattr(garth, "client", DummyClient(raises=True))  # probe raises
        monkeypatch.setattr(garth, "resume", lambda d: None)
        login_calls = _stub_login(gc, monkeypatch)

        gc.ensure()

        assert login_calls == [True]

    def test_logs_in_when_resume_raises(self, gc, session_dir, monkeypatch):
        session_dir.mkdir(parents=True)
        (session_dir / "oauth2_token.json").write_text("{}")
        monkeypatch.setattr(garth, "client", DummyClient())

        def boom(_):
            raise RuntimeError("resume failed")

        monkeypatch.setattr(garth, "resume", boom)
        login_calls = _stub_login(gc, monkeypatch)

        gc.ensure()

        assert login_calls == [True]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-p", "no:cacheprovider", "-v"]))
