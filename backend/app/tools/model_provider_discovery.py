from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from app.core.model_provider_templates import (
    TRANSPORT_ANTHROPIC_MESSAGES,
    TRANSPORT_CODEX_RESPONSES,
    TRANSPORT_GEMINI_GENERATE_CONTENT,
    TRANSPORT_OPENAI_COMPATIBLE,
    build_codex_default_model_item,
    normalize_transport,
)
from app.tools.model_provider_http import (
    anthropic_headers,
    build_auth_headers,
    dedupe_strings,
    normalize_base_url,
    request_json,
)
from app.tools.openai_codex_client import (
    DEFAULT_CODEX_MODEL_IDS,
    codex_http_client_kwargs,
    refresh_codex_access_token,
    resolve_codex_access_token,
)


def parse_data_model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Model discovery returned an unexpected payload shape.")
    return dedupe_strings(
        [
            str(item.get("id") or item.get("name") or "").strip()
            for item in data
            if isinstance(item, dict) and str(item.get("id") or item.get("name") or "").strip()
        ]
    )


def parse_gemini_model_ids(payload: dict[str, Any]) -> list[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Model discovery returned an unexpected payload shape.")

    model_ids: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" not in methods:
            continue
        name = str(item.get("name") or item.get("baseModelId") or "").strip()
        if not name:
            continue
        model_ids.append(name.removeprefix("models/"))
    return dedupe_strings(model_ids)


def _codex_model_slug(item: dict[str, Any]) -> str:
    return str(item.get("slug") or item.get("id") or item.get("name") or "").strip()


def _codex_model_rank(item: dict[str, Any]) -> int:
    priority = item.get("priority")
    return int(priority) if isinstance(priority, (int, float)) else 10_000


def _codex_model_is_visible(item: dict[str, Any]) -> bool:
    if item.get("supported_in_api") is False:
        return False
    visibility = item.get("visibility")
    return not (isinstance(visibility, str) and visibility.strip().lower() in {"hide", "hidden"})


def _codex_capabilities(item: dict[str, Any], fallback: dict[str, bool]) -> dict[str, bool]:
    native_capabilities = item.get("capabilities")
    native_capabilities = native_capabilities if isinstance(native_capabilities, dict) else {}
    capabilities = dict(fallback)
    for key in fallback:
        value = native_capabilities.get(key)
        if isinstance(value, bool):
            capabilities[key] = value
    if capabilities["embedding"]:
        purpose = "embedding"
    elif capabilities["rerank"]:
        purpose = "rerank"
    else:
        purpose = "chat"
    capabilities["chat"] = purpose == "chat"
    capabilities["embedding"] = purpose == "embedding"
    capabilities["rerank"] = purpose == "rerank"
    if purpose != "chat":
        capabilities["vision"] = False
        capabilities["tool_call"] = False
        capabilities["structured_output"] = False
    return capabilities


def _codex_modalities(item: dict[str, Any], capabilities: dict[str, bool], fallback: list[str]) -> list[str]:
    native_modalities = item.get("modalities")
    if isinstance(native_modalities, list):
        modalities = dedupe_strings([str(modality) for modality in native_modalities])
        if modalities:
            return modalities
    return ["text", "image"] if capabilities.get("vision") else list(fallback)


def _codex_positive_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int) and value > 0:
            return value
    return None


def _codex_compression_threshold(value: Any) -> float | None:
    if isinstance(value, (int, float)) and 0 < float(value) <= 1:
        return float(value)
    return None


def parse_codex_model_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Model discovery returned an unexpected payload shape.")

    sortable: list[tuple[int, str, dict[str, Any]]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        if not _codex_model_is_visible(item):
            continue
        slug = _codex_model_slug(item)
        if not slug:
            continue
        model_item = build_codex_default_model_item(slug)
        model_item["label"] = str(
            item.get("display_name")
            or item.get("label")
            or item.get("title")
            or item.get("name")
            or slug
        ).strip() or slug
        model_item["capabilities"] = _codex_capabilities(item, model_item["capabilities"])
        model_item["modalities"] = _codex_modalities(item, model_item["capabilities"], model_item["modalities"])
        context_window = _codex_positive_int(
            item.get("context_window"),
            item.get("context_window_tokens"),
            item.get("max_context_length"),
        )
        if context_window is not None:
            model_item["context_window"] = context_window
        compression_threshold = _codex_compression_threshold(item.get("compression_threshold"))
        if compression_threshold is not None:
            model_item["compression_threshold"] = compression_threshold
        sortable.append((_codex_model_rank(item), slug, model_item))

    sortable.sort(key=lambda entry: (entry[0], entry[1]))
    model_items: list[dict[str, Any]] = []
    seen = set()
    for _rank, slug, model_item in sortable:
        identity = slug.lower()
        if identity in seen:
            continue
        seen.add(identity)
        model_items.append(model_item)
    return model_items


def parse_codex_model_ids(payload: dict[str, Any]) -> list[str]:
    return [item["model"] for item in parse_codex_model_items(payload)]


def derive_lmstudio_native_base_url(openai_base_url: str) -> str:
    parsed = urlsplit(normalize_base_url(openai_base_url))
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    elif path == "/v1":
        path = ""
    native_path = f"{path}/api/v1" if path else "/api/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, native_path, "", ""))


def parse_lmstudio_model_ids(payload: dict[str, Any]) -> list[str]:
    return dedupe_strings([item["model"] for item in parse_lmstudio_model_items(payload)])


def _first_loaded_lmstudio_context_length(item: dict[str, Any]) -> int | None:
    loaded_instances = item.get("loaded_instances")
    if not isinstance(loaded_instances, list):
        return None
    for instance in loaded_instances:
        if not isinstance(instance, dict):
            continue
        config = instance.get("config")
        if not isinstance(config, dict):
            continue
        context_length = config.get("context_length")
        if isinstance(context_length, int) and context_length > 0:
            return context_length
    return None


def _lmstudio_context_window(item: dict[str, Any]) -> int | None:
    loaded_context = _first_loaded_lmstudio_context_length(item)
    if loaded_context is not None:
        return loaded_context
    max_context_length = item.get("max_context_length")
    if isinstance(max_context_length, int) and max_context_length > 0:
        return max_context_length
    return None


def _lmstudio_capabilities(item: dict[str, Any]) -> dict[str, bool]:
    model_type = str(item.get("type") or "").strip().lower()
    native_capabilities = item.get("capabilities")
    native_capabilities = native_capabilities if isinstance(native_capabilities, dict) else {}
    is_embedding = model_type == "embedding"
    is_rerank = model_type == "rerank"
    is_chat = not is_embedding and not is_rerank
    vision = bool(native_capabilities.get("vision")) if is_chat else False
    tool_call = bool(
        native_capabilities.get("trained_for_tool_use")
        or native_capabilities.get("tool_use")
        or native_capabilities.get("tool_call")
    ) if is_chat else False
    return {
        "chat": is_chat,
        "embedding": is_embedding,
        "rerank": is_rerank,
        "vision": vision,
        "tool_call": tool_call,
        "structured_output": is_chat,
    }


def _lmstudio_reasoning_enabled(item: dict[str, Any]) -> bool:
    if str(item.get("type") or "").strip().lower() in {"embedding", "rerank"}:
        return False
    native_capabilities = item.get("capabilities")
    if not isinstance(native_capabilities, dict):
        return False
    reasoning = native_capabilities.get("reasoning")
    if isinstance(reasoning, dict):
        default = str(reasoning.get("default") or "").strip().lower()
        return bool(default and default not in {"off", "none", "false"})
    return bool(reasoning)


def parse_lmstudio_model_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("LM Studio model discovery returned an unexpected payload shape.")

    model_items: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_name = str(item.get("key") or item.get("id") or item.get("model") or "").strip()
        if not model_name:
            continue
        model_type = str(item.get("type") or "").strip().lower()
        context_window = _lmstudio_context_window(item)
        model_item: dict[str, Any] = {
            "model": model_name,
            "label": str(item.get("display_name") or item.get("name") or model_name).strip() or model_name,
            "reasoning": _lmstudio_reasoning_enabled(item),
            "modalities": ["text", "image"] if bool(_lmstudio_capabilities(item).get("vision")) else ["text"],
            "capabilities": _lmstudio_capabilities(item),
        }
        if context_window is not None:
            model_item["context_window"] = context_window
        if model_type == "embedding":
            model_item["embedding"] = {
                "dimensions": None,
            }
        model_items.append(model_item)
    return model_items


def _discover_openai_compatible_model_ids(
    *,
    normalized_base_url: str,
    api_key: str,
    auth_header: str,
    auth_scheme: str,
    timeout_sec: float,
) -> list[str]:
    payload = request_json(
        method="GET",
        url=f"{normalized_base_url}/models",
        timeout_sec=timeout_sec,
        headers=build_auth_headers(api_key=api_key, auth_header=auth_header, auth_scheme=auth_scheme),
        error_label="Model discovery failed",
    )
    return parse_data_model_ids(payload)


def discover_provider_model_items(
    *,
    provider_id: str,
    transport: str,
    base_url: str,
    api_key: str = "",
    auth_header: str = "Authorization",
    auth_scheme: str = "Bearer",
    timeout_sec: float = 8.0,
    resolve_codex_access_token_fn: Callable[[], str] | None = None,
    refresh_codex_access_token_fn: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    normalized_transport = normalize_transport(transport)
    normalized_base_url = normalize_base_url(base_url)
    if normalized_transport == TRANSPORT_OPENAI_COMPATIBLE and str(provider_id or "").strip().lower() == "lmstudio":
        try:
            payload = request_json(
                method="GET",
                url=f"{derive_lmstudio_native_base_url(normalized_base_url)}/models",
                timeout_sec=timeout_sec,
                headers=build_auth_headers(api_key=api_key, auth_header=auth_header, auth_scheme=auth_scheme),
                error_label="LM Studio native model discovery failed",
            )
            return parse_lmstudio_model_items(payload)
        except RuntimeError:
            pass
    if normalized_transport == TRANSPORT_CODEX_RESPONSES:
        resolve_token = resolve_codex_access_token_fn or resolve_codex_access_token
        refresh_token = refresh_codex_access_token_fn or refresh_codex_access_token
        access_token = resolve_token()
        try:
            payload = request_json(
                method="GET",
                url=f"{normalized_base_url}/models",
                timeout_sec=timeout_sec,
                headers=build_auth_headers(api_key=access_token),
                params={"client_version": "1.0.0"},
                error_label="Model discovery failed",
                client_kwargs=codex_http_client_kwargs(timeout=timeout_sec),
            )
        except RuntimeError as exc:
            if "HTTP 401" in str(exc):
                access_token = refresh_token()
                payload = request_json(
                    method="GET",
                    url=f"{normalized_base_url}/models",
                    timeout_sec=timeout_sec,
                    headers=build_auth_headers(api_key=access_token),
                    params={"client_version": "1.0.0"},
                    error_label="Model discovery failed",
                    client_kwargs=codex_http_client_kwargs(timeout=timeout_sec),
                )
            else:
                return [build_codex_default_model_item(model_id) for model_id in DEFAULT_CODEX_MODEL_IDS]
        model_items = parse_codex_model_items(payload)
        return model_items or [build_codex_default_model_item(model_id) for model_id in DEFAULT_CODEX_MODEL_IDS]
    return [
        {"model": model_id, "label": model_id, "modalities": ["text"]}
        for model_id in discover_provider_models(
            provider_id=provider_id,
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
            timeout_sec=timeout_sec,
            resolve_codex_access_token_fn=resolve_codex_access_token_fn,
            refresh_codex_access_token_fn=refresh_codex_access_token_fn,
        )
    ]


def discover_provider_models(
    *,
    provider_id: str,
    transport: str,
    base_url: str,
    api_key: str = "",
    auth_header: str = "Authorization",
    auth_scheme: str = "Bearer",
    timeout_sec: float = 8.0,
    resolve_codex_access_token_fn: Callable[[], str] | None = None,
    refresh_codex_access_token_fn: Callable[[], str] | None = None,
) -> list[str]:
    _ = provider_id
    normalized_transport = normalize_transport(transport)
    normalized_base_url = normalize_base_url(base_url)

    if normalized_transport == TRANSPORT_OPENAI_COMPATIBLE:
        if str(provider_id or "").strip().lower() == "lmstudio":
            try:
                payload = request_json(
                    method="GET",
                    url=f"{derive_lmstudio_native_base_url(normalized_base_url)}/models",
                    timeout_sec=timeout_sec,
                    headers=build_auth_headers(api_key=api_key, auth_header=auth_header, auth_scheme=auth_scheme),
                    error_label="LM Studio native model discovery failed",
                )
                return parse_lmstudio_model_ids(payload)
            except RuntimeError:
                pass
        return _discover_openai_compatible_model_ids(
            normalized_base_url=normalized_base_url,
            api_key=api_key,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
            timeout_sec=timeout_sec,
        )

    if normalized_transport == TRANSPORT_ANTHROPIC_MESSAGES:
        payload = request_json(
            method="GET",
            url=f"{normalized_base_url}/models",
            timeout_sec=timeout_sec,
            headers=anthropic_headers(api_key),
            error_label="Model discovery failed",
        )
        return parse_data_model_ids(payload)

    if normalized_transport == TRANSPORT_GEMINI_GENERATE_CONTENT:
        payload = request_json(
            method="GET",
            url=f"{normalized_base_url}/models",
            timeout_sec=timeout_sec,
            params={"key": str(api_key or "").strip()} if str(api_key or "").strip() else None,
            error_label="Model discovery failed",
        )
        return parse_gemini_model_ids(payload)

    if normalized_transport == TRANSPORT_CODEX_RESPONSES:
        resolve_token = resolve_codex_access_token_fn or resolve_codex_access_token
        refresh_token = refresh_codex_access_token_fn or refresh_codex_access_token
        access_token = resolve_token()
        try:
            payload = request_json(
                method="GET",
                url=f"{normalized_base_url}/models",
                timeout_sec=timeout_sec,
                headers=build_auth_headers(api_key=access_token),
                params={"client_version": "1.0.0"},
                error_label="Model discovery failed",
                client_kwargs=codex_http_client_kwargs(timeout=timeout_sec),
            )
        except RuntimeError as exc:
            if "HTTP 401" in str(exc):
                access_token = refresh_token()
                payload = request_json(
                    method="GET",
                    url=f"{normalized_base_url}/models",
                    timeout_sec=timeout_sec,
                    headers=build_auth_headers(api_key=access_token),
                    params={"client_version": "1.0.0"},
                    error_label="Model discovery failed",
                    client_kwargs=codex_http_client_kwargs(timeout=timeout_sec),
                )
            else:
                return list(DEFAULT_CODEX_MODEL_IDS)
        model_ids = parse_codex_model_ids(payload)
        return model_ids or list(DEFAULT_CODEX_MODEL_IDS)

    raise RuntimeError(f"Unsupported provider transport: {normalized_transport}")  # pragma: no cover
