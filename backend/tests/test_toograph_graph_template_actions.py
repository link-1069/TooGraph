from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.actions.definitions import _parse_native_action_manifest
from app.core.schemas.actions import ActionLlmNodeEligibility, ActionSourceScope

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_ROOT = REPO_ROOT / "action" / "official"


def _load_action_module(action_key: str):
    script_path = ACTIONS_ROOT / action_key / "after_llm.py"
    spec = importlib.util.spec_from_file_location(f"test_{action_key}_after_llm", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {action_key} script.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _official_template_payload(template_id: str = "advanced_web_research_loop") -> dict:
    return json.loads((REPO_ROOT / "graph_template" / "official" / template_id / "template.json").read_text(encoding="utf-8"))


class GraphTemplateActionTests(unittest.TestCase):
    def test_manifests_expose_graph_template_creation_eval_gate(self) -> None:
        expected = {
            "toograph_graph_template_reader": {
                "permissions": ["file_read"],
                "eval_suites": [
                    "toograph_graph_template_creation_workflow_core",
                    "buddy_improvement_review_workflow_core",
                ],
            },
            "toograph_graph_template_validator": {
                "permissions": [],
                "eval_suites": [
                    "toograph_graph_template_creation_workflow_core",
                    "buddy_improvement_review_workflow_core",
                ],
            },
            "toograph_graph_template_writer": {
                "permissions": ["file_write"],
                "eval_suites": ["toograph_graph_template_creation_workflow_core"],
            },
        }
        expected_command_args = ["-m", "unittest", "backend.tests.test_toograph_graph_template_actions"]

        for action_key, contract in expected.items():
            with self.subTest(action_key=action_key):
                definition = _parse_native_action_manifest(
                    ACTIONS_ROOT / action_key / "action.json",
                    ActionSourceScope.OFFICIAL,
                ).definition

                self.assertEqual(definition.action_key, action_key)
                self.assertEqual(definition.llm_node_eligibility, ActionLlmNodeEligibility.READY)
                self.assertEqual(definition.permissions, contract["permissions"])
                self.assertEqual(definition.verification_eval_suites, contract["eval_suites"])
                self.assertNotIn("你已绑定", definition.llm_instruction)
                self.assertEqual(len(definition.verification_commands), 1)
                self.assertEqual(definition.verification_commands[0].command, "python")
                self.assertEqual(definition.verification_commands[0].args, expected_command_args)

    def test_reader_returns_existing_official_template_without_runtime_artifacts(self) -> None:
        reader = _load_action_module("toograph_graph_template_reader")

        result = reader.toograph_graph_template_reader(template_id="advanced_web_research_loop")

        self.assertTrue(result["success"])
        self.assertEqual(result["template_package"]["template_id"], "advanced_web_research_loop")
        self.assertEqual(result["template_package"]["source_scope"], "official")
        self.assertEqual(result["template_package"]["template_json"]["template_id"], "advanced_web_research_loop")
        self.assertIn("Read official graph template", result["result"])

    def test_reader_rejects_template_path_traversal(self) -> None:
        reader = _load_action_module("toograph_graph_template_reader")

        result = reader.toograph_graph_template_reader(template_id="../advanced_web_research_loop")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "invalid_template_id")

    def test_validator_reports_node_system_and_runtime_compatibility(self) -> None:
        validator = _load_action_module("toograph_graph_template_validator")

        result = validator.toograph_graph_template_validator(template_json=_official_template_payload())

        self.assertTrue(result["success"])
        self.assertTrue(result["validation_report"]["valid"])
        self.assertEqual(result["validation_report"]["runtime_unsupported_reasons"], [])
        self.assertGreater(result["validation_report"]["node_count"], 0)

    def test_validator_rejects_invalid_template_payload(self) -> None:
        validator = _load_action_module("toograph_graph_template_validator")

        result = validator.toograph_graph_template_validator(template_json={"template_id": "broken"})

        self.assertFalse(result["success"])
        self.assertFalse(result["validation_report"]["valid"])
        self.assertTrue(result["validation_report"]["issues"])

    def test_writer_saves_user_template_with_recoverable_revision(self) -> None:
        writer = _load_action_module("toograph_graph_template_writer")
        payload = _official_template_payload()
        payload["template_id"] = "user_graph_template_writer_demo"
        payload["label"] = "Graph Template Writer Demo"
        payload["default_graph_name"] = "Graph Template Writer Demo"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            user_root = temp_root / "graph_template" / "user"
            official_root = temp_root / "graph_template" / "official"
            revision_root = temp_root / "backend" / "data" / "template_revisions"
            official_root.mkdir(parents=True)
            user_root.mkdir(parents=True)
            revision_root.mkdir(parents=True)

            with (
                patch.object(writer, "USER_TEMPLATES_ROOT", user_root),
                patch.object(writer, "OFFICIAL_TEMPLATES_ROOT", official_root),
                patch.object(writer, "TEMPLATE_REVISION_ROOT", revision_root),
            ):
                result = writer.toograph_graph_template_writer(template_json=payload)

            written_path = user_root / "user_graph_template_writer_demo" / "template.json"
            revision_files = list((revision_root / "user_graph_template_writer_demo").glob("*.json"))
            written_template_exists = written_path.is_file()
            revision_payload = json.loads(revision_files[0].read_text(encoding="utf-8")) if revision_files else {}

        self.assertTrue(result["success"])
        self.assertEqual(result["template_id"], "user_graph_template_writer_demo")
        self.assertEqual(result["template_path"], "graph_template/user/user_graph_template_writer_demo/template.json")
        self.assertTrue(result["revision_id"].startswith("gtrev_"))
        self.assertTrue(written_template_exists)
        self.assertEqual(len(revision_files), 1)
        self.assertIsNone(revision_payload["previous_template"])
        self.assertEqual(revision_payload["next_template"]["template_id"], "user_graph_template_writer_demo")

    def test_writer_uses_runtime_context_template_workspace_override(self) -> None:
        writer = _load_action_module("toograph_graph_template_writer")
        payload = _official_template_payload()
        payload["template_id"] = "user_graph_template_writer_context_demo"
        payload["label"] = "Graph Template Writer Context Demo"
        payload["default_graph_name"] = "Graph Template Writer Context Demo"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            legacy_user_root = temp_root / "legacy" / "graph_template" / "user"
            legacy_revision_root = temp_root / "legacy" / "backend" / "data" / "template_revisions"
            runtime_user_root = temp_root / "runtime" / "graph_template" / "user"
            runtime_revision_root = temp_root / "runtime" / "backend" / "data" / "template_revisions"
            official_root = temp_root / "graph_template" / "official"
            for path in [legacy_user_root, legacy_revision_root, runtime_user_root, runtime_revision_root, official_root]:
                path.mkdir(parents=True)

            runtime_context = {
                "graph_template_writer": {
                    "user_templates_root": str(runtime_user_root),
                    "template_revision_root": str(runtime_revision_root),
                }
            }
            with (
                patch.object(writer, "USER_TEMPLATES_ROOT", legacy_user_root),
                patch.object(writer, "OFFICIAL_TEMPLATES_ROOT", official_root),
                patch.object(writer, "TEMPLATE_REVISION_ROOT", legacy_revision_root),
                patch.dict(os.environ, {"TOOGRAPH_ACTION_RUNTIME_CONTEXT": json.dumps(runtime_context)}),
            ):
                result = writer.toograph_graph_template_writer(template_json=payload)

            runtime_written_path = runtime_user_root / "user_graph_template_writer_context_demo" / "template.json"
            legacy_written_path = legacy_user_root / "user_graph_template_writer_context_demo" / "template.json"
            runtime_revision_files = list((runtime_revision_root / "user_graph_template_writer_context_demo").glob("*.json"))
            legacy_revision_files = list((legacy_revision_root / "user_graph_template_writer_context_demo").glob("*.json"))
            runtime_written_exists = runtime_written_path.is_file()
            legacy_written_exists = legacy_written_path.exists()

        self.assertTrue(result["success"])
        self.assertTrue(runtime_written_exists)
        self.assertFalse(legacy_written_exists)
        self.assertEqual(len(runtime_revision_files), 1)
        self.assertEqual(legacy_revision_files, [])
