import json
import logging
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("FRIDAY")

DEFAULT_DEVICE_ID = "friday-esp32"
ALLOWED_REPEAT_RULES = {"once", "daily", "weekdays", "weekends"}


def _supabase_request(method: str, path: str, *, params=None, payload=None, prefer=None):
    """Call Supabase REST using the server-only secret key."""
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
    if not base_url or not secret_key:
        raise RuntimeError(
            "FRIDAY database is not configured. Check SUPABASE_URL and "
            "SUPABASE_SECRET_KEY in the cloud service environment."
        )

    url = f"{base_url}/rest/v1/{path}"
    if params:
        url += "?" + urlencode(params)

    headers = {"apikey": secret_key, "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if prefer:
        headers["Prefer"] = prefer

    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Database request failed (HTTP {exc.code}): {detail}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach the FRIDAY database: {exc}") from None


@mcp.tool()
def get_current_time() -> dict:
    """Get the current date and time in India."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return {
        "timezone": "Asia/Kolkata",
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%I:%M:%S %p")
    }


@mcp.tool()
def friday_status() -> dict:
    """Check whether the FRIDAY MCP service is running."""
    return {"assistant": "FRIDAY", "status": "online"}


@mcp.tool()
def set_alarm(
    scheduled_at: str,
    label: str = "FRIDAY alarm",
    repeat_rule: str = "once",
    sound_uri: str = "",
    device_id: str = DEFAULT_DEVICE_ID,
) -> dict:
    """Save an alarm. scheduled_at must be ISO 8601 with a timezone, e.g. 2026-11-25T07:00:00+05:30. Repeat rule: once, daily, weekdays, or weekends."""
    label = label.strip()
    device_id = device_id.strip()
    if not label or len(label) > 80:
        return {"success": False, "error": "Alarm label must be 1 to 80 characters."}
    if not device_id or len(device_id) > 80:
        return {"success": False, "error": "Device ID must be 1 to 80 characters."}
    if repeat_rule not in ALLOWED_REPEAT_RULES:
        return {"success": False, "error": "repeat_rule must be once, daily, weekdays, or weekends."}

    try:
        when = datetime.fromisoformat(scheduled_at.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return {"success": False, "error": "Use ISO 8601 date and time including a timezone offset, e.g. +05:30."}

    if when.tzinfo is None or when.utcoffset() is None:
        return {"success": False, "error": "The alarm time must include a timezone offset, e.g. +05:30 for India."}
    if when <= datetime.now(timezone.utc):
        return {"success": False, "error": "Please choose a future date and time."}

    payload = {
        "device_id": device_id,
        "label": label,
        "scheduled_at": when.isoformat(),
        "timezone": "Asia/Kolkata",
        "repeat_rule": repeat_rule,
        "sound_uri": sound_uri.strip() or None,
        "status": "active",
    }
    rows = _supabase_request(
        "POST", "friday_alarms", payload=payload, prefer="return=representation"
    )
    if not rows:
        return {"success": False, "error": "The database did not return the saved alarm."}
    return {"success": True, "message": "Alarm saved in FRIDAY cloud.", "alarm": rows[0]}


@mcp.tool()
def list_alarms(device_id: str = DEFAULT_DEVICE_ID) -> dict:
    """List upcoming active alarms saved for the FRIDAY device."""
    device_id = device_id.strip()
    if not device_id or len(device_id) > 80:
        return {"success": False, "error": "Invalid device ID."}

    rows = _supabase_request(
        "GET",
        "friday_alarms",
        params={
            "select": "id,label,scheduled_at,timezone,repeat_rule,sound_uri,status",
            "device_id": f"eq.{device_id}",
            "status": "eq.active",
            "order": "scheduled_at.asc",
            "limit": "25",
        },
    )
    return {"success": True, "count": len(rows), "alarms": rows}


@mcp.tool()
def cancel_alarm(alarm_id: str, device_id: str = DEFAULT_DEVICE_ID) -> dict:
    """Cancel an active alarm using its alarm ID."""
    alarm_id = alarm_id.strip()
    device_id = device_id.strip()
    if not alarm_id or len(alarm_id) > 80:
        return {"success": False, "error": "Provide a valid alarm ID."}
    if not device_id or len(device_id) > 80:
        return {"success": False, "error": "Invalid device ID."}

    rows = _supabase_request(
        "PATCH",
        "friday_alarms",
        params={
            "id": f"eq.{alarm_id}",
            "device_id": f"eq.{device_id}",
            "status": "eq.active",
        },
        payload={"status": "cancelled"},
        prefer="return=representation",
    )
    if not rows:
        return {"success": False, "message": "No matching active alarm was found. It may already be cancelled."}
    return {"success": True, "message": "Alarm cancelled.", "alarm": rows[0]}

def _supabase_storage_request(method: str, path: str, *, payload=None):
    """Call Supabase Storage using the server-only secret key."""
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")

    if not base_url or not secret_key:
        raise RuntimeError("Supabase Storage is not configured.")

    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }

    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    request = Request(
        f"{base_url}/storage/v1/{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(
            f"Music storage request failed (HTTP {exc.code}): {detail}"
        ) from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach music storage: {exc}") from None


@mcp.tool()
def list_music(prefix: str = "") -> dict:
    """List MP3 songs in FRIDAY's private music library."""
    prefix = prefix.strip().lstrip("/")

    if len(prefix) > 300 or ".." in prefix.split("/"):
        return {"success": False, "error": "Invalid folder prefix."}

    result = _supabase_storage_request(
        "POST",
        "object/list/friday-music",
        payload={
            "prefix": prefix,
            "limit": 100,
            "offset": 0,
            "sortBy": {"column": "name", "order": "asc"},
        },
    )

    songs = []
    for item in result if isinstance(result, list) else []:
        name = item.get("name", "")
        if name.lower().endswith(".mp3"):
            songs.append({
                "name": name,
                "metadata": item.get("metadata") or {},
            })

    return {
        "success": True,
        "count": len(songs),
        "songs": songs,
    }


@mcp.tool()
def play_music(song_name: str, expires_in: int = 3600) -> dict:
    """Create a temporary secure streaming URL for a library MP3."""
    from urllib.parse import quote

    song_name = song_name.strip().lstrip("/")

    if (
        not song_name
        or len(song_name) > 500
        or ".." in song_name.split("/")
        or not song_name.lower().endswith(".mp3")
    ):
        return {
            "success": False,
            "error": "Provide the exact MP3 filename from list_music.",
        }

    if not 60 <= expires_in <= 3600:
        return {
            "success": False,
            "error": "URL expiry must be between 60 and 3600 seconds.",
        }

    object_path = "/".join(
        quote(part, safe="") for part in song_name.split("/")
    )

    result = _supabase_storage_request(
        "POST",
        f"object/sign/friday-music/{object_path}",
        payload={"expiresIn": expires_in},
    )

    signed_url = result.get("signedURL") or result.get("signedUrl")

    if not signed_url:
        return {
            "success": False,
            "error": "Storage did not return a signed music URL.",
        }

    if signed_url.startswith("/"):
        signed_url = (
            os.environ["SUPABASE_URL"].rstrip("/") + signed_url
        )

    return {
        "success": True,
        "song": song_name.rsplit("/", 1)[-1],
        "stream_url": signed_url,
        "expires_in": expires_in,
        "message": "Temporary music stream URL created.",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
