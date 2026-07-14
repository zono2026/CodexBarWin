import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import codex_usage


SAMPLE_RATE_LIMITS_RESULT = {
    "rateLimits": {
        "primary": {"usedPercent": 12, "windowDurationMins": 300, "resetsAt": 1784020800},
        "secondary": {"usedPercent": 24, "windowDurationMins": 10080, "resetsAt": 1784440800},
    }
}


class FakeStdin:
    def __init__(self):
        self.lines = []

    def write(self, data):
        self.lines.append(data)

    def flush(self):
        pass


class FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if not self._lines:
            return ""
        return self._lines.pop(0)


class FakeProcess:
    def __init__(self, response_lines, exit_immediately=False):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(response_lines)
        self.terminated = False
        self.killed = False
        self._exit_immediately = exit_immediately

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0 if self._exit_immediately else None


def make_fake_spawn(response_lines, exit_immediately=False):
    process = FakeProcess(response_lines, exit_immediately=exit_immediately)

    def fake_spawn():
        return process

    return fake_spawn, process


def canned_responses():
    initialize_response = json.dumps({"id": 0, "result": {"userAgent": "codex/test"}}) + "\n"
    rate_limits_response = json.dumps({"id": 1, "result": SAMPLE_RATE_LIMITS_RESULT}) + "\n"
    return [initialize_response, rate_limits_response]


def test_parse_rate_limits_extracts_primary_and_secondary():
    result = codex_usage.parse_rate_limits(SAMPLE_RATE_LIMITS_RESULT)
    assert result["primary"]["used_percent"] == 12
    assert result["primary"]["window_duration_mins"] == 300
    assert result["primary"]["resets_at"] == 1784020800
    assert result["secondary"]["used_percent"] == 24


def test_parse_rate_limits_handles_missing_secondary():
    data = {"rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 300, "resetsAt": 1}}}
    result = codex_usage.parse_rate_limits(data)
    assert result["primary"]["used_percent"] == 5
    assert result["secondary"]["used_percent"] is None


def test_fetch_usage_success_sends_expected_handshake():
    fake_spawn, process = make_fake_spawn(canned_responses())

    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5)

    assert "error" not in result
    assert result["primary"]["used_percent"] == 12
    assert result["secondary"]["used_percent"] == 24

    sent = [json.loads(line) for line in process.stdin.lines]
    assert sent[0]["method"] == "initialize"
    assert sent[0]["params"]["clientInfo"]["name"] == "codexbar_win"
    assert sent[1]["method"] == "initialized"
    assert sent[2]["method"] == "account/rateLimits/read"

    assert process.terminated or process.killed


def test_fetch_usage_spawn_failure_returns_error():
    def failing_spawn():
        raise OSError("codex executable not found")

    result = codex_usage.fetch_usage(spawn=failing_spawn, timeout=5)
    assert "error" in result


def test_fetch_usage_malformed_response_returns_error():
    fake_spawn, process = make_fake_spawn(["not json\n", ""])
    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5)
    assert "error" in result


def test_fetch_usage_empty_stream_returns_error():
    fake_spawn, process = make_fake_spawn([])
    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5)
    assert "error" in result


def test_fetch_usage_initialize_error_returns_error_without_further_requests():
    initialize_error_response = json.dumps({"id": 0, "error": {"message": "unsupported clientInfo"}}) + "\n"
    fake_spawn, process = make_fake_spawn([initialize_error_response])

    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5)

    assert "error" in result
    assert "unsupported clientInfo" in result["error"]
    sent = [json.loads(line) for line in process.stdin.lines]
    assert len(sent) == 1  # only the initialize request; never sent initialized/rateLimits
    assert sent[0]["method"] == "initialize"


def test_fetch_usage_skips_non_dict_json_lines_without_crashing():
    lines = [
        "5\n",  # bare scalar, not an object
        "[1, 2]\n",  # bare array, not an object
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": SAMPLE_RATE_LIMITS_RESULT}) + "\n",
    ]
    fake_spawn, process = make_fake_spawn(lines)

    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5)

    assert "error" not in result
    assert result["primary"]["used_percent"] == 12


def test_fetch_usage_overall_timeout_is_not_reset_by_each_notification():
    notification = json.dumps({"method": "some/notification"}) + "\n"
    lines = [notification] * 5 + [json.dumps({"id": 0, "result": {}}) + "\n"]
    fake_spawn, process = make_fake_spawn(lines)

    clock = {"t": 0.0}

    def fake_time_source():
        clock["t"] += 2
        return clock["t"]

    result = codex_usage.fetch_usage(spawn=fake_spawn, timeout=5, time_source=fake_time_source)

    assert "error" in result
    assert "timed out" in result["error"]


def test_fetch_usage_default_spawn_missing_codex_returns_clear_error(monkeypatch):
    monkeypatch.setattr(codex_usage.shutil, "which", lambda name: None)

    result = codex_usage.fetch_usage()

    assert "error" in result
    assert "not found" in result["error"]
