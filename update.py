"""Run Courtside's protected updater and verify its durable public status."""

import datetime
import json
import os
import re
import signal
import sys
import urllib.error
import urllib.request

ORIGIN = "https://courtside-nba-terminal.mapledill2.chatgpt.site"
MAX_BYTES = 16384
REQUEST_SECONDS = 55
TOTAL_SECONDS = 120
STATUSES = {"idle", "running", "success", "partial", "failed", "unavailable"}
TIME_FIELDS = ("lastStartedAt", "lastCompletedAt", "lastSuccessfulAt", "lastCachedBoardAt")


class SchedulerFailure(Exception):
    """A controlled error code, never an upstream body or exception message."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise SchedulerFailure("redirect-rejected")


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z", value
    ):
        raise SchedulerFailure("invalid-status")
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SchedulerFailure("invalid-status") from None


def public_status(value):
    if not isinstance(value, dict) or value.get("enabled") is not True or value.get("status") not in STATUSES:
        raise SchedulerFailure("invalid-status")
    result = {"status": value["status"]}
    for field in TIME_FIELDS:
        timestamp(value.get(field))
        result[field] = value.get(field)
    date = value.get("lastCachedBoardDate")
    if date is not None:
        try:
            if not isinstance(date, str) or datetime.date.fromisoformat(date).isoformat() != date:
                raise ValueError()
        except ValueError:
            raise SchedulerFailure("invalid-status") from None
    result["lastCachedBoardDate"] = date
    return result


def read_json(opener, path, method, key=None, service_token=None):
    if (method, path) not in {("POST", "/api/background/update"), ("GET", "/api/background/status")} or service_token is None:
        raise SchedulerFailure("invalid-updater-request")
    if (method == "POST" and key is None) or (method == "GET" and key is not None):
        raise SchedulerFailure("invalid-updater-request")
    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    headers["OAI-Sites-Authorization"] = "Bearer " + service_token
    if key is not None:
        headers["X-Courtside-Updater-Key"] = key
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(ORIGIN + path, data=b"{}" if method == "POST" else None, headers=headers, method=method)
    stage = "update" if method == "POST" else "status"
    try:
        with opener.open(request, timeout=REQUEST_SECONDS) as response:
            if response.geturl() != request.full_url:
                raise SchedulerFailure("redirect-rejected")
            if response.status != 200:
                raise SchedulerFailure(stage + "-http-" + str(int(response.status)))
            length = response.headers.get("Content-Length")
            if length and (not length.isdigit() or int(length) > MAX_BYTES):
                raise SchedulerFailure("response-too-large")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise SchedulerFailure("response-too-large")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise SchedulerFailure("invalid-response")
        return value
    except SchedulerFailure:
        raise
    except urllib.error.HTTPError as error:
        raise SchedulerFailure("redirect-rejected" if 300 <= error.code < 400 else stage + "-http-" + str(error.code)) from None
    except (ValueError, UnicodeError):
        raise SchedulerFailure("invalid-response") from None
    except Exception:
        raise SchedulerFailure(stage + "-unavailable") from None


def run_update(environment=None, opener=None):
    environment = os.environ if environment is None else environment
    key = environment.get("COURTSIDE_UPDATER_KEY", "")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", key):
        raise SchedulerFailure("missing-or-invalid-secret")
    service_token = environment.get("COURTSIDE_SITE_SERVICE_TOKEN", "")
    if not isinstance(service_token, str) or not 24 <= len(service_token) <= 2048 or any(
        ord(character) < 33 or ord(character) > 126 for character in service_token
    ):
        raise SchedulerFailure("missing-or-invalid-service-token")
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    updated = read_json(opener, "/api/background/update", "POST", key, service_token)
    if type(updated.get("ran")) is not bool:
        raise SchedulerFailure("invalid-response")
    previous = public_status(updated)
    saved = public_status(read_json(opener, "/api/background/status", "GET", service_token=service_token))
    for field in ("lastStartedAt", "lastCompletedAt", "lastSuccessfulAt"):
        before, after = timestamp(previous[field]), timestamp(saved[field])
        if before is not None and (after is None or after < before):
            raise SchedulerFailure("status-not-persisted")
    if updated["ran"] and (previous["lastStartedAt"] is None or previous["lastCompletedAt"] is None):
        raise SchedulerFailure("status-not-persisted")
    if saved["status"] in {"partial", "failed", "unavailable", "idle"}:
        raise SchedulerFailure("background-" + saved["status"])
    result = {"ok": True, "ran": updated["ran"], "persisted": True, **saved}
    if updated.get("reason") in {"running", "not-due"}:
        result["reason"] = updated["reason"]
    return result


def timeout_handler(signum, frame):
    raise SchedulerFailure("deadline-exceeded")


def main():
    # GitHub's standard Ubuntu runner supports SIGALRM: it bounds both HTTP
    # requests and all body reads together, including a slow upstream response.
    alarm = hasattr(signal, "SIGALRM")
    if alarm:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TOTAL_SECONDS)
    try:
        result = run_update()
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except SchedulerFailure as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        return 1
    except Exception:
        print('{"ok":false,"error":"scheduler-unavailable"}')
        return 1
    finally:
        if alarm:
            signal.alarm(0)


if __name__ == "__main__":
    sys.exit(main())
