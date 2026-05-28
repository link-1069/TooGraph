from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ModelProviderCredentialTests(unittest.TestCase):
    def test_update_provider_credential_pool_after_failure_sets_cooldown_and_preserves_secret(self) -> None:
        from app.core.model_provider_credentials import update_provider_credential_pool_after_call

        updated, event = update_provider_credential_pool_after_call(
            {
                "model_providers": {
                    "openai": {
                        "credential_pool": [
                            {
                                "credential_id": "primary",
                                "api_key": "sk-primary",
                                "status": "active",
                                "cooldown_until": None,
                                "failure_count": 1,
                            },
                            {
                                "credential_id": "backup",
                                "api_key": "sk-backup",
                                "status": "active",
                                "cooldown_until": None,
                                "failure_count": 0,
                            },
                        ],
                    }
                }
            },
            provider_id="openai",
            credential_id="primary",
            success=False,
            now=datetime(2026, 5, 29, 3, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(
            updated["model_providers"]["openai"]["credential_pool"],
            [
                {
                    "credential_id": "primary",
                    "status": "cooling_down",
                    "cooldown_until": "2026-05-29T03:02:00Z",
                    "failure_count": 2,
                    "api_key": "sk-primary",
                },
                {
                    "credential_id": "backup",
                    "status": "active",
                    "cooldown_until": None,
                    "failure_count": 0,
                    "api_key": "sk-backup",
                },
            ],
        )
        self.assertEqual(
            event,
            {
                "kind": "provider_credential_state_update",
                "version": 1,
                "provider_id": "openai",
                "credential_id": "primary",
                "outcome": "failure",
                "previous_status": "active",
                "status": "cooling_down",
                "previous_failure_count": 1,
                "failure_count": 2,
                "cooldown_until": "2026-05-29T03:02:00Z",
                "cooldown_seconds": 120,
            },
        )

    def test_update_provider_credential_pool_after_success_clears_failure_state(self) -> None:
        from app.core.model_provider_credentials import update_provider_credential_pool_after_call

        updated, event = update_provider_credential_pool_after_call(
            {
                "model_providers": {
                    "openai": {
                        "credential_pool": [
                            {
                                "credential_id": "primary",
                                "api_key": "sk-primary",
                                "status": "cooling_down",
                                "cooldown_until": "2026-05-29T03:02:00Z",
                                "failure_count": 2,
                            },
                        ],
                    }
                }
            },
            provider_id="openai",
            credential_id="primary",
            success=True,
            now=datetime(2026, 5, 29, 3, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(
            updated["model_providers"]["openai"]["credential_pool"],
            [
                {
                    "credential_id": "primary",
                    "status": "active",
                    "cooldown_until": None,
                    "failure_count": 0,
                    "api_key": "sk-primary",
                },
            ],
        )
        self.assertEqual(
            event,
            {
                "kind": "provider_credential_state_update",
                "version": 1,
                "provider_id": "openai",
                "credential_id": "primary",
                "outcome": "success",
                "previous_status": "cooling_down",
                "status": "active",
                "previous_failure_count": 2,
                "failure_count": 0,
                "cooldown_until": None,
            },
        )

    def test_select_provider_credential_allows_expired_cooling_down_record(self) -> None:
        from app.core.model_provider_credentials import select_provider_credential

        api_key, credential = select_provider_credential(
            {
                "credential_pool": [
                    {
                        "credential_id": "primary",
                        "api_key": "sk-primary",
                        "status": "cooling_down",
                        "cooldown_until": "2026-05-29T02:59:00Z",
                        "failure_count": 2,
                    },
                    {
                        "credential_id": "backup",
                        "api_key": "sk-backup",
                        "status": "active",
                        "failure_count": 0,
                    },
                ]
            },
            now=datetime(2026, 5, 29, 3, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(api_key, "sk-primary")
        self.assertEqual(
            credential,
            {
                "credential_id": "primary",
                "status": "active",
                "source": "credential_pool",
                "previous_status": "cooling_down",
            },
        )


if __name__ == "__main__":
    unittest.main()
