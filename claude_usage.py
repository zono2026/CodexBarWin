"""Fetch Claude Code usage/rate-limit info via the internal usage endpoint.

Uses the same GET /api/oauth/usage endpoint that Claude Code itself calls to
power its /usage display. This is an undocumented, private API and may change
without notice.
"""

import json
import os
import urllib.request
import urllib.error

DEFAULT_CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REQUEST_TIMEOUT_SECONDS = 5


class ClaudeUsageError(Exception):
    pass


def load_access_token(credentials_path=DEFAULT_CREDENTIALS_PATH):
    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ClaudeUsageError("credentials file not found")
    except json.JSONDecodeError:
        raise ClaudeUsageError("credentials file is not valid JSON")

    try:
        return data["claudeAiOauth"]["accessToken"]
    except (KeyError, TypeError):
        raise ClaudeUsageError("accessToken not found in credentials file")


def parse_usage(data):
    def window(key):
        entry = data.get(key) or {}
        return {
            "utilization": entry.get("utilization"),
            "resets_at": entry.get("resets_at"),
        }

    return {
        "five_hour": window("five_hour"),
        "seven_day": window("seven_day"),
    }


def _default_http_get(url, headers, timeout):
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def fetch_usage(credentials_path=DEFAULT_CREDENTIALS_PATH, timeout=REQUEST_TIMEOUT_SECONDS, http_get=None):
    http_get = http_get or _default_http_get

    try:
        token = load_access_token(credentials_path=credentials_path)
    except ClaudeUsageError as e:
        return {"error": str(e)}

    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
    }

    try:
        status, body = http_get(USAGE_URL, headers, timeout)
    except urllib.error.HTTPError as e:
        return {"error": f"http error {e.code}"}
    except Exception as e:
        # Never surface the raw exception message: it may embed request
        # details (headers, URL) that could contain the bearer token.
        return {"error": f"request failed ({type(e).__name__})"}

    if status != 200:
        return {"error": f"http error {status}"}

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "invalid response body"}

    return parse_usage(data)
