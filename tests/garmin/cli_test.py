"""Unit tests for garmin.cli.WorkoutClient. pytest only.

A DummyClient stands in for the garth client (injected via workout._client), so
no network calls happen.
"""

import json
import logging
import sys
from types import SimpleNamespace

import pytest

from src.garmin import cli


class DummyClient:
    """Records connectapi calls and returns a canned response."""

    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def connectapi(self, path, method="GET", **kwargs):
        self.calls.append({"path": path, "method": method, **kwargs})
        return self.response


@pytest.fixture
def workout():
    p = cli.WorkoutClient()
    p._client = DummyClient(response={"ok": True})
    return p


class TestStrip:
    def test_removes_server_fields(self):
        data = {"workoutId": 1, "ownerId": 2, "workoutName": "x", "keep": 3}
        assert cli.WorkoutClient._strip(data) == {"workoutName": "x", "keep": 3}

    def test_keeps_child_step_id_but_drops_step_id(self):
        assert cli.WorkoutClient._strip({"childStepId": 5, "stepId": 9}) == {"childStepId": 5}

    def test_recurses_through_lists_and_nested_dicts(self):
        data = {"segments": [{"stepId": 1, "reps": 5, "sub": {"ownerId": 2, "x": 1}}]}
        assert cli.WorkoutClient._strip(data) == {"segments": [{"reps": 5, "sub": {"x": 1}}]}


class TestGet:
    def test_hits_workout_path(self, workout):
        workout.get(SimpleNamespace(workout_id="123"))
        assert workout._client.calls[0]["path"] == "/workout-service/workout/123"

    def test_dumps_full_body(self, workout, caplog):
        caplog.set_level(logging.INFO)
        workout._client.response = {"workoutId": 7, "workoutName": "x"}
        workout.get(SimpleNamespace(workout_id="7"))
        assert json.loads(caplog.messages[-1]) == {"workoutId": 7, "workoutName": "x"}


class TestList:
    def test_hits_workouts_path_with_params(self, workout):
        workout._client.response = []
        workout.list(SimpleNamespace(limit=50))
        call = workout._client.calls[0]
        assert call["path"] == "/workout-service/workouts"
        assert call["params"] == {"start": 0, "limit": 50, "myWorkoutsOnly": "true"}

    def test_logs_id_and_name_per_workout(self, workout, caplog):
        caplog.set_level(logging.INFO)
        workout._client.response = [
            {"workoutId": 1, "workoutName": "Week 1 Day A"},
            {"workoutId": 2, "workoutName": "Week 1 Day B"},
        ]
        workout.list(SimpleNamespace(limit=100))
        assert "1\tWeek 1 Day A" in caplog.text
        assert "2\tWeek 1 Day B" in caplog.text


class TestCreate:
    def test_dry_run_previews_without_sending(self, workout, monkeypatch, caplog):
        caplog.set_level(logging.INFO)
        monkeypatch.setattr(workout, "_load", lambda f: {"workoutName": "x", "workoutId": 99})
        workout.create(SimpleNamespace(file="w.json", live=False))
        assert "[dry run] POST /workout-service/workout" in caplog.text
        assert workout._client.calls == []  # nothing sent
        assert "workoutId" not in caplog.text  # server field stripped from preview

    def test_live_sends_stripped_payload(self, workout, monkeypatch):
        monkeypatch.setattr(workout, "_load", lambda f: {"workoutName": "x", "workoutId": 99})
        workout.create(SimpleNamespace(file="w.json", live=True))
        call = workout._client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/workout-service/workout"
        assert call["json"] == {"workoutName": "x"}  # workoutId stripped


class TestUpdate:
    def test_live_targets_workout_id(self, workout, monkeypatch):
        monkeypatch.setattr(workout, "_load", lambda f: {"a": 1})
        workout.update(SimpleNamespace(workout_id="555", file="w.json", live=True))
        call = workout._client.calls[0]
        assert call["method"] == "PUT"
        assert call["path"] == "/workout-service/workout/555"


class TestDelete:
    def test_dry_run_does_not_send(self, workout, caplog):
        caplog.set_level(logging.INFO)
        workout.delete(SimpleNamespace(workout_id="7", live=False))
        assert workout._client.calls == []
        assert "[dry run] DELETE /workout-service/workout/7" in caplog.text

    def test_live_sends_delete_without_body(self, workout):
        workout.delete(SimpleNamespace(workout_id="7", live=True))
        call = workout._client.calls[0]
        assert call["method"] == "DELETE"
        assert "json" not in call


class TestSchedule:
    def test_live_posts_date(self, workout):
        workout.schedule(SimpleNamespace(workout_id="7", date="2026-07-21", live=True))
        call = workout._client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/workout-service/schedule/7"
        assert call["json"] == {"date": "2026-07-21"}


class TestTypes:
    def test_writes_catalog_to_ref(self, workout, tmp_path, monkeypatch):
        workout._client.response = {"stepTypes": []}
        monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)
        (tmp_path / "ref").mkdir()

        workout.types(SimpleNamespace())

        written = json.loads((tmp_path / "ref" / "workout-types.json").read_text())
        assert written == {"stepTypes": []}


class TestClientWiring:
    def test_client_is_lazy_and_cached(self, monkeypatch):
        calls = []
        sentinel = object()

        def fake_ensure():
            calls.append(True)
            return sentinel

        p = cli.WorkoutClient()
        monkeypatch.setattr(p._garmin, "ensure", fake_ensure)
        assert calls == []  # not created at construction
        assert p.client is sentinel
        assert p.client is sentinel  # second access
        assert calls == [True]  # created exactly once

    def test_auth_command_does_not_authenticate(self, monkeypatch):
        ensure_calls = []
        login_calls = []
        p = cli.WorkoutClient()
        monkeypatch.setattr(p._garmin, "ensure", lambda: ensure_calls.append(True))
        monkeypatch.setattr(p._garmin, "login", lambda: login_calls.append(True))

        p.auth(SimpleNamespace())

        assert login_calls == [True]
        assert ensure_calls == []  # auth never builds the client


class TestReport:
    def test_confirms_with_workout_id(self, caplog):
        caplog.set_level(logging.INFO)
        cli.WorkoutClient._report("create", True, {"workoutId": 42})
        assert "create ok -- workoutId 42" in caplog.text

    def test_confirms_without_id_when_response_has_none(self, caplog):
        caplog.set_level(logging.INFO)
        cli.WorkoutClient._report("schedule", True, None)
        assert "schedule ok" in caplog.text
        assert "workoutId" not in caplog.text

    def test_silent_on_dry_run(self, caplog):
        caplog.set_level(logging.INFO)
        cli.WorkoutClient._report("create", False, None)
        assert caplog.records == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-p", "no:cacheprovider", "-v"]))
