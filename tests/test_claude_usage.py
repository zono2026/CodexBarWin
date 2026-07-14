import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import claude_usage


SAMPLE_RESPONSE = {
    "five_hour": {"utilization": 12.0, "resets_at": "2026-07-14T09:19:59.969453+00:00"},
    "seven_day": {"utilization": 24.0, "resets_at": "2026-07-19T05:59:59.969484+00:00"},
}


def test_parse_usage_extracts_five_hour_and_seven_day():
    result = claude_usage.parse_usage(SAMPLE_RESPONSE)
    assert result["five_hour"]["utilization"] == 12.0
    assert result["five_hour"]["resets_at"] == "2026-07-14T09:19:59.969453+00:00"
    assert result["seven_day"]["utilization"] == 24.0
    assert result["seven_day"]["resets_at"] == "2026-07-19T05:59:59.969484+00:00"


def test_parse_usage_handles_missing_keys_gracefully():
    result = claude_usage.parse_usage({})
    assert result["five_hour"]["utilization"] is None
    assert result["seven_day"]["utilization"] is None


def test_load_access_token_reads_from_credentials_file(tmp_path):
    creds_file = tmp_path / ".credentials.json"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-test-token"}}))
    token = claude_usage.load_access_token(credentials_path=str(creds_file))
    assert token == "sk-ant-oat-test-token"


def test_load_access_token_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(claude_usage.ClaudeUsageError):
        claude_usage.load_access_token(credentials_path=str(missing))


def test_load_access_token_missing_key_raises(tmp_path):
    creds_file = tmp_path / ".credentials.json"
    creds_file.write_text(json.dumps({"somethingElse": {}}))
    with pytest.raises(claude_usage.ClaudeUsageError):
        claude_usage.load_access_token(credentials_path=str(creds_file))


def test_fetch_usage_success(tmp_path):
    creds_file = tmp_path / ".credentials.json"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-test-token"}}))

    def fake_http_get(url, headers, timeout):
        assert url == claude_usage.USAGE_URL
        assert headers["authorization"] == "Bearer sk-ant-oat-test-token"
        return 200, json.dumps(SAMPLE_RESPONSE).encode("utf-8")

    result = claude_usage.fetch_usage(credentials_path=str(creds_file), http_get=fake_http_get)
    assert "error" not in result
    assert result["five_hour"]["utilization"] == 12.0
    assert result["seven_day"]["utilization"] == 24.0


def test_fetch_usage_missing_credentials_returns_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    result = claude_usage.fetch_usage(credentials_path=str(missing), http_get=lambda *a, **k: (200, b"{}"))
    assert "error" in result


def test_fetch_usage_http_401_via_injected_http_get_returns_error_without_leaking_token(tmp_path):
    # Exercises the http_get injection contract directly (a caller may choose to
    # return a non-200 tuple instead of raising). The REAL default HTTP transport
    # never takes this branch — see test_fetch_usage_real_http_401_returns_error
    # below for that path.
    creds_file = tmp_path / ".credentials.json"
    secret_token = "sk-ant-oat-super-secret-token"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": secret_token}}))

    def fake_http_get(url, headers, timeout):
        return 401, b'{"error": "unauthorized"}'

    result = claude_usage.fetch_usage(credentials_path=str(creds_file), http_get=fake_http_get)
    assert "error" in result
    assert secret_token not in json.dumps(result)


def test_fetch_usage_real_http_401_returns_error(tmp_path, monkeypatch):
    # Uses the REAL _default_http_get (urllib-based) transport, not an injected
    # fake, to prove the actual network error path is covered: urlopen raises
    # HTTPError for non-2xx responses rather than returning a status tuple.
    creds_file = tmp_path / ".credentials.json"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-test-token"}}))

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(claude_usage.urllib.request, "urlopen", fake_urlopen)

    result = claude_usage.fetch_usage(credentials_path=str(creds_file))
    assert result == {"error": "http error 401"}


def test_fetch_usage_network_exception_returns_error_without_leaking_token(tmp_path):
    creds_file = tmp_path / ".credentials.json"
    secret_token = "sk-ant-oat-super-secret-token"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": secret_token}}))

    def fake_http_get(url, headers, timeout):
        raise OSError(f"connection refused for token {secret_token}")

    result = claude_usage.fetch_usage(credentials_path=str(creds_file), http_get=fake_http_get)
    assert "error" in result
    assert secret_token not in json.dumps(result)


def test_fetch_usage_malformed_json_returns_error(tmp_path):
    creds_file = tmp_path / ".credentials.json"
    creds_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-test-token"}}))

    def fake_http_get(url, headers, timeout):
        return 200, b"not json"

    result = claude_usage.fetch_usage(credentials_path=str(creds_file), http_get=fake_http_get)
    assert "error" in result
