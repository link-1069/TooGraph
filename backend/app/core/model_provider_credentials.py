from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


PROVIDER_CREDENTIAL_STATUS_ACTIVE = "active"
PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN = "cooling_down"
PROVIDER_CREDENTIAL_STATUS_DISABLED = "disabled"
PROVIDER_CREDENTIAL_STATUS_EXHAUSTED = "exhausted"
PROVIDER_CREDENTIAL_BASE_COOLDOWN_SECONDS = 60
PROVIDER_CREDENTIAL_MAX_COOLDOWN_SECONDS = 3600
PROVIDER_CREDENTIAL_EXHAUSTED_FAILURE_COUNT = 5
PROVIDER_CREDENTIAL_STATUSES = {
    PROVIDER_CREDENTIAL_STATUS_ACTIVE,
    PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN,
    PROVIDER_CREDENTIAL_STATUS_DISABLED,
    PROVIDER_CREDENTIAL_STATUS_EXHAUSTED,
}


def build_api_key_preview(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"
    if len(text) <= 12:
        return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"
    return f"{text[:8]}{'*' * (len(text) - 12)}{text[-4:]}"


def normalize_provider_credential_pool(value: Any, *, include_secrets: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    credentials: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        credential_id = str(item.get("credential_id") or item.get("id") or "").strip()
        if not credential_id:
            continue
        identity = credential_id.lower()
        if identity in seen:
            continue
        seen.add(identity)
        status = _normalize_credential_status(item.get("status"))
        credential = {
            "credential_id": credential_id,
            "status": status,
            "cooldown_until": _normalize_optional_text(item.get("cooldown_until")),
            "failure_count": _normalize_failure_count(item.get("failure_count")),
        }
        last_used_at = _normalize_optional_text(item.get("last_used_at"))
        if last_used_at:
            credential["last_used_at"] = last_used_at
        api_key = _normalize_optional_text(item.get("api_key"))
        if include_secrets and api_key:
            credential["api_key"] = api_key
        credentials.append(credential)
    return credentials


def preserve_provider_credential_pool_secrets(
    credentials: list[dict[str, Any]],
    existing_value: Any,
) -> list[dict[str, Any]]:
    existing_credentials = normalize_provider_credential_pool(existing_value, include_secrets=True)
    existing_keys = {
        str(credential.get("credential_id") or "").strip().lower(): str(credential.get("api_key") or "").strip()
        for credential in existing_credentials
        if str(credential.get("credential_id") or "").strip() and str(credential.get("api_key") or "").strip()
    }
    merged: list[dict[str, Any]] = []
    for credential in credentials:
        next_credential = dict(credential)
        credential_id = str(next_credential.get("credential_id") or "").strip().lower()
        if credential_id and not str(next_credential.get("api_key") or "").strip() and existing_keys.get(credential_id):
            next_credential["api_key"] = existing_keys[credential_id]
        merged.append(next_credential)
    return merged


def select_provider_credential(
    provider_config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    candidates: list[tuple[datetime, int, str, dict[str, Any], str]] = []
    for credential in normalize_provider_credential_pool(provider_config.get("credential_pool"), include_secrets=True):
        api_key = str(credential.get("api_key") or "").strip()
        if not api_key:
            continue
        status = str(credential.get("status") or PROVIDER_CREDENTIAL_STATUS_ACTIVE).strip()
        if status in {PROVIDER_CREDENTIAL_STATUS_DISABLED, PROVIDER_CREDENTIAL_STATUS_EXHAUSTED}:
            continue
        is_cooling_down = _credential_is_cooling_down(credential, now=now)
        if status == PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN and is_cooling_down:
            continue
        if status == PROVIDER_CREDENTIAL_STATUS_ACTIVE and is_cooling_down:
            continue
        if status not in {PROVIDER_CREDENTIAL_STATUS_ACTIVE, PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN}:
            continue
        last_used_at = _parse_datetime(credential.get("last_used_at")) or datetime.min.replace(tzinfo=timezone.utc)
        candidates.append((last_used_at, len(candidates), api_key, credential, status))
    if candidates:
        _last_used_at, _index, api_key, credential, status = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        selected = _provider_credential_selection_meta(credential, previous_status=status)
        return api_key, selected
    return str(provider_config.get("api_key") or "").strip(), {}


def has_configured_provider_credential(provider_config: dict[str, Any]) -> bool:
    api_key, _credential = select_provider_credential(provider_config)
    return bool(api_key)


def update_provider_credential_pool_after_call(
    settings: Any,
    *,
    provider_id: str,
    credential_id: str,
    success: bool,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_settings = deepcopy(settings) if isinstance(settings, dict) else {}
    normalized_provider_id = str(provider_id or "").strip()
    normalized_credential_id = str(credential_id or "").strip()
    if not normalized_provider_id or not normalized_credential_id:
        return updated_settings, {}

    providers = updated_settings.get("model_providers")
    if not isinstance(providers, dict):
        return updated_settings, {}
    provider_config = providers.get(normalized_provider_id)
    if not isinstance(provider_config, dict):
        return updated_settings, {}

    credential_pool = normalize_provider_credential_pool(provider_config.get("credential_pool"), include_secrets=True)
    credential_identity = normalized_credential_id.lower()
    current_time = _normalize_datetime(now or datetime.now(timezone.utc))
    for credential in credential_pool:
        if str(credential.get("credential_id") or "").strip().lower() != credential_identity:
            continue
        previous_status = str(credential.get("status") or PROVIDER_CREDENTIAL_STATUS_ACTIVE).strip()
        previous_failure_count = _normalize_failure_count(credential.get("failure_count"))
        previous_cooldown_until = credential.get("cooldown_until")
        previous_last_used_at = credential.get("last_used_at")
        last_used_at = _format_datetime(current_time)
        event: dict[str, Any] = {
            "kind": "provider_credential_state_update",
            "version": 1,
            "provider_id": normalized_provider_id,
            "credential_id": normalized_credential_id,
            "outcome": "success" if success else "failure",
            "previous_status": previous_status,
            "previous_failure_count": previous_failure_count,
            "previous_last_used_at": previous_last_used_at,
            "last_used_at": last_used_at,
        }
        if success:
            credential["status"] = PROVIDER_CREDENTIAL_STATUS_ACTIVE
            credential["cooldown_until"] = None
            credential["failure_count"] = 0
            credential["last_used_at"] = last_used_at
            event.update(
                {
                    "status": PROVIDER_CREDENTIAL_STATUS_ACTIVE,
                    "failure_count": 0,
                    "cooldown_until": None,
                }
            )
        else:
            next_failure_count = previous_failure_count + 1
            credential["failure_count"] = next_failure_count
            credential["last_used_at"] = last_used_at
            if next_failure_count >= PROVIDER_CREDENTIAL_EXHAUSTED_FAILURE_COUNT:
                credential["status"] = PROVIDER_CREDENTIAL_STATUS_EXHAUSTED
                credential["cooldown_until"] = None
                event.update(
                    {
                        "status": PROVIDER_CREDENTIAL_STATUS_EXHAUSTED,
                        "failure_count": next_failure_count,
                        "cooldown_until": None,
                    }
                )
            else:
                cooldown_seconds = _credential_cooldown_seconds(next_failure_count)
                cooldown_until = _format_datetime(current_time + timedelta(seconds=cooldown_seconds))
                credential["status"] = PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN
                credential["cooldown_until"] = cooldown_until
                event.update(
                    {
                        "status": PROVIDER_CREDENTIAL_STATUS_COOLING_DOWN,
                        "failure_count": next_failure_count,
                        "cooldown_until": cooldown_until,
                        "cooldown_seconds": cooldown_seconds,
                    }
                )
        if (
            credential.get("status") == previous_status
            and credential.get("failure_count") == previous_failure_count
            and credential.get("cooldown_until") == previous_cooldown_until
            and credential.get("last_used_at") == previous_last_used_at
        ):
            return updated_settings, {}
        provider_config["credential_pool"] = credential_pool
        return updated_settings, event
    return updated_settings, {}


def _normalize_credential_status(value: Any) -> str:
    status = str(value or PROVIDER_CREDENTIAL_STATUS_ACTIVE).strip().lower().replace("-", "_")
    return status if status in PROVIDER_CREDENTIAL_STATUSES else PROVIDER_CREDENTIAL_STATUS_ACTIVE


def _provider_credential_selection_meta(credential: dict[str, Any], *, previous_status: str) -> dict[str, Any]:
    selected_status = PROVIDER_CREDENTIAL_STATUS_ACTIVE
    selected = {
        "credential_id": str(credential.get("credential_id") or "").strip(),
        "status": selected_status,
        "source": "credential_pool",
    }
    last_used_at = _normalize_optional_text(credential.get("last_used_at"))
    if last_used_at:
        selected["last_used_at"] = last_used_at
    if previous_status != selected_status:
        selected["previous_status"] = previous_status
    return selected


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_failure_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _credential_is_cooling_down(credential: dict[str, Any], *, now: datetime | None = None) -> bool:
    cooldown_until = _parse_datetime(credential.get("cooldown_until"))
    if cooldown_until is None:
        return False
    current = _normalize_datetime(now or datetime.now(timezone.utc))
    return cooldown_until > current


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _credential_cooldown_seconds(failure_count: int) -> int:
    normalized_failure_count = max(1, _normalize_failure_count(failure_count))
    return min(
        PROVIDER_CREDENTIAL_MAX_COOLDOWN_SECONDS,
        PROVIDER_CREDENTIAL_BASE_COOLDOWN_SECONDS * normalized_failure_count,
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return _normalize_datetime(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")
