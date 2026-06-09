from __future__ import annotations

from typing import Any

from app.core.model_catalog import build_model_ref, split_model_ref
from app.core.storage import settings_store
from app.core.storage.embedding_store import embedding_model_has_vectors, register_embedding_model, resolve_embedding_model
from app.tools.model_provider_client import embed_text_with_model_ref


DEFAULT_EMBEDDING_MODEL_DIMENSIONS = 384
EMBEDDING_DIMENSION_PROBE_TEXT = "TooGraph embedding dimension probe."


def sync_default_embedding_model_from_settings(
    settings: dict[str, Any] | None = None,
    model_ref: str = "",
) -> dict[str, Any] | None:
    source_settings = settings if isinstance(settings, dict) else settings_store.load_app_settings()
    selected_model_ref = str(model_ref or source_settings.get("embedding_model_ref") or "").strip()
    if not selected_model_ref:
        return None

    provider_key, model_name = split_model_ref(selected_model_ref, default_provider="local")
    provider = _find_provider(source_settings, provider_key)
    if provider is None:
        return None
    model = _find_provider_model(provider, model_name)
    if model is None or not _model_supports_embedding(model):
        return None

    normalized_model_ref = build_model_ref(provider_key, model_name)
    dimensions, dimensions_source = _embedding_dimensions_with_source(model)
    metadata = {
        "source": "model_providers.default_embedding_model_ref",
        "model_ref": normalized_model_ref,
        "provider_label": str(provider.get("label") or provider_key),
        "model_label": str(model.get("label") or model_name),
        "dimensions_source": dimensions_source,
    }
    existing_model = _resolve_existing_embedding_model(normalized_model_ref)
    if (
        dimensions_source == "default"
        and existing_model is not None
        and embedding_model_has_vectors(str(existing_model["embedding_model_id"]))
    ):
        existing_metadata = dict(existing_model.get("metadata") or {})
        if existing_metadata.get("dimensions_source") != "default":
            dimensions = int(existing_model["dimensions"] or dimensions)
            metadata = {
                **existing_metadata,
                "source": metadata["source"],
                "model_ref": metadata["model_ref"],
                "provider_label": metadata["provider_label"],
                "model_label": metadata["model_label"],
                "dimensions_source": str(existing_metadata.get("dimensions_source") or "provider_probe"),
            }
    return register_embedding_model(
        provider_key=provider_key,
        model=model_name,
        dimensions=dimensions,
        enabled=True,
        metadata=metadata,
    )


def get_default_embedding_model_ref_from_settings(settings: dict[str, Any] | None = None) -> str:
    model = sync_default_embedding_model_from_settings(settings=settings)
    if not model:
        return ""
    return build_model_ref(str(model["provider_key"]), str(model["model"]))


def get_default_embedding_model_refs_from_settings(settings: dict[str, Any] | None = None) -> list[str]:
    model_ref = get_default_embedding_model_ref_from_settings(settings=settings)
    return [model_ref] if model_ref else []


def probe_embedding_model_dimensions(
    settings: dict[str, Any] | None = None,
    model_ref: str = "",
) -> dict[str, Any]:
    source_settings = settings if isinstance(settings, dict) else settings_store.load_app_settings()
    model = sync_default_embedding_model_from_settings(settings=source_settings, model_ref=model_ref)
    if model is None:
        return {
            "status": "unconfigured",
            "model_ref": str(model_ref or source_settings.get("embedding_model_ref") or "").strip(),
            "dimensions": None,
            "dimensions_source": "",
            "error": "No embedding-capable model is configured.",
        }

    normalized_model_ref = build_model_ref(str(model["provider_key"]), str(model["model"]))
    metadata = dict(model.get("metadata") or {})
    try:
        vector, embedding_meta = embed_text_with_model_ref(
            model_ref=normalized_model_ref,
            text=EMBEDDING_DIMENSION_PROBE_TEXT,
            dimensions=None,
        )
        dimensions = len(vector) if isinstance(vector, list) else 0
        if dimensions <= 0:
            raise RuntimeError("Embedding probe returned an empty vector.")
        updated_model = register_embedding_model(
            provider_key=str(model["provider_key"]),
            model=str(model["model"]),
            dimensions=dimensions,
            enabled=True,
            metadata={
                **metadata,
                "source": "model_providers.embedding_dimension_probe",
                "model_ref": normalized_model_ref,
                "dimensions_source": "provider_probe",
            },
        )
        return {
            "status": "succeeded",
            "model_ref": normalized_model_ref,
            "embedding_model_id": updated_model["embedding_model_id"],
            "dimensions": int(updated_model["dimensions"]),
            "dimensions_source": "provider_probe",
            "error": "",
            "embedding_meta": embedding_meta,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "model_ref": normalized_model_ref,
            "embedding_model_id": model["embedding_model_id"],
            "dimensions": int(model["dimensions"] or 0) if model.get("dimensions") else None,
            "dimensions_source": str(metadata.get("dimensions_source") or "default"),
            "error": str(exc),
        }


def _find_provider(settings: dict[str, Any], provider_key: str) -> dict[str, Any] | None:
    providers = settings.get("model_providers")
    if not isinstance(providers, dict):
        return None
    provider = providers.get(provider_key)
    return provider if isinstance(provider, dict) else None


def _find_provider_model(provider: dict[str, Any], model_name: str) -> dict[str, Any] | None:
    models = provider.get("models")
    if not isinstance(models, list):
        return None
    for model in models:
        if not isinstance(model, dict):
            continue
        candidate_name = str(model.get("model") or model.get("id") or "").strip()
        if candidate_name == model_name:
            return model
    return None


def _model_supports_embedding(model: dict[str, Any]) -> bool:
    capabilities = model.get("capabilities")
    return isinstance(capabilities, dict) and bool(capabilities.get("embedding"))


def _embedding_dimensions_with_source(model: dict[str, Any]) -> tuple[int, str]:
    return DEFAULT_EMBEDDING_MODEL_DIMENSIONS, "default"


def _resolve_existing_embedding_model(model_ref: str) -> dict[str, Any] | None:
    try:
        return resolve_embedding_model(model_ref)
    except FileNotFoundError:
        return None
