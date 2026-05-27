from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database
from app.core.storage.memory_store import load_memory_entry
from app.core.storage.run_store import load_run
from app.evaluator.checks import evaluate_case_checks
from app.evaluator.official_seed import seed_official_eval_suites
from app.evaluator.llm_judge import run_llm_judge
from app.evaluator import runner, store
from app.buddy import store as buddy_store
from app.main import app


@contextmanager
def isolated_eval_database():
    old_data_dir = database.DATA_DIR
    old_db_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "toograph.db"
        try:
            database.initialize_storage()
            yield
        finally:
            database.DATA_DIR = old_data_dir
            database.DB_PATH = old_db_path


def _eval_template_record() -> dict[str, object]:
    return {
        "template_id": "mock_template",
        "label": "Mock Template",
        "description": "Mock eval template",
        "default_graph_name": "Mock Eval Template",
        "state_schema": {
            "prompt": {
                "name": "Prompt",
                "description": "",
                "type": "text",
                "value": "",
                "color": "#2563eb",
            }
        },
        "nodes": {
            "input_prompt": {
                "kind": "input",
                "name": "Input Prompt",
                "description": "",
                "ui": {"position": {"x": 0, "y": 0}},
                "reads": [],
                "writes": [{"state": "prompt", "mode": "replace"}],
                "config": {"boundaryType": "text"},
            },
            "output_prompt": {
                "kind": "output",
                "name": "Output Prompt",
                "description": "",
                "ui": {"position": {"x": 240, "y": 0}},
                "reads": [{"state": "prompt", "required": True}],
                "writes": [],
                "config": {
                    "displayMode": "auto",
                    "persistEnabled": False,
                    "persistFormat": "auto",
                    "fileNameTemplate": "",
                },
            },
        },
        "edges": [{"source": "input_prompt", "target": "output_prompt"}],
        "conditional_edges": [],
        "metadata": {"description": "Mock eval template"},
        "source": "official",
        "status": "active",
    }


def _generated_policy_template_payload(template_id: str = "eval_policy_checklist_template") -> dict[str, object]:
    return {
        "template_id": template_id,
        "label": "政策清单生成模板",
        "description": "把政策原文整理成资格初判、材料清单和办理步骤。",
        "default_graph_name": "政策清单生成",
        "state_schema": {
            "policy_text": {
                "name": "政策原文",
                "description": "需要整理的政策文本。",
                "type": "text",
                "value": "",
                "color": "#2563eb",
            },
            "application_checklist": {
                "name": "办理清单",
                "description": "资格初判、材料清单和办理步骤。",
                "type": "markdown",
                "value": "",
                "color": "#16a34a",
            },
        },
        "nodes": {
            "input_policy_text": {
                "kind": "input",
                "name": "输入政策原文",
                "description": "提供政策原文。",
                "ui": {"position": {"x": 80, "y": 120}, "collapsed": False, "size": {"width": 360, "height": 180}},
                "reads": [],
                "writes": [{"state": "policy_text", "mode": "replace"}],
                "config": {"value": "", "boundaryType": "text"},
            },
            "draft_application_checklist": {
                "kind": "agent",
                "name": "整理办理清单",
                "description": "把政策原文整理成结构化办理清单。",
                "ui": {"position": {"x": 560, "y": 100}, "collapsed": False, "size": {"width": 440, "height": 240}},
                "reads": [{"state": "policy_text", "required": True}],
                "writes": [{"state": "application_checklist", "mode": "replace"}],
                "config": {
                    "actionKey": "",
                    "actionBindings": [],
                    "suspendedFreeWrites": [],
                    "actionInstructionBlocks": {},
                    "taskInstruction": "读取政策原文，输出资格初判、材料清单和办理步骤。",
                    "modelSource": "global",
                    "model": "",
                    "thinkingMode": "medium",
                    "temperature": 0.2,
                },
            },
            "output_application_checklist": {
                "kind": "output",
                "name": "输出办理清单",
                "description": "展示整理后的办理清单。",
                "ui": {"position": {"x": 1120, "y": 120}, "collapsed": False, "size": {"width": 420, "height": 220}},
                "reads": [{"state": "application_checklist", "required": True}],
                "writes": [],
                "config": {"displayMode": "markdown", "persistEnabled": False, "persistFormat": "auto", "fileNameTemplate": ""},
            },
        },
        "edges": [
            {"source": "input_policy_text", "target": "draft_application_checklist"},
            {"source": "draft_application_checklist", "target": "output_application_checklist"},
        ],
        "conditional_edges": [],
        "metadata": {
            "category": "policy",
            "role": "generated_policy_checklist",
            "capabilityDiscoverableDefault": True,
            "tags": ["policy", "checklist"],
        },
        "source": "user",
        "status": "active",
    }


def _graph_template_creation_model_fixture(template_payload: dict[str, object]) -> dict[str, object]:
    response_payload = {
        "toograph_graph_template_reader": {
            "template_id": "advanced_web_research_loop",
            "source_scope": "official",
        },
        "requirement_review": {
            "needs_clarification": False,
            "should_create_template": True,
            "summary": "需求明确，可以创建政策办理清单图模板。",
        },
        "generation_brief": "创建一个输入政策文本、生成办理清单并输出 markdown 的 node_system 图模板。",
        "graph_diff_draft": {
            "operation": "create",
            "template_id": template_payload["template_id"],
            "states": ["policy_text", "application_checklist"],
        },
        "template_preview": "模板包含输入政策原文、整理办理清单、输出办理清单三个节点。",
        "test_run_decision": {
            "should_run": False,
            "reason": "eval 只验证生成、校验和受控写入，不执行新模板试运行。",
        },
        "generated_template_id": template_payload["template_id"],
        "generated_template_json": template_payload,
        "template_test_goal": "把政策原文整理成办理清单。",
        "toograph_graph_template_validator": {"template_json": template_payload},
        "save_review": {
            "approved": True,
            "reason": "模板已通过校验，可以写入隔离的用户模板目录。",
        },
        "toograph_graph_template_writer": {
            "template_json": template_payload,
            "reason": "Eval graph template creation workflow.",
        },
        "final_summary": "图模板已生成、校验，并写入用户模板目录。",
    }
    return {
        "model_providers": {
            "eval-primary": {
                "enabled": True,
                "transport": "openai-compatible",
                "base_url": "http://127.0.0.1:9999/v1",
                "models": [
                    {
                        "model": "gpt-primary",
                        "capabilities": {"chat": True, "structured_output": True},
                        "permissions": ["text_generation"],
                    }
                ],
            }
        },
        "responses": {
            "eval-primary/gpt-primary": {
                "content": json.dumps(response_payload, ensure_ascii=False),
                "meta": {"response_id": "graph-template-creation-fixture"},
            }
        },
    }


def _completed_eval_graph_run() -> dict[str, object]:
    return {
        "run_id": "run_completed",
        "graph_id": "eval_buddy_autonomous_loop_case",
        "graph_name": "Buddy 自主主循环 / Eval case",
        "template_id": "buddy_autonomous_loop",
        "status": "completed",
        "runtime_backend": "langgraph",
        "metadata": {
            "eval": {
                "suite_id": "buddy_autonomous_loop_core",
                "case_id": "buddy-main-loop-selector-fallback-after-recent-failures",
                "target_template_id": "buddy_autonomous_loop",
            }
        },
        "final_result": "结论引用 [1]。",
        "errors": [],
        "output_previews": [
            {
                "node_id": "output_final",
                "label": "public_response",
                "source_kind": "state",
                "source_key": "public_response",
                "value": "结论引用 [1]。",
            },
            {
                "node_id": "output_citations",
                "label": "citations",
                "source_kind": "state",
                "source_key": "citations",
                "value": ["kb:1"],
            },
        ],
        "saved_outputs": [
            {
                "node_id": "output_final",
                "source_key": "public_response",
                "path": "backend/data/outputs/run_completed/final.md",
                "format": "md",
                "file_name": "final.md",
            }
        ],
        "artifacts": {
            "exported_outputs": [
                {
                    "node_id": "output_final",
                    "source_key": "public_response",
                    "value": "结论引用 [1]。",
                    "saved_file": {
                        "path": "backend/data/outputs/run_completed/final.md",
                        "format": "md",
                        "file_name": "final.md",
                    },
                }
            ],
            "state_values": {
                "public_response": "结论引用 [1]。",
                "citations": ["kb:1"],
                "capability_selection_trace": {
                    "selected": {"kind": "action", "key": "web_search"},
                    "rejected_candidates": [
                        {
                            "kind": "subgraph",
                            "key": "advanced_web_research_loop",
                            "reason": "recent_failures_fallback_preferred",
                        }
                    ],
                },
            },
        },
        "graph_snapshot": {
            "nodes": {
                "load_history_context": {"kind": "tool"},
                "reply_and_select_capability": {"kind": "agent"},
                "output_ab549b8d": {"kind": "output"},
            }
        },
        "node_status_map": {
            "load_history_context": "completed",
            "reply_and_select_capability": "completed",
            "output_ab549b8d": "completed",
        },
        "node_executions": [
            {"node_id": "load_history_context", "node_type": "tool", "status": "completed"},
            {"node_id": "reply_and_select_capability", "node_type": "agent", "status": "completed"},
            {"node_id": "output_ab549b8d", "node_type": "output", "status": "completed"},
        ],
        "activity_events": [{"kind": "tool_call", "node_id": "load_history_context"}],
    }


class EvaluatorStoreRouteTests(unittest.TestCase):
    def test_eval_store_closes_read_connections(self) -> None:
        class FakeConnection:
            def __init__(self) -> None:
                self.closed = False

            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def execute(self, *_args: object) -> "FakeConnection":
                return self

            def fetchall(self) -> list[object]:
                return []

            def close(self) -> None:
                self.closed = True

        fake_connection = FakeConnection()

        with patch("app.evaluator.store.get_connection", return_value=fake_connection):
            self.assertEqual(store.list_eval_suites(), [])

        self.assertTrue(fake_connection.closed)

    def test_eval_route_starts_case_graph_run_from_target_template(self) -> None:
        saved_runs: list[dict[str, object]] = []

        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.save_run", side_effect=lambda run: saved_runs.append(dict(run))),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "template_eval",
                        "name": "Template eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/template_eval/cases",
                    json={
                        "case_id": "case_one",
                        "name": "Case one",
                        "input_values": {"prompt": "输入材料"},
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "template_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                run_detail_response = client.get(f"/api/evals/runs/{eval_run_id}")

        self.assertEqual(start_response.status_code, 200)
        started_case = start_response.json()
        self.assertEqual(started_case["status"], "running")
        self.assertTrue(started_case["graph_run_id"].startswith("run_"))
        self.assertEqual(started_case["final_output"], {})
        self.assertEqual(started_case["artifacts"], {})
        self.assertEqual(started_case["check_results"], [])
        self.assertEqual(run_detail_response.json()["status"], "running")
        self.assertEqual(saved_runs[0]["metadata"]["eval"]["eval_run_id"], eval_run_id)
        self.assertEqual(saved_runs[0]["metadata"]["eval"]["case_id"], "case_one")
        self.assertEqual(saved_runs[0]["metadata"]["eval"]["target_template_id"], "mock_template")
        self.assertEqual(saved_runs[0]["graph_snapshot"]["state_schema"]["prompt"]["value"], "输入材料")

    def test_eval_runner_attaches_model_runtime_fixture_to_graph_metadata(self) -> None:
        model_runtime_fixture = {
            "model_providers": {
                "eval-primary": {"models": [{"model": "gpt-primary"}]},
                "eval-fallback": {"models": [{"model": "gpt-fallback"}]},
            },
            "failures": {"eval-primary/gpt-primary": {"message": "timeout"}},
            "responses": {"eval-fallback/gpt-fallback": {"content": '{"answer":"fallback"}'}},
        }

        with patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()):
            graph = runner.build_eval_case_graph_document(
                {
                    "eval_run_id": "evalrun_model_runtime",
                    "suite_id": "model_runtime_suite",
                    "target_template_id": "mock_template",
                },
                {
                    "result_id": "result_model_runtime",
                    "suite_id": "model_runtime_suite",
                    "case_id": "case_one",
                },
                {
                    "case_id": "case_one",
                    "metadata": {"fixture_model_runtime": model_runtime_fixture},
                },
            )

        self.assertEqual(graph.metadata["eval"]["model_runtime_fixture"], model_runtime_fixture)

    def test_eval_runner_attaches_tool_runtime_fixture_to_graph_metadata(self) -> None:
        tool_runtime_fixture = {
            "failures": {
                "primary_tool": {
                    "tool_key": "provider_fallback_resolver",
                    "error_type": "eval_tool_timeout",
                    "message": "primary tool failed",
                }
            },
            "responses": {
                "fallback_tool": {
                    "tool_key": "agent_loop_guard",
                    "outputs": {"status": "succeeded", "result": {"fallback": True}},
                }
            },
        }

        with patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()):
            graph = runner.build_eval_case_graph_document(
                {
                    "eval_run_id": "evalrun_tool_runtime",
                    "suite_id": "tool_runtime_suite",
                    "target_template_id": "mock_template",
                },
                {
                    "result_id": "result_tool_runtime",
                    "suite_id": "tool_runtime_suite",
                    "case_id": "case_one",
                },
                {
                    "case_id": "case_one",
                    "metadata": {"fixture_tool_runtime": tool_runtime_fixture},
                },
            )

        self.assertEqual(graph.metadata["eval"]["tool_runtime_fixture"], tool_runtime_fixture)

    def test_eval_runner_attaches_isolated_graph_template_workspace_context(self) -> None:
        with isolated_eval_database():
            with patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()):
                graph = runner.build_eval_case_graph_document(
                    {
                        "eval_run_id": "evalrun_graph_template_workspace",
                        "suite_id": "graph_template_workspace_suite",
                        "target_template_id": "mock_template",
                    },
                    {
                        "result_id": "result_graph_template_workspace",
                        "suite_id": "graph_template_workspace_suite",
                        "case_id": "case_one",
                    },
                    {
                        "case_id": "case_one",
                        "metadata": {"fixture_graph_template_workspace": True},
                    },
                )

            action_context = graph.metadata["action_runtime_context"]["graph_template_writer"]
            user_templates_root = Path(action_context["user_templates_root"])
            revision_root = Path(action_context["template_revision_root"])

            self.assertTrue(user_templates_root.is_dir())
            self.assertTrue(revision_root.is_dir())
            self.assertTrue(str(user_templates_root).startswith(str(database.DATA_DIR)))
            self.assertTrue(str(revision_root).startswith(str(database.DATA_DIR)))

    def test_eval_runner_can_override_agent_models_for_runtime_fixture_cases(self) -> None:
        template = _eval_template_record()
        template["state_schema"] = {
            **template["state_schema"],
            "answer": {"name": "Answer", "description": "", "type": "text", "value": "", "color": "#16a34a"},
        }
        template["nodes"] = {
            **template["nodes"],
            "answer_prompt": {
                "kind": "agent",
                "name": "Answer Prompt",
                "description": "",
                "ui": {"position": {"x": 300, "y": 0}},
                "reads": [{"state": "prompt", "required": True}],
                "writes": [{"state": "answer", "mode": "replace"}],
                "config": {
                    "modelSource": "global",
                    "model": "",
                    "thinkingMode": "low",
                    "temperature": 0,
                    "taskInstruction": "Answer.",
                },
            },
            "embedded_answer": {
                "kind": "subgraph",
                "name": "Embedded Answer",
                "description": "",
                "ui": {"position": {"x": 520, "y": 0}},
                "reads": [],
                "writes": [],
                "config": {
                    "graph": {
                        "state_schema": {
                            "inner_prompt": {
                                "name": "Inner Prompt",
                                "description": "",
                                "type": "text",
                                "value": "",
                                "color": "#2563eb",
                            },
                            "inner_answer": {
                                "name": "Inner Answer",
                                "description": "",
                                "type": "text",
                                "value": "",
                                "color": "#16a34a",
                            },
                        },
                        "nodes": {
                            "inner_answer_prompt": {
                                "kind": "agent",
                                "name": "Inner Answer Prompt",
                                "description": "",
                                "ui": {"position": {"x": 0, "y": 0}},
                                "reads": [{"state": "inner_prompt", "required": False}],
                                "writes": [{"state": "inner_answer", "mode": "replace"}],
                                "config": {
                                    "modelSource": "global",
                                    "model": "",
                                    "thinkingMode": "low",
                                    "temperature": 0,
                                    "taskInstruction": "Answer inside subgraph.",
                                },
                            }
                        },
                        "edges": [],
                        "conditional_edges": [],
                        "metadata": {},
                    }
                },
            },
        }
        template["edges"] = [{"source": "input_prompt", "target": "answer_prompt"}]

        with patch("app.evaluator.runner.load_template_record", return_value=template):
            graph = runner.build_eval_case_graph_document(
                {
                    "eval_run_id": "evalrun_agent_model_ref",
                    "suite_id": "agent_model_ref_suite",
                    "target_template_id": "mock_template",
                },
                {
                    "result_id": "result_agent_model_ref",
                    "suite_id": "agent_model_ref_suite",
                    "case_id": "case_one",
                },
                {
                    "case_id": "case_one",
                    "metadata": {"fixture_agent_model_ref": "eval-primary/gpt-primary"},
                },
            )

        node_config = graph.model_dump(by_alias=True, mode="json")["nodes"]["answer_prompt"]["config"]
        self.assertEqual(node_config["modelSource"], "override")
        self.assertEqual(node_config["model"], "eval-primary/gpt-primary")
        inner_config = graph.model_dump(by_alias=True, mode="json")["nodes"]["embedded_answer"]["config"]["graph"]["nodes"][
            "inner_answer_prompt"
        ]["config"]
        self.assertEqual(inner_config["modelSource"], "override")
        self.assertEqual(inner_config["model"], "eval-primary/gpt-primary")

    def test_eval_route_runs_llm_runtime_fallback_case_with_model_fixture(self) -> None:
        fixture = {
            "model_providers": {
                "eval-primary": {
                    "enabled": True,
                    "transport": "openai-compatible",
                    "base_url": "http://127.0.0.1:9999/v1",
                    "models": [
                        {
                            "model": "gpt-primary",
                            "capabilities": {"chat": True, "structured_output": True},
                            "permissions": ["text_generation"],
                        }
                    ],
                },
                "eval-fallback": {
                    "enabled": True,
                    "transport": "openai-compatible",
                    "base_url": "http://127.0.0.1:9998/v1",
                    "models": [
                        {
                            "model": "gpt-fallback",
                            "capabilities": {"chat": True, "structured_output": True},
                            "permissions": ["text_generation"],
                        }
                    ],
                },
            },
            "failures": {
                "eval-primary/gpt-primary": {
                    "error_type": "provider_timeout",
                    "message": "eval injected timeout",
                }
            },
            "responses": {
                "eval-fallback/gpt-fallback": {
                    "content": "{\"public_response\":\"fallback runtime response\"}",
                    "meta": {"response_id": "fixture-response-route"},
                }
            },
        }

        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "llm_runtime_fallback_route",
                        "name": "LLM runtime fallback route",
                        "target_template_id": "llm_runtime_fallback_eval",
                    },
                )
                client.post(
                    "/api/evals/suites/llm_runtime_fallback_route/cases",
                    json={
                        "case_id": "case_one",
                        "input_values": {"prompt": "Check fallback"},
                        "metadata": {"fixture_model_runtime": fixture},
                        "checks": [
                            {"kind": "schema", "target": "final_output", "required": ["public_response"]},
                            {
                                "kind": "provider_fallback",
                                "target": "provider_fallback_trace",
                                "required_requested": {"provider_id": "eval-primary", "model": "gpt-primary"},
                                "required_selected": {"provider_id": "eval-fallback", "model": "gpt-fallback"},
                                "required_failed": {
                                    "provider_id": "eval-primary",
                                    "error_type": "provider_timeout",
                                },
                                "required_capabilities": ["chat", "structured_output"],
                                "required_permissions": ["text_generation"],
                                "min_fallbacks": 1,
                            },
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "llm_runtime_fallback_route"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertEqual(graph_run["state_values"]["public_response"], "fallback runtime response")
        runtime_configs = [
            execution.get("artifacts", {}).get("runtime_config", {})
            for execution in graph_run.get("node_executions", [])
            if isinstance(execution, dict)
        ]
        self.assertTrue(any(config.get("provider_fallback_used") for config in runtime_configs))
        self.assertFalse(any("model_runtime_fixture" in config for config in runtime_configs))
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(
            collected["final_output"]["provider_fallback_trace"]["selected"]["model_ref"],
            "eval-fallback/gpt-fallback",
        )
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed"])

    def test_eval_route_runs_tool_runtime_fallback_case_with_tool_fixture(self) -> None:
        fixture = {
            "failures": {
                "primary_provider_tool": {
                    "tool_key": "provider_fallback_resolver",
                    "error_type": "eval_tool_timeout",
                    "message": "eval injected timeout",
                    "outputs": {
                        "status": "failed",
                        "selected_model_ref": "",
                        "provider_fallback_trace": {"decision": "tool_failed"},
                    },
                }
            },
            "responses": {
                "fallback_guard_tool": {
                    "tool_key": "agent_loop_guard",
                    "outputs": {
                        "status": "succeeded",
                        "agent_loop_report": {
                            "decision": "fallback_tool_succeeded",
                            "primary_tool_error_type": "eval_tool_timeout",
                        },
                        "agent_loop_stop_reason": "",
                        "agent_loop_should_continue": False,
                        "agent_loop_should_retry": False,
                        "reason": "fallback tool completed",
                    },
                }
            },
        }

        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "tool_runtime_fallback_route",
                        "name": "Tool runtime fallback route",
                        "target_template_id": "tool_runtime_fallback_eval",
                    },
                )
                client.post(
                    "/api/evals/suites/tool_runtime_fallback_route/cases",
                    json={
                        "case_id": "case_one",
                        "input_values": {
                            "requested_model_ref": "openai/gpt-primary",
                            "failure_event": {
                                "model_ref": "openai/gpt-primary",
                                "provider_id": "openai",
                                "error_type": "provider_timeout",
                            },
                            "provider_candidates": [],
                            "required_capabilities": ["chat"],
                            "required_permissions": ["text_generation"],
                            "preserve_permission_scope": True,
                        },
                        "metadata": {"fixture_tool_runtime": fixture},
                        "checks": [
                            {"kind": "schema", "target": "final_output", "required": ["fallback_agent_loop_report"]},
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_tool_invocations": [
                                    {
                                        "node_id": "primary_provider_tool",
                                        "tool_key": "provider_fallback_resolver",
                                        "status": "failed",
                                        "error_type": "eval_tool_timeout",
                                    },
                                    {
                                        "node_id": "fallback_guard_tool",
                                        "tool_key": "agent_loop_guard",
                                        "status": "succeeded",
                                    },
                                ],
                                "min_tool_invocations": 2,
                            },
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "tool_runtime_fallback_route"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertEqual(graph_run["state_values"]["primary_tool_status"], "failed")
        tool_outputs = {
            output["node_id"]: output
            for output in graph_run.get("tool_outputs", [])
            if isinstance(output, dict)
        }
        self.assertEqual(tool_outputs["primary_provider_tool"]["error_type"], "eval_tool_timeout")
        self.assertEqual(tool_outputs["fallback_guard_tool"]["status"], "succeeded")
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(
            collected["final_output"]["fallback_agent_loop_report"]["decision"],
            "fallback_tool_succeeded",
        )
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_live_tool_failure_fallback_case(self) -> None:
        case_id = "buddy-main-loop-recovers-from-live-tool-failure-with-fallback"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertIn("fallback 工具", graph_run["state_values"]["public_response"])
        tool_outputs = [
            output
            for output in graph_run.get("tool_outputs", [])
            if isinstance(output, dict) and output.get("node_id") == "execute_capability"
        ]
        self.assertTrue(
            any(
                output.get("tool_key") == "provider_fallback_resolver"
                and output.get("status") == "failed"
                and output.get("error_type") == "eval_tool_timeout"
                for output in tool_outputs
            )
        )
        self.assertTrue(
            any(
                output.get("tool_key") == "runtime_context_loader"
                and output.get("status") == "succeeded"
                for output in tool_outputs
            )
        )
        capability_trace = graph_run["state_values"]["capability_trace"]
        self.assertIn("primary_failed", json.dumps(capability_trace, ensure_ascii=False))
        self.assertIn("fallback_succeeded", json.dumps(capability_trace, ensure_ascii=False))
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_provider_model_fallback_case(self) -> None:
        case_id = "buddy-main-loop-recovers-from-provider-model-fallback"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertIn("fallback provider", graph_run["state_values"]["public_response"])
        runtime_configs = [
            execution.get("artifacts", {}).get("runtime_config", {})
            for execution in graph_run.get("node_executions", [])
            if isinstance(execution, dict)
        ]
        fallback_traces = [
            config.get("action_input_provider_fallback_trace") or config.get("provider_fallback_trace")
            for config in runtime_configs
            if isinstance(config, dict)
            if config.get("action_input_provider_fallback_trace") or config.get("provider_fallback_trace")
        ]
        self.assertTrue(any(trace.get("selected", {}).get("model_ref") == "eval-fallback/gpt-fallback" for trace in fallback_traces))
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(
            collected["final_output"]["provider_fallback_trace"]["selected"]["model_ref"],
            "eval-fallback/gpt-fallback",
        )
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed", "passed"])

    def test_eval_route_installs_case_fixture_source_runs_before_starting_graph(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "fixture_eval",
                        "name": "Fixture eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/fixture_eval/cases",
                    json={
                        "case_id": "case_with_source_run",
                        "name": "Case with source run",
                        "input_values": {"prompt": "输入材料"},
                        "metadata": {
                            "fixture_runs": [
                                {
                                    "run_id": "run_eval_source_fixture",
                                    "graph_id": "buddy_fixture_graph",
                                    "graph_name": "Buddy source fixture",
                                    "status": "completed",
                                    "metadata": {
                                        "runtime_context": {
                                            "buddy_session_id": "session_eval_fixture",
                                            "buddy_current_message_id": "message_eval_fixture",
                                        }
                                    },
                                    "state_values": {
                                        "user_message": "请记住我偏好简洁回答。",
                                        "conversation_history": {
                                            "kind": "context_assembly_ref",
                                            "source_refs": [
                                                {"source_kind": "buddy_message", "source_id": "message_eval_fixture"}
                                            ],
                                        },
                                        "public_response": "我会在后续回复中保持简洁。",
                                    },
                                }
                            ]
                        },
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "fixture_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_with_source_run/run")
                fixture_run = load_run("run_eval_source_fixture")

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(fixture_run["status"], "completed")
        self.assertEqual(fixture_run["graph_id"], "buddy_fixture_graph")
        self.assertEqual(
            fixture_run["metadata"]["runtime_context"]["buddy_session_id"],
            "session_eval_fixture",
        )
        self.assertEqual(fixture_run["metadata"]["eval_fixture"]["eval_run_id"], eval_run_id)
        self.assertEqual(fixture_run["metadata"]["eval_fixture"]["case_id"], "case_with_source_run")
        self.assertEqual(
            fixture_run["state_snapshot"]["values"]["public_response"],
            "我会在后续回复中保持简洁。",
        )
        self.assertEqual(
            fixture_run["artifacts"]["state_values"]["user_message"],
            "请记住我偏好简洁回答。",
        )

    def test_eval_route_installs_case_fixture_memory_entries_before_starting_graph(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "memory_fixture_eval",
                        "name": "Memory fixture eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/memory_fixture_eval/cases",
                    json={
                        "case_id": "case_with_memory_fixture",
                        "input_values": {"prompt": "召回 memory-fixture-evidence"},
                        "metadata": {
                            "fixture_memory_entries": [
                                {
                                    "memory_id": "mem_eval_fixture_preference",
                                    "scope_kind": "buddy",
                                    "scope_id": "default",
                                    "layer": "long_term",
                                    "memory_type": "preference",
                                    "title": "评测偏好",
                                    "content": "memory-fixture-evidence 表示用户偏好先给结论。",
                                    "confidence": 0.9,
                                    "salience": 0.8,
                                    "sources": [
                                        {
                                            "source_kind": "buddy_message",
                                            "source_id": "msg_eval_fixture_preference",
                                        }
                                    ],
                                }
                            ]
                        },
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "memory_fixture_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_with_memory_fixture/run")
                memory = load_memory_entry("mem_eval_fixture_preference")

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(memory["title"], "评测偏好")
        self.assertEqual(memory["metadata"]["eval_fixture"]["eval_run_id"], eval_run_id)
        self.assertEqual(memory["metadata"]["eval_fixture"]["case_id"], "case_with_memory_fixture")
        self.assertEqual(memory["sources"][0]["source_id"], "msg_eval_fixture_preference")

    def test_eval_route_installs_case_fixture_buddy_sessions_before_starting_graph(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "buddy_session_fixture_eval",
                        "name": "Buddy session fixture eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/buddy_session_fixture_eval/cases",
                    json={
                        "case_id": "case_with_buddy_session_fixture",
                        "input_values": {"prompt": "召回 hybrid-session-evidence"},
                        "metadata": {
                            "fixture_buddy_sessions": [
                                {
                                    "session_id": "session_eval_hybrid_history",
                                    "title": "Hybrid history",
                                    "messages": [
                                        {
                                            "message_id": "msg_eval_hybrid_user",
                                            "role": "user",
                                            "content": "hybrid-session-evidence 来自历史用户消息。",
                                            "client_order": 0,
                                        },
                                        {
                                            "message_id": "msg_eval_hybrid_assistant",
                                            "role": "assistant",
                                            "content": "历史伙伴回复保留 source ref。",
                                            "client_order": 1,
                                        },
                                    ],
                                }
                            ]
                        },
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_session_fixture_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_with_buddy_session_fixture/run"
                )
                session = buddy_store.get_chat_session("session_eval_hybrid_history")
                messages = buddy_store.list_chat_messages("session_eval_hybrid_history")

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(session["title"], "Hybrid history")
        self.assertEqual([message["message_id"] for message in messages], ["msg_eval_hybrid_user", "msg_eval_hybrid_assistant"])
        self.assertEqual(messages[0]["metadata"]["eval_fixture"]["eval_run_id"], eval_run_id)
        self.assertEqual(messages[0]["content"], "hybrid-session-evidence 来自历史用户消息。")

    def test_eval_route_installs_case_fixture_capability_usage_before_starting_graph(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "capability_usage_fixture_eval",
                        "name": "Capability usage fixture eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/capability_usage_fixture_eval/cases",
                    json={
                        "case_id": "case_with_capability_usage_fixture",
                        "input_values": {"prompt": "需要选择健康 fallback 能力"},
                        "metadata": {
                            "fixture_capability_usage_entries": [
                                {
                                    "capability": {
                                        "kind": "subgraph",
                                        "key": "advanced_web_research_loop",
                                    },
                                    "success": False,
                                    "run_id": "run_eval_selector_failed_1",
                                    "summary": "provider timeout",
                                },
                                {
                                    "capability": {
                                        "kind": "subgraph",
                                        "key": "advanced_web_research_loop",
                                    },
                                    "success": False,
                                    "run_id": "run_eval_selector_failed_2",
                                    "summary": "provider timeout",
                                },
                                {
                                    "capability": {"kind": "action", "key": "web_search"},
                                    "success": True,
                                    "run_id": "run_eval_selector_search_ok",
                                    "summary": "search completed",
                                },
                            ]
                        },
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "capability_usage_fixture_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_with_capability_usage_fixture/run"
                )
                second_start_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_with_capability_usage_fixture/run"
                )
                from app.buddy.store import load_capability_usage_stats

                stats = load_capability_usage_stats()

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(second_start_response.status_code, 200)
        capabilities = stats["capabilities"]
        self.assertEqual(capabilities["subgraph:advanced_web_research_loop"]["failure_count"], 2)
        self.assertEqual(capabilities["subgraph:advanced_web_research_loop"]["recent_runs"][0]["success"], False)
        self.assertEqual(capabilities["action:web_search"]["success_count"], 1)

    def test_eval_route_installs_case_fixture_scheduler_records_before_starting_graph(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.scheduler.store.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "scheduler_fixture_eval",
                        "name": "Scheduler fixture eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/scheduler_fixture_eval/cases",
                    json={
                        "case_id": "case_with_scheduler_fixture",
                        "input_values": {"prompt": "读取调度运行"},
                        "metadata": {
                            "fixture_scheduled_graph_jobs": [
                                {
                                    "job_id": "sched_eval_retry_delivery",
                                    "name": "调度重试投递评测",
                                    "template_id": "mock_template",
                                    "schedule_kind": "interval",
                                    "schedule_expr": "PT6H",
                                    "retry_policy": {"max_attempts": 3, "delay_seconds": 300},
                                    "delivery_target": {
                                        "kind": "local_audit",
                                        "label": "Scheduler eval",
                                        "token": "secret-token",
                                    },
                                }
                            ],
                            "fixture_scheduled_graph_job_runs": [
                                {
                                    "job_run_id": "schedrun_eval_retry_delivery_1",
                                    "job_id": "sched_eval_retry_delivery",
                                    "run_id": "run_eval_scheduler_failed_1",
                                    "trigger_reason": "schedule",
                                    "status": "failed",
                                    "error": "provider timeout",
                                    "started_at": "2026-05-27T06:00:00Z",
                                    "completed_at": "2026-05-27T06:05:00Z",
                                    "now": "2026-05-27T06:05:00Z",
                                }
                            ],
                        },
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "scheduler_fixture_eval"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_with_scheduler_fixture/run")
                from app.scheduler import store as scheduler_store

                job = scheduler_store.load_scheduled_graph_job("sched_eval_retry_delivery")
                job_run = scheduler_store.load_scheduled_graph_job_run("schedrun_eval_retry_delivery_1")

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(job["metadata"]["scheduler_retry_pending"]["next_attempt_number"], 2)
        self.assertEqual(job["metadata"]["scheduler_retry_pending"]["parent_run_id"], "run_eval_scheduler_failed_1")
        self.assertEqual(job_run["metadata"]["retry_decision"]["action"], "scheduled")
        self.assertEqual(job_run["metadata"]["delivery_result"]["status"], "delivered")
        self.assertEqual(job_run["metadata"]["delivery_result"]["target"]["token"], "[redacted]")

    def test_eval_route_reruns_case_and_clears_previous_result_data(self) -> None:
        saved_runs: list[dict[str, object]] = []

        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.load_template_record", return_value=_eval_template_record()),
                patch("app.evaluator.runner.save_run", side_effect=lambda run: saved_runs.append(dict(run))),
                patch("app.evaluator.runner.execute_node_system_graph_langgraph", return_value={}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "rerun_eval",
                        "name": "Rerun eval",
                        "target_template_id": "mock_template",
                    },
                )
                client.post(
                    "/api/evals/suites/rerun_eval/cases",
                    json={"case_id": "case_one", "input_values": {"prompt": "第一次输入"}},
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "rerun_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={
                        "graph_run_id": "old_graph_run",
                        "status": "failed",
                        "final_output": {"public_response": "旧输出"},
                        "artifacts": {"old.md": {"path": "old.md"}},
                        "node_failures": [{"node_id": "agent", "error": "failed"}],
                        "check_results": [{"kind": "rule", "status": "failed", "message": "old"}],
                    },
                )

                rerun_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")

        self.assertEqual(rerun_response.status_code, 200)
        rerun_case = rerun_response.json()
        self.assertEqual(rerun_case["status"], "running")
        self.assertNotEqual(rerun_case["graph_run_id"], "old_graph_run")
        self.assertEqual(rerun_case["final_output"], {})
        self.assertEqual(rerun_case["artifacts"], {})
        self.assertEqual(rerun_case["node_failures"], [])
        self.assertEqual(rerun_case["check_results"], [])
        self.assertEqual(saved_runs[-1]["graph_snapshot"]["state_schema"]["prompt"]["value"], "第一次输入")

    def test_eval_route_collects_completed_graph_run_outputs_and_evaluates_checks(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=_completed_eval_graph_run()),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_eval",
                        "name": "Collect eval",
                        "target_graph_id": "graph_collect",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "schema",
                                "target": "final_output",
                                "required": ["public_response", "citations"],
                            },
                            {"kind": "artifact", "target": "final.md"},
                            {"kind": "citation", "min_citations": 1},
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["final_output"]["public_response"], "结论引用 [1]。")
        self.assertEqual(collected["final_output"]["citations"], ["kb:1"])
        self.assertEqual(collected["artifacts"]["final.md"]["path"], "backend/data/outputs/run_completed/final.md")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed"])

    def test_eval_route_collects_graph_run_artifact_and_evaluates_graph_run_check(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=_completed_eval_graph_run()),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_graph_run_eval",
                        "name": "Collect graph run eval",
                        "target_template_id": "buddy_autonomous_loop",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_graph_run_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_template_id": "buddy_autonomous_loop",
                                "required_metadata": {
                                    "eval": {
                                        "suite_id": "buddy_autonomous_loop_core",
                                        "case_id": "buddy-main-loop-selector-fallback-after-recent-failures",
                                    }
                                },
                                "required_state_keys": ["public_response", "capability_selection_trace"],
                                "required_node_ids": ["load_history_context", "reply_and_select_capability"],
                                "required_activity_kinds": ["tool_call"],
                                "min_node_executions": 2,
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_graph_run_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["artifacts"]["graph_run"]["run_id"], "run_completed")
        self.assertEqual(collected["artifacts"]["graph_run"]["template_id"], "buddy_autonomous_loop")
        self.assertIn("capability_selection_trace", collected["artifacts"]["graph_run"]["state_keys"])
        self.assertEqual(collected["check_results"][0]["status"], "passed")
        self.assertEqual(collected["check_results"][0]["actual"]["missing_state_keys"], [])

    def test_eval_route_collects_tool_invocations_for_graph_run_checks(self) -> None:
        graph_run = _completed_eval_graph_run()
        graph_run["tool_outputs"] = [
            {
                "node_id": "primary_tool",
                "tool_key": "provider_fallback_resolver",
                "status": "failed",
                "error": "eval injected timeout",
                "error_type": "eval_tool_timeout",
                "duration_ms": 3,
            },
            {
                "node_id": "fallback_tool",
                "tool_key": "agent_loop_guard",
                "status": "succeeded",
                "error": "",
                "error_type": "",
                "duration_ms": 2,
            },
        ]

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=graph_run),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_tool_invocation_eval",
                        "name": "Collect tool invocation eval",
                        "target_template_id": "buddy_autonomous_loop",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_tool_invocation_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_tool_invocations": [
                                    {
                                        "node_id": "primary_tool",
                                        "tool_key": "provider_fallback_resolver",
                                        "status": "failed",
                                        "error_type": "eval_tool_timeout",
                                    },
                                    {
                                        "node_id": "fallback_tool",
                                        "tool_key": "agent_loop_guard",
                                        "status": "succeeded",
                                    },
                                ],
                                "min_tool_invocations": 2,
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_tool_invocation_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(
            collected["artifacts"]["graph_run"]["tool_invocations"][0]["error_type"],
            "eval_tool_timeout",
        )
        self.assertEqual(collected["check_results"][0]["actual"]["missing_tool_invocations"], [])

    def test_eval_route_collects_subgraph_invocations_for_graph_run_checks(self) -> None:
        graph_run = _completed_eval_graph_run()
        graph_run["capability_outputs"] = [
            {
                "node_id": "execute_capability",
                "capability_kind": "subgraph",
                "capability_key": "advanced_web_research_loop",
                "status": "failed",
                "error": "Missing required input(s) for subgraph 'advanced_web_research_loop': user_question.",
                "error_type": "missing_required_input",
                "duration_ms": 4,
                "child_run_id": "",
            }
        ]

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=graph_run),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_subgraph_invocation_eval",
                        "name": "Collect subgraph invocation eval",
                        "target_template_id": "buddy_autonomous_loop",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_subgraph_invocation_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_subgraph_invocations": [
                                    {
                                        "node_id": "execute_capability",
                                        "subgraph_key": "advanced_web_research_loop",
                                        "status": "failed",
                                        "error_type": "missing_required_input",
                                    }
                                ],
                                "min_subgraph_invocations": 1,
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_subgraph_invocation_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(
            collected["artifacts"]["graph_run"]["subgraph_invocations"][0]["error_type"],
            "missing_required_input",
        )
        self.assertEqual(collected["check_results"][0]["actual"]["missing_subgraph_invocations"], [])

    def test_eval_route_collects_awaiting_permission_graph_run_checks(self) -> None:
        graph_run = _completed_eval_graph_run()
        graph_run["status"] = "awaiting_human"
        graph_run["metadata"] = {
            "eval": {
                "suite_id": "permission_required_eval",
                "case_id": "case_one",
                "target_template_id": "buddy_autonomous_loop",
            },
            "graph_permission_mode": "ask_first",
            "capability_permission_policy": {"approval_required_permission_tiers": ["risky"]},
            "pending_permission_approval": {
                "kind": "capability_permission_approval",
                "node_id": "execute_capability",
                "capability_kind": "action",
                "capability_key": "local_workspace_executor",
                "binding_source": "capability_state",
                "permissions": ["file_write"],
            },
        }
        graph_run["activity_events"] = [
            {
                "kind": "permission_pause",
                "node_id": "execute_capability",
                "status": "awaiting_human",
                "detail": {"action_key": "local_workspace_executor", "permissions": ["file_write"]},
            }
        ]

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=graph_run),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "permission_required_eval",
                        "name": "Permission required eval",
                        "target_template_id": "buddy_autonomous_loop",
                    },
                )
                client.post(
                    "/api/evals/suites/permission_required_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "awaiting_human",
                                "required_metadata": {
                                    "graph_permission_mode": "ask_first",
                                    "pending_permission_approval": {
                                        "kind": "capability_permission_approval",
                                        "node_id": "execute_capability",
                                        "capability_key": "local_workspace_executor",
                                        "permissions": ["file_write"],
                                    },
                                },
                                "required_activity_kinds": ["permission_pause"],
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "permission_required_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["check_results"][0]["actual"]["missing_fields"], [])
        self.assertEqual(collected["check_results"][0]["actual"]["missing_activity_kinds"], [])

    def test_eval_route_runs_buddy_main_loop_permission_required_case(self) -> None:
        case_id = "buddy-main-loop-pauses-for-action-permission-required"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "awaiting_human")
        pending = graph_run["metadata"]["pending_permission_approval"]
        self.assertEqual(pending["kind"], "capability_permission_approval")
        self.assertEqual(pending["node_id"], "execute_capability")
        self.assertEqual(pending["capability_key"], "local_workspace_executor")
        self.assertEqual(pending["binding_source"], "capability_state")
        self.assertEqual(pending["permissions"], ["file_write"])
        self.assertTrue(
            any(
                event.get("kind") == "permission_pause"
                and event.get("node_id") == "execute_capability"
                and event.get("status") == "awaiting_human"
                for event in graph_run.get("activity_events", [])
                if isinstance(event, dict)
            )
        )
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_context_overflow_compaction_case(self) -> None:
        case_id = "buddy-main-loop-compacts-context-overflow-before-reply"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        state_values = graph_run["state_values"]
        self.assertEqual(state_values["context_budget_report"]["reason"], "history_pressure")
        self.assertTrue(state_values["context_budget_report"]["should_compact"])
        self.assertIn("context-overflow-summary", state_values["context_compaction_summary"])
        self.assertIn("context overflow", state_values["public_response"])
        self.assertTrue(
            any(
                output.get("tool_key") == "buddy_context_pressure_check"
                and output.get("node_id") == "check_context_pressure"
                and output.get("status") == "succeeded"
                for output in graph_run.get("tool_outputs", [])
                if isinstance(output, dict)
            )
        )
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_context_overflow_then_tool_failure_fallback_case(self) -> None:
        case_id = "buddy-main-loop-compacts-context-overflow-then-recovers-from-tool-failure"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        state_values = graph_run["state_values"]
        self.assertGreaterEqual(state_values["context_budget_report"]["history_source_chars"], 6000)
        self.assertEqual(state_values["context_budget_report"]["history_omitted_count"], 3)
        self.assertIn("combo-overflow-summary", state_values["context_compaction_summary"])
        self.assertIn("fallback 工具", state_values["public_response"])
        self.assertIn("combo fallback context loaded", state_values["public_response"])
        tool_outputs = [
            output
            for output in graph_run.get("tool_outputs", [])
            if isinstance(output, dict) and output.get("node_id") == "execute_capability"
        ]
        self.assertTrue(
            any(
                output.get("tool_key") == "provider_fallback_resolver"
                and output.get("status") == "failed"
                and output.get("error_type") == "eval_tool_timeout"
                for output in tool_outputs
            )
        )
        self.assertTrue(
            any(
                output.get("tool_key") == "runtime_context_loader"
                and output.get("status") == "succeeded"
                for output in tool_outputs
            )
        )
        capability_trace = json.dumps(state_values["capability_trace"], ensure_ascii=False)
        self.assertIn("buddy_context_compaction", capability_trace)
        self.assertIn("primary_failed", capability_trace)
        self.assertIn("fallback_succeeded", capability_trace)
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_context_overflow_then_subgraph_failure_fallback_case(self) -> None:
        case_id = "buddy-main-loop-compacts-context-overflow-then-recovers-from-subgraph-failure"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        state_values = graph_run["state_values"]
        self.assertIn("combo-subgraph-overflow-summary", state_values["context_compaction_summary"])
        self.assertIn("advanced_web_research_loop", state_values["public_response"])
        self.assertIn("combo subgraph fallback context loaded", state_values["public_response"])
        subgraph_outputs = [
            output
            for output in graph_run.get("capability_outputs", [])
            if isinstance(output, dict)
            and output.get("node_id") == "execute_capability"
            and output.get("capability_kind") == "subgraph"
        ]
        self.assertTrue(
            any(
                output.get("capability_key") == "advanced_web_research_loop"
                and output.get("status") == "failed"
                and output.get("error_type") == "missing_required_input"
                for output in subgraph_outputs
            )
        )
        self.assertTrue(
            any(
                output.get("tool_key") == "runtime_context_loader"
                and output.get("status") == "succeeded"
                for output in graph_run.get("tool_outputs", [])
                if isinstance(output, dict)
            )
        )
        capability_trace = json.dumps(state_values["capability_trace"], ensure_ascii=False)
        self.assertIn("buddy_context_compaction", capability_trace)
        self.assertIn("subgraph_failed", capability_trace)
        self.assertIn("fallback_succeeded", capability_trace)
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_context_overflow_then_permission_pause_case(self) -> None:
        case_id = "buddy-main-loop-compacts-context-overflow-then-pauses-for-action-permission-required"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "awaiting_human")
        state_values = graph_run["state_values"]
        self.assertIn("combo-permission-overflow-summary", state_values["context_compaction_summary"])
        self.assertIn("local_workspace_executor", state_values["public_response"])
        self.assertIn("权限", state_values["public_response"])
        pending = graph_run["metadata"]["pending_permission_approval"]
        self.assertEqual(pending["kind"], "capability_permission_approval")
        self.assertEqual(pending["node_id"], "execute_capability")
        self.assertEqual(pending["capability_key"], "local_workspace_executor")
        self.assertEqual(pending["permissions"], ["file_write"])
        self.assertTrue(
            any(
                event.get("kind") == "permission_pause"
                and event.get("node_id") == "execute_capability"
                and event.get("status") == "awaiting_human"
                for event in graph_run.get("activity_events", [])
                if isinstance(event, dict)
            )
        )
        capability_trace = json.dumps(state_values["capability_trace"], ensure_ascii=False)
        self.assertIn("buddy_context_compaction", capability_trace)
        self.assertIn("permission_required_expected", capability_trace)
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed"])

    def test_eval_route_runs_buddy_main_loop_subgraph_failure_fallback_case(self) -> None:
        case_id = "buddy-main-loop-recovers-from-subgraph-failure-with-fallback"

        with isolated_eval_database():
            with TestClient(app) as client:
                seed_official_eval_suites()
                run_response = client.post("/api/evals/runs", json={"suite_id": "buddy_autonomous_loop_core"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/{case_id}/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertIn("fallback 工具", graph_run["state_values"]["public_response"])
        subgraph_outputs = [
            output
            for output in graph_run.get("capability_outputs", [])
            if isinstance(output, dict)
            and output.get("node_id") == "execute_capability"
            and output.get("capability_kind") == "subgraph"
        ]
        self.assertTrue(
            any(
                output.get("capability_key") == "advanced_web_research_loop"
                and output.get("status") == "failed"
                and output.get("error_type") == "missing_required_input"
                for output in subgraph_outputs
            )
        )
        self.assertTrue(
            any(
                output.get("tool_key") == "runtime_context_loader"
                and output.get("status") == "succeeded"
                for output in graph_run.get("tool_outputs", [])
                if isinstance(output, dict)
            )
        )
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed", "passed", "passed", "passed"])

    def test_eval_route_runs_workspace_executor_action_case_with_model_fixture(self) -> None:
        fixture = {
            "model_providers": {
                "eval-primary": {
                    "enabled": True,
                    "transport": "openai-compatible",
                    "base_url": "http://127.0.0.1:9999/v1",
                    "models": [
                        {
                            "model": "gpt-primary",
                            "capabilities": {"chat": True, "structured_output": True},
                            "permissions": ["text_generation"],
                        }
                    ],
                }
            },
            "responses": {
                "eval-primary/gpt-primary": {
                    "content": "{\"local_workspace_executor\":{\"operation\":\"search\",\"path\":\"docs/hermes-agent-capability-parity-roadmap.md\",\"content\":\"\",\"query\":\"Tool runtime fallback\",\"old_string\":\"\",\"new_string\":\"\",\"replace_all\":false,\"expected_sha256\":\"\",\"expected_mtime_ns\":\"\",\"args\":{}}}",
                    "meta": {"response_id": "workspace-action-fixture"},
                }
            },
        }

        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "workspace_executor_route",
                        "name": "Workspace executor route",
                        "target_template_id": "workspace_executor_eval",
                    },
                )
                client.post(
                    "/api/evals/suites/workspace_executor_route/cases",
                    json={
                        "case_id": "case_one",
                        "input_values": {
                            "workspace_request": "在路线图里搜索 Tool runtime fallback 的记录。"
                        },
                        "metadata": {"fixture_model_runtime": fixture},
                        "checks": [
                            {
                                "kind": "schema",
                                "target": "final_output",
                                "required": ["workspace_success", "workspace_result"],
                            },
                            {
                                "kind": "rule",
                                "target": "workspace_result",
                                "must_include": ["Tool runtime fallback"],
                            },
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_action_invocations": [
                                    {
                                        "node_id": "run_workspace_search",
                                        "action_key": "local_workspace_executor",
                                        "status": "succeeded",
                                    }
                                ],
                                "min_action_invocations": 1,
                            },
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "workspace_executor_route"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(graph_run["status"], "completed")
        self.assertEqual(graph_run["state_values"]["workspace_success"], True)
        action_outputs = {
            output["node_id"]: output
            for output in graph_run.get("action_outputs", [])
            if isinstance(output, dict)
        }
        self.assertEqual(action_outputs["run_workspace_search"]["action_key"], "local_workspace_executor")
        self.assertEqual(action_outputs["run_workspace_search"]["inputs"]["operation"], "search")
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["check_results"][2]["actual"]["missing_action_invocations"], [])

    def test_eval_route_runs_graph_template_creation_workflow_with_action_fixtures(self) -> None:
        template_payload = _generated_policy_template_payload("eval_policy_checklist_template")
        fixture = _graph_template_creation_model_fixture(template_payload)

        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "graph_template_creation_route",
                        "name": "Graph template creation route",
                        "target_template_id": "toograph_graph_template_creation_workflow",
                    },
                )
                client.post(
                    "/api/evals/suites/graph_template_creation_route/cases",
                    json={
                        "case_id": "case_one",
                        "input_values": {
                            "template_request": "创建政策办理清单图模板。",
                            "target_template_id": "advanced_web_research_loop",
                            "capability_gap": {
                                "requested_capability": "policy_document_to_application_checklist_graph",
                                "risk": "template_creation",
                            },
                        },
                        "metadata": {
                            "fixture_agent_model_ref": "eval-primary/gpt-primary",
                            "fixture_model_runtime": fixture,
                            "fixture_graph_template_workspace": True,
                        },
                        "checks": [
                            {
                                "kind": "schema",
                                "target": "final_output",
                                "required": [
                                    "generated_template_json",
                                    "validation_report",
                                    "write_template_result",
                                    "final_summary",
                                ],
                            },
                            {
                                "kind": "rule",
                                "target": "write_template_result",
                                "must_include": ["eval_policy_checklist_template", "gtrev_"],
                            },
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_state_keys": [
                                    "generated_template_json",
                                    "validation_report",
                                    "write_template_result",
                                    "written_template_revision_id",
                                ],
                                "required_output_keys": ["final_summary"],
                                "required_action_invocations": [
                                    {
                                        "node_id": "read_existing_template",
                                        "action_key": "toograph_graph_template_reader",
                                        "status": "succeeded",
                                    },
                                    {
                                        "node_id": "validate_template_json",
                                        "action_key": "toograph_graph_template_validator",
                                        "status": "succeeded",
                                    },
                                    {
                                        "node_id": "write_template_json",
                                        "action_key": "toograph_graph_template_writer",
                                        "status": "succeeded",
                                    },
                                ],
                                "min_action_invocations": 3,
                            },
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "graph_template_creation_route"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

            action_context = graph_run["metadata"]["action_runtime_context"]["graph_template_writer"]
            written_template = (
                Path(action_context["user_templates_root"])
                / "eval_policy_checklist_template"
                / "template.json"
            )
            revision_files = list(
                (Path(action_context["template_revision_root"]) / "eval_policy_checklist_template").glob("*.json")
            )
            written_template_exists = written_template.is_file()
            revision_count = len(revision_files)

        self.assertEqual(graph_run["status"], "completed")
        self.assertTrue(written_template_exists)
        self.assertGreaterEqual(revision_count, 1)
        self.assertEqual(graph_run["state_values"]["validation_success"], True)
        self.assertEqual(graph_run["state_values"]["write_template_success"], True)
        self.assertEqual(graph_run["state_values"]["written_template_id"], "eval_policy_checklist_template")
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["check_results"][2]["actual"]["missing_action_invocations"], [])

    def test_eval_route_runs_video_segmenter_tool_case_with_video_fixture(self) -> None:
        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "video_segmenter_route",
                        "name": "Video segmenter route",
                        "target_template_id": "video_segmenter_eval",
                    },
                )
                client.post(
                    "/api/evals/suites/video_segmenter_route/cases",
                    json={
                        "case_id": "case_one",
                        "metadata": {
                            "fixture_video_files": [
                                {
                                    "state_key": "source_video",
                                    "filename": "source.mp4",
                                    "duration_seconds": 1.2,
                                }
                            ]
                        },
                        "checks": [
                            {
                                "kind": "schema",
                                "target": "final_output",
                                "required": ["video_segments"],
                            },
                            {
                                "kind": "rule",
                                "target": "video_segments",
                                "must_include": ["segment_000.mp4"],
                            },
                            {
                                "kind": "graph_run",
                                "target": "graph_run",
                                "required_status": "completed",
                                "required_tool_invocations": [
                                    {
                                        "node_id": "segment_video",
                                        "tool_key": "video_segmenter",
                                        "status": "succeeded",
                                    }
                                ],
                                "min_tool_invocations": 1,
                            },
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "video_segmenter_route"})
                eval_run_id = run_response.json()["eval_run_id"]

                start_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/run")
                graph_run_id = start_response.json()["graph_run_id"]
                graph_run = load_run(graph_run_id)
                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(graph_run["status"], "completed")
        segments = graph_run["state_values"]["video_segments"]
        self.assertGreaterEqual(len(segments), 1)
        self.assertTrue(str(segments[0]["local_path"]).endswith("segment_000.mp4"))
        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(collected["status"], "passed")
        self.assertEqual(collected["check_results"][2]["actual"]["missing_tool_invocations"], [])

    def test_eval_route_collects_provider_fallback_trace_from_graph_run_runtime_config(self) -> None:
        trace = {
            "kind": "provider_fallback_trace",
            "decision": "fallback_selected",
            "fallback_used": True,
            "requested": {
                "provider_id": "eval-primary",
                "model": "gpt-primary",
                "model_ref": "eval-primary/gpt-primary",
            },
            "selected": {
                "provider_id": "eval-fallback",
                "model": "gpt-fallback",
                "model_ref": "eval-fallback/gpt-fallback",
            },
            "failed_candidates": [
                {
                    "provider_id": "eval-primary",
                    "model": "gpt-primary",
                    "model_ref": "eval-primary/gpt-primary",
                    "error_type": "provider_timeout",
                }
            ],
            "fallback_candidates": [
                {
                    "provider_id": "eval-fallback",
                    "model": "gpt-fallback",
                    "model_ref": "eval-fallback/gpt-fallback",
                    "reason": "compatible_fallback",
                }
            ],
            "required_capabilities": ["chat", "structured_output"],
            "required_permissions": ["text_generation"],
        }
        graph_run = _completed_eval_graph_run()
        graph_run["node_executions"][1]["artifacts"] = {"runtime_config": {"provider_fallback_trace": trace}}

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=graph_run),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_provider_fallback_eval",
                        "name": "Collect provider fallback eval",
                        "target_template_id": "buddy_autonomous_loop",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_provider_fallback_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "provider_fallback",
                                "target": "provider_fallback_trace",
                                "required_requested": {"provider_id": "eval-primary", "model": "gpt-primary"},
                                "required_selected": {"provider_id": "eval-fallback", "model": "gpt-fallback"},
                                "required_failed": {
                                    "provider_id": "eval-primary",
                                    "error_type": "provider_timeout",
                                },
                                "required_capabilities": ["chat", "structured_output"],
                                "required_permissions": ["text_generation"],
                                "min_fallbacks": 1,
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_provider_fallback_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 200)
        collected = collect_response.json()
        self.assertEqual(
            collected["final_output"]["provider_fallback_trace"]["selected"]["model_ref"],
            "eval-fallback/gpt-fallback",
        )
        self.assertEqual(
            collected["artifacts"]["graph_run"]["provider_fallback_traces"][0]["selected"]["model_ref"],
            "eval-fallback/gpt-fallback",
        )
        self.assertEqual([check["status"] for check in collected["check_results"]], ["passed"])

    def test_eval_route_collect_can_opt_into_llm_judge_checks(self) -> None:
        def fake_create_judge_runner():
            return lambda **_kwargs: {
                "status": "passed",
                "score": 0.9,
                "message": "Useful and grounded.",
                "actual": {"verdict": "pass"},
                "details": {"model_ref": "test/judge-model"},
            }

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value=_completed_eval_graph_run()),
                patch("app.api.routes_evals.create_llm_judge_runner", side_effect=fake_create_judge_runner) as create_runner,
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "collect_judge_eval",
                        "name": "Collect judge eval",
                        "target_graph_id": "graph_collect",
                    },
                )
                client.post(
                    "/api/evals/suites/collect_judge_eval/cases",
                    json={
                        "case_id": "case_one",
                        "checks": [
                            {
                                "kind": "llm_judge",
                                "name": "Rubric judge",
                                "rubric": "The answer must be useful and grounded.",
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "collect_judge_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_completed", "status": "running"},
                )

                collect_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/collect",
                    json={"run_llm_judge": True},
                )

        self.assertEqual(collect_response.status_code, 200)
        self.assertEqual(collect_response.json()["status"], "passed")
        self.assertEqual(collect_response.json()["check_results"][0]["reviewer"], "llm_judge")
        self.assertEqual(collect_response.json()["check_results"][0]["score"], 0.9)
        self.assertEqual(create_runner.call_count, 1)

    def test_eval_route_collect_rejects_non_terminal_graph_run(self) -> None:
        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.load_run", return_value={"run_id": "run_pending", "status": "running"}),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "pending_collect_eval",
                        "name": "Pending collect eval",
                        "target_graph_id": "graph_collect",
                    },
                )
                client.post(
                    "/api/evals/suites/pending_collect_eval/cases",
                    json={"case_id": "case_one"},
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "pending_collect_eval"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_pending", "status": "running"},
                )

                collect_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/case_one/collect")

        self.assertEqual(collect_response.status_code, 409)
        self.assertIn("not terminal", collect_response.json()["detail"])

    def test_eval_check_executor_evaluates_schema_artifact_rule_and_citation_checks(self) -> None:
        case = {
            "case_id": "policy_answer",
            "expected": {"min_citations": 2},
            "checks": [
                {
                    "kind": "schema",
                    "name": "Final output fields",
                    "target": "final_output",
                    "required": ["public_response", "citations"],
                },
                {"kind": "artifact", "name": "Markdown artifact", "target": "final.md"},
                {
                    "kind": "rule",
                    "name": "Grounded answer",
                    "target": "public_response",
                    "must_include": ["引用"],
                    "forbidden": ["保证通过"],
                },
                {"kind": "citation", "name": "Two citations", "min_citations": 2},
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={"public_response": "已引用 [1] 和 [2]，仍需人工确认。", "citations": ["kb:1", "kb:2"]},
            artifacts={"final.md": {"path": "backend/data/outputs/run/final.md", "summary": "final answer"}},
        )

        self.assertEqual([result["status"] for result in results], ["passed", "passed", "passed", "passed"])
        self.assertEqual(results[0]["actual"]["present"], ["public_response", "citations"])
        self.assertEqual(results[1]["actual"]["found"], True)
        self.assertEqual(results[2]["actual"]["forbidden_found"], [])
        self.assertEqual(results[3]["actual"]["citation_count"], 2)

    def test_eval_check_executor_rule_checks_can_match_structured_target_keys(self) -> None:
        case = {
            "case_id": "structured_report",
            "checks": [
                {
                    "kind": "rule",
                    "name": "Report records budget fields",
                    "target": "graph_run.state_values.context_budget_report",
                    "must_include": ["history_source_chars", "history_omitted_count", "history_pressure"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={},
            artifacts={
                "graph_run": {
                    "state_values": {
                        "context_budget_report": {
                            "history_source_chars": 6056,
                            "history_omitted_count": 3,
                            "reason": "history_pressure",
                        }
                    }
                }
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["missing"], [])

    def test_eval_check_executor_evaluates_graph_run_contract(self) -> None:
        case = {
            "case_id": "buddy_e2e_run_contract",
            "checks": [
                {
                    "kind": "graph_run",
                    "name": "Buddy graph run contract",
                    "target": "graph_run",
                    "required_status": "completed",
                    "required_template_id": "buddy_autonomous_loop",
                    "required_metadata": {"eval": {"suite_id": "buddy_autonomous_loop_core"}},
                    "required_state_keys": ["public_response", "capability_selection_trace"],
                    "required_node_ids": ["reply_and_select_capability"],
                    "required_activity_kinds": ["tool_call"],
                    "min_node_executions": 2,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={},
            artifacts={
                "graph_run": {
                    "run_id": "run_completed",
                    "status": "completed",
                    "template_id": "buddy_autonomous_loop",
                    "metadata": {"eval": {"suite_id": "buddy_autonomous_loop_core"}},
                    "state_keys": ["public_response", "capability_selection_trace"],
                    "node_ids": ["load_history_context", "reply_and_select_capability"],
                    "activity_kinds": ["tool_call"],
                    "node_execution_count": 3,
                }
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["missing_state_keys"], [])
        self.assertEqual(results[0]["actual"]["missing_node_ids"], [])

    def test_eval_check_executor_evaluates_graph_run_tool_invocation_contract(self) -> None:
        case = {
            "case_id": "tool_runtime_fallback_contract",
            "checks": [
                {
                    "kind": "graph_run",
                    "target": "graph_run",
                    "required_status": "completed",
                    "required_tool_invocations": [
                        {
                            "node_id": "primary_tool",
                            "tool_key": "provider_fallback_resolver",
                            "status": "failed",
                            "error_type": "eval_tool_timeout",
                        },
                        {
                            "node_id": "fallback_tool",
                            "tool_key": "agent_loop_guard",
                            "status": "succeeded",
                        },
                    ],
                    "min_tool_invocations": 2,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={},
            artifacts={
                "graph_run": {
                    "status": "completed",
                    "tool_invocations": [
                        {
                            "node_id": "primary_tool",
                            "tool_key": "provider_fallback_resolver",
                            "status": "failed",
                            "error_type": "eval_tool_timeout",
                        },
                        {
                            "node_id": "fallback_tool",
                            "tool_key": "agent_loop_guard",
                            "status": "succeeded",
                            "error_type": "",
                        },
                    ],
                }
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["missing_tool_invocations"], [])

    def test_eval_check_executor_evaluates_graph_run_action_invocation_contract(self) -> None:
        case = {
            "case_id": "workspace_action_contract",
            "checks": [
                {
                    "kind": "graph_run",
                    "target": "graph_run",
                    "required_status": "completed",
                    "required_action_invocations": [
                        {
                            "node_id": "run_workspace_search",
                            "action_key": "local_workspace_executor",
                            "status": "succeeded",
                        }
                    ],
                    "min_action_invocations": 1,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={},
            artifacts={
                "graph_run": {
                    "status": "completed",
                    "action_invocations": [
                        {
                            "node_id": "run_workspace_search",
                            "action_key": "local_workspace_executor",
                            "status": "succeeded",
                            "error_type": "",
                        }
                    ],
                }
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["missing_action_invocations"], [])

    def test_eval_check_executor_evaluates_graph_run_subgraph_invocation_contract(self) -> None:
        case = {
            "case_id": "subgraph_failure_contract",
            "checks": [
                {
                    "kind": "graph_run",
                    "target": "graph_run",
                    "required_status": "completed",
                    "required_subgraph_invocations": [
                        {
                            "node_id": "execute_capability",
                            "subgraph_key": "advanced_web_research_loop",
                            "status": "failed",
                            "error_type": "missing_required_input",
                        }
                    ],
                    "min_subgraph_invocations": 1,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={},
            artifacts={
                "graph_run": {
                    "status": "completed",
                    "subgraph_invocations": [
                        {
                            "node_id": "execute_capability",
                            "subgraph_key": "advanced_web_research_loop",
                            "status": "failed",
                            "error_type": "missing_required_input",
                        }
                    ],
                }
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["missing_subgraph_invocations"], [])

    def test_eval_check_executor_evaluates_knowledge_retrieval_quality(self) -> None:
        case = {
            "case_id": "refund_policy_retrieval",
            "checks": [
                {
                    "kind": "knowledge_retrieval",
                    "name": "Refund policy retrieval quality",
                    "target": "knowledge_context",
                    "min_results": 2,
                    "required_chunk_ids": ["refund-policy#rules"],
                    "required_citation_ids": ["kb:hybrid-test:1"],
                    "required_source_paths": ["docs/policies/refund.md"],
                    "required_terms": ["Refund audit policy", "human review"],
                    "forbidden_terms": ["unverified shortcut"],
                    "max_citations": 3,
                    "max_context_chars": 900,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "knowledge_context": {
                    "result_count": 2,
                    "context": (
                        "Refund audit policy requires support tickets and human review before approval. "
                        "Evidence must stay citation-ready."
                    ),
                    "results": [
                        {
                            "citation_id": "kb:hybrid-test:1",
                            "chunk_id": "refund-policy#rules",
                            "title": "Refund Policy",
                            "source": "https://example.test/refund",
                            "summary": "Refund audit policy",
                            "metadata": {"source_path": "docs/policies/refund.md"},
                            "retrieval": {"mode": "hybrid", "keyword_score": 1.0, "vector_score": 0.77},
                        },
                        {
                            "citation_id": "kb:hybrid-test:2",
                            "chunk_id": "refund-policy#evidence",
                            "title": "Refund Evidence",
                            "source": "docs/policies/refund.md",
                            "summary": "Evidence requirements",
                            "metadata": {"source_path": "docs/policies/refund.md"},
                            "retrieval": {"mode": "hybrid", "keyword_score": 0.8, "vector_score": 0.52},
                        },
                    ],
                    "citations": [
                        {"citation_id": "kb:hybrid-test:1", "chunk_id": "refund-policy#rules"},
                        {"citation_id": "kb:hybrid-test:2", "chunk_id": "refund-policy#evidence"},
                    ],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["result_count"], 2)
        self.assertEqual(results[0]["actual"]["citation_count"], 2)
        self.assertEqual(results[0]["actual"]["missing_chunk_ids"], [])
        self.assertEqual(results[0]["actual"]["missing_citation_ids"], [])
        self.assertEqual(results[0]["actual"]["missing_source_paths"], [])
        self.assertEqual(results[0]["actual"]["missing_terms"], [])
        self.assertEqual(results[0]["actual"]["forbidden_terms_found"], [])

    def test_eval_check_executor_evaluates_memory_retrieval_quality(self) -> None:
        case = {
            "case_id": "memory_recall_quality",
            "checks": [
                {
                    "kind": "memory_retrieval",
                    "name": "Memory recall quality",
                    "target": "memory_search_report",
                    "min_results": 1,
                    "required_memory_ids": ["mem_eval_preference"],
                    "required_source_refs": [
                        {"source_kind": "buddy_message", "source_id": "msg_eval_preference"}
                    ],
                    "required_terms": ["先给结论", "memory recall"],
                    "forbidden_terms": ["无来源"],
                    "max_context_chars": 1200,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "memory_search_report": {
                    "query": "memory recall",
                    "memory_count": 1,
                    "context_chars": 42,
                    "memory_ids": ["mem_eval_preference"],
                    "source_refs": [
                        {
                            "source_kind": "memory_entry",
                            "source_id": "mem_eval_preference",
                        },
                        {
                            "source_kind": "buddy_message",
                            "source_id": "msg_eval_preference",
                        },
                    ],
                    "results": [
                        {
                            "memory_id": "mem_eval_preference",
                            "title": "回复偏好",
                            "content": "用户偏好 memory recall 命中后先给结论。",
                        }
                    ],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["memory_count"], 1)
        self.assertEqual(results[0]["actual"]["missing_memory_ids"], [])
        self.assertEqual(results[0]["actual"]["missing_source_refs"], [])
        self.assertEqual(results[0]["actual"]["missing_terms"], [])

    def test_eval_check_executor_fails_memory_retrieval_when_required_rerank_order_is_missing(self) -> None:
        case = {
            "case_id": "memory_rerank_quality",
            "checks": [
                {
                    "kind": "memory_retrieval",
                    "target": "memory_search_report",
                    "min_results": 2,
                    "required_memory_ids": ["mem_expected", "mem_other"],
                    "required_reranker_model_ref": "local-rerank/bge-reranker-v2",
                    "required_rerank_status": "succeeded",
                    "required_top_memory_id": "mem_expected",
                    "required_ranked_memory_ids": ["mem_expected", "mem_other"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "memory_search_report": {
                    "memory_count": 2,
                    "memory_ids": ["mem_expected", "mem_other"],
                    "ranking_reports": [
                        {
                            "kind": "retrieval_ranking_report",
                            "reranker_model_ref": "local-rerank/bge-reranker-v2",
                            "ranking_metadata": {"rerank": {"status": "succeeded"}},
                            "ranked_results": [
                                {
                                    "rank": 1,
                                    "source_ref": {"source_kind": "memory_entry", "source_id": "mem_other"},
                                    "rerank_score": 0.91,
                                },
                                {
                                    "rank": 2,
                                    "source_ref": {"source_kind": "memory_entry", "source_id": "mem_expected"},
                                    "rerank_score": 0.89,
                                },
                            ],
                        }
                    ],
                    "results": [
                        {"memory_id": "mem_expected", "content": "expected memory"},
                        {"memory_id": "mem_other", "content": "other memory"},
                    ],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("Expected top reranked memory id mem_expected", results[0]["message"])
        self.assertEqual(results[0]["actual"]["top_memory_id"], "mem_other")
        self.assertEqual(results[0]["actual"]["ranked_memory_ids"], ["mem_other", "mem_expected"])

    def test_eval_check_executor_passes_memory_retrieval_rerank_quality(self) -> None:
        case = {
            "case_id": "memory_rerank_quality",
            "checks": [
                {
                    "kind": "memory_retrieval",
                    "target": "memory_search_report",
                    "min_results": 2,
                    "required_memory_ids": ["mem_expected", "mem_other"],
                    "required_reranker_model_ref": "local-rerank/bge-reranker-v2",
                    "required_rerank_status": "succeeded",
                    "required_top_memory_id": "mem_expected",
                    "required_ranked_memory_ids": ["mem_expected", "mem_other"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "memory_search_report": {
                    "memory_count": 2,
                    "memory_ids": ["mem_expected", "mem_other"],
                    "ranking_reports": [
                        {
                            "kind": "retrieval_ranking_report",
                            "reranker_model_ref": "local-rerank/bge-reranker-v2",
                            "ranking_metadata": {"rerank": {"status": "succeeded"}},
                            "ranked_results": [
                                {
                                    "rank": 1,
                                    "source_ref": {"source_kind": "memory_entry", "source_id": "mem_expected"},
                                    "rerank_score": 0.97,
                                },
                                {
                                    "rank": 2,
                                    "source_ref": {"source_kind": "memory_entry", "source_id": "mem_other"},
                                    "rerank_score": 0.61,
                                },
                            ],
                        }
                    ],
                    "results": [
                        {"memory_id": "mem_expected", "content": "expected memory"},
                        {"memory_id": "mem_other", "content": "other memory"},
                    ],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["actual"]["top_memory_id"], "mem_expected")
        self.assertEqual(results[0]["actual"]["rerank_statuses"], ["succeeded"])

    def test_eval_check_executor_evaluates_hybrid_recall_report(self) -> None:
        case = {
            "case_id": "hybrid_recall_quality",
            "checks": [
                {
                    "kind": "hybrid_recall",
                    "name": "Hybrid recall quality",
                    "target": "hybrid_recall_report",
                    "min_memory_results": 1,
                    "min_session_results": 1,
                    "required_memory_ids": ["mem_eval_hybrid_preference"],
                    "required_message_ids": ["msg_eval_hybrid_user"],
                    "required_source_refs": [
                        {"source_kind": "memory_entry", "source_id": "mem_eval_hybrid_preference"},
                        {"source_kind": "buddy_message", "source_id": "msg_eval_hybrid_user"},
                    ],
                    "required_terms": ["hybrid-memory-evidence", "hybrid-session-evidence"],
                    "max_context_chars": 1600,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "hybrid_recall_report": {
                    "scope": "hybrid_recall",
                    "query": "hybrid evidence",
                    "memory_count": 1,
                    "session_count": 1,
                    "context_chars": 84,
                    "memory_ids": ["mem_eval_hybrid_preference"],
                    "message_ids": ["msg_eval_hybrid_user"],
                    "source_refs": [
                        {"source_kind": "memory_entry", "source_id": "mem_eval_hybrid_preference"},
                        {"source_kind": "buddy_message", "source_id": "msg_eval_hybrid_user"},
                    ],
                    "results": [
                        {
                            "kind": "memory",
                            "memory_id": "mem_eval_hybrid_preference",
                            "content": "hybrid-memory-evidence 表示用户偏好。",
                        },
                        {
                            "kind": "session",
                            "message_id": "msg_eval_hybrid_user",
                            "content": "hybrid-session-evidence 来自历史对话。",
                        },
                    ],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["memory_count"], 1)
        self.assertEqual(results[0]["actual"]["session_count"], 1)
        self.assertEqual(results[0]["actual"]["missing_memory_ids"], [])
        self.assertEqual(results[0]["actual"]["missing_message_ids"], [])
        self.assertEqual(results[0]["actual"]["missing_source_refs"], [])

    def test_eval_check_executor_evaluates_capability_selection_fallback_trace(self) -> None:
        case = {
            "case_id": "selector_fallback_quality",
            "checks": [
                {
                    "kind": "capability_selection",
                    "name": "Selector chooses healthy fallback",
                    "target": "capability_selection_trace",
                    "required_requested": {"kind": "action", "key": "raw_search"},
                    "required_selected": {"kind": "action", "key": "web_search_backup"},
                    "required_rejected": [
                        {
                            "kind": "action",
                            "key": "raw_search",
                            "reason": "recent_failures_fallback_preferred",
                        }
                    ],
                    "required_fallbacks": [
                        {"kind": "action", "key": "raw_search", "reason": "original_candidate"}
                    ],
                    "min_rejected": 1,
                    "min_fallbacks": 1,
                    "required_terms": ["recent_failures_fallback_preferred"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "capability_selection_trace": {
                    "requested": {"kind": "action", "key": "raw_search"},
                    "selected": {"kind": "action", "key": "web_search_backup"},
                    "rejected_candidates": [
                        {
                            "kind": "action",
                            "key": "raw_search",
                            "reason": "recent_failures_fallback_preferred",
                        }
                    ],
                    "fallback_candidates": [
                        {"kind": "action", "key": "raw_search", "reason": "original_candidate"}
                    ],
                    "score_breakdown": {"selected": {"recent_failure_count": 0}},
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["selected"], {"kind": "action", "key": "web_search_backup"})
        self.assertEqual(results[0]["actual"]["missing_selected"], [])
        self.assertEqual(results[0]["actual"]["missing_rejected"], [])
        self.assertEqual(results[0]["actual"]["missing_fallbacks"], [])

    def test_eval_check_executor_evaluates_scheduler_retry_delivery_report(self) -> None:
        case = {
            "case_id": "scheduler_retry_delivery_quality",
            "checks": [
                {
                    "kind": "scheduler_run",
                    "name": "Scheduler retry and delivery",
                    "target": "scheduler_run_report",
                    "required_job_id": "sched_eval_retry_delivery",
                    "required_job_run_id": "schedrun_eval_retry_delivery_1",
                    "required_run_id": "run_eval_scheduler_failed_1",
                    "required_trigger_reason": "schedule",
                    "required_status": "failed",
                    "required_retry_decision": {
                        "action": "scheduled",
                        "next_attempt_number": 2,
                        "delay_seconds": 300,
                    },
                    "required_pending_retry": {
                        "next_attempt_number": 2,
                        "parent_run_id": "run_eval_scheduler_failed_1",
                    },
                    "required_delivery_result": {
                        "kind": "local_audit",
                        "status": "delivered",
                        "terminal_status": "failed",
                        "run_ref": {"run_id": "run_eval_scheduler_failed_1"},
                    },
                    "required_terms": ["provider timeout", "scheduler_retry_pending"],
                    "forbidden_terms": ["secret-token"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "scheduler_run_report": {
                    "job_id": "sched_eval_retry_delivery",
                    "job_run_id": "schedrun_eval_retry_delivery_1",
                    "run_id": "run_eval_scheduler_failed_1",
                    "trigger_reason": "schedule",
                    "status": "failed",
                    "error": "provider timeout",
                    "retry_decision": {
                        "action": "scheduled",
                        "attempt_number": 1,
                        "next_attempt_number": 2,
                        "max_attempts": 3,
                        "scheduled_for": "2026-05-27T06:10:00Z",
                        "delay_seconds": 300,
                    },
                    "scheduler_retry_pending": {
                        "parent_job_run_id": "schedrun_eval_retry_delivery_1",
                        "parent_run_id": "run_eval_scheduler_failed_1",
                        "next_attempt_number": 2,
                        "scheduled_for": "2026-05-27T06:10:00Z",
                    },
                    "delivery_result": {
                        "kind": "local_audit",
                        "status": "delivered",
                        "terminal_status": "failed",
                        "run_ref": {"kind": "graph_run", "run_id": "run_eval_scheduler_failed_1"},
                        "target": {"kind": "local_audit", "token": "[redacted]"},
                    },
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["missing_retry_decision"], {})
        self.assertEqual(results[0]["actual"]["missing_delivery_result"], {})
        self.assertEqual(results[0]["actual"]["forbidden_terms_found"], [])

    def test_eval_check_executor_fails_scheduler_report_missing_permission_policy(self) -> None:
        case = {
            "case_id": "scheduler_permission_boundary_quality",
            "checks": [
                {
                    "kind": "scheduler_run",
                    "name": "Scheduler permission boundary",
                    "target": "scheduler_run_report",
                    "required_graph_permission_mode": "ask_first",
                    "required_permission_policy": {
                        "approval_required_permission_tiers": ["risky"],
                    },
                    "required_permission_policy_source": "scheduler_default",
                    "required_pending_permission_approval": {
                        "permissions": ["file_write"],
                    },
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={"scheduler_run_report": {"job_id": "sched_eval_permission"}},
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["actual"]["missing_fields"], ["graph_permission_mode", "permission_policy_source"])
        self.assertEqual(
            results[0]["actual"]["missing_permission_policy"],
            {"approval_required_permission_tiers": ["risky"]},
        )
        self.assertEqual(
            results[0]["actual"]["missing_pending_permission_approval"],
            {"permissions": ["file_write"]},
        )

    def test_eval_check_executor_evaluates_delegation_worker_result_package(self) -> None:
        case = {
            "case_id": "delegation_worker_quality",
            "checks": [
                {
                    "kind": "delegation_worker",
                    "name": "Worker result package",
                    "target": "worker_result_package",
                    "required_task_id": "worker_eval_research_1",
                    "required_status": "succeeded",
                    "required_output_keys": ["findings", "source_refs"],
                    "required_source_refs": [
                        {"source_kind": "context_package", "source_id": "ctx_eval_worker_brief"}
                    ],
                    "required_terms": ["TooGraph", "Hermes"],
                    "forbidden_terms": ["unscoped secret"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "worker_result_package": {
                    "kind": "worker_result_package",
                    "task_id": "worker_eval_research_1",
                    "status": "succeeded",
                    "summary": "Compared TooGraph and Hermes worker delegation requirements.",
                    "outputs": {
                        "findings": {
                            "name": "Findings",
                            "type": "markdown",
                            "value": "TooGraph should expose worker_task_packet and worker_result_package.",
                        },
                        "source_refs": {
                            "name": "Source Refs",
                            "type": "json",
                            "value": [{"source_kind": "context_package", "source_id": "ctx_eval_worker_brief"}],
                        },
                    },
                    "source_refs": [
                        {"source_kind": "context_package", "source_id": "ctx_eval_worker_brief"}
                    ],
                    "budget": {"max_steps": 2, "used_steps": 1},
                    "errors": [],
                    "followups": [],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["missing_output_keys"], [])
        self.assertEqual(results[0]["actual"]["missing_source_refs"], [])
        self.assertEqual(results[0]["actual"]["forbidden_terms_found"], [])

    def test_eval_check_executor_evaluates_worker_merge_review_package(self) -> None:
        case = {
            "case_id": "delegation_worker_merge_quality",
            "checks": [
                {
                    "kind": "worker_merge_review",
                    "name": "Worker merge review package",
                    "target": "worker_merge_review_package",
                    "required_status": "partial",
                    "required_output_keys": ["findings"],
                    "required_source_refs": [
                        {"source_kind": "graph_run", "source_id": "run_worker_1"}
                    ],
                    "required_terms": ["retry_failed_workers", "research_1", "research_2"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "worker_merge_review_package": {
                    "kind": "worker_merge_review_package",
                    "status": "partial",
                    "summary": "Merged research_1 and research_2 worker results.",
                    "worker_count": 2,
                    "status_counts": {"failed": 1, "succeeded": 1},
                    "outputs": {
                        "findings": {
                            "name": "Findings",
                            "type": "markdown",
                            "values": [
                                {
                                    "task_id": "research_1",
                                    "status": "succeeded",
                                    "value": "Use worker_task_packet and worker_result_package.",
                                }
                            ],
                        }
                    },
                    "source_refs": [{"source_kind": "graph_run", "source_id": "run_worker_1"}],
                    "review": {
                        "needs_review": True,
                        "risk_flags": ["worker_failed:research_2"],
                        "recommended_next_action": "retry_failed_workers",
                    },
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["missing_output_keys"], [])
        self.assertEqual(results[0]["actual"]["missing_source_refs"], [])

    def test_eval_check_executor_evaluates_provider_fallback_trace(self) -> None:
        case = {
            "case_id": "provider_fallback_quality",
            "checks": [
                {
                    "kind": "provider_fallback",
                    "name": "Provider fallback quality",
                    "target": "provider_fallback_trace",
                    "required_requested": {"provider_id": "openai", "model": "gpt-primary"},
                    "required_selected": {"provider_id": "local", "model": "backup-model"},
                    "required_failed": {"provider_id": "openai", "error_type": "provider_timeout"},
                    "required_capabilities": ["chat", "structured_output"],
                    "required_permissions": ["text_generation"],
                    "min_fallbacks": 1,
                    "required_terms": ["fallback_selected", "provider_timeout"],
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "provider_fallback_trace": {
                    "kind": "provider_fallback_trace",
                    "decision": "fallback_selected",
                    "fallback_used": True,
                    "requested": {"provider_id": "openai", "model": "gpt-primary", "model_ref": "openai/gpt-primary"},
                    "selected": {"provider_id": "local", "model": "backup-model", "model_ref": "local/backup-model"},
                    "failed_candidates": [
                        {
                            "provider_id": "openai",
                            "model": "gpt-primary",
                            "model_ref": "openai/gpt-primary",
                            "error_type": "provider_timeout",
                        }
                    ],
                    "fallback_candidates": [
                        {"provider_id": "local", "model": "backup-model", "model_ref": "local/backup-model"}
                    ],
                    "required_capabilities": ["chat", "structured_output"],
                    "required_permissions": ["text_generation"],
                }
            },
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["score"], 1.0)
        self.assertEqual(results[0]["actual"]["selected"]["model_ref"], "local/backup-model")
        self.assertEqual(results[0]["actual"]["missing_failed"], [])
        self.assertEqual(results[0]["actual"]["missing_capabilities"], [])

    def test_eval_check_executor_reports_knowledge_retrieval_quality_failures(self) -> None:
        case = {
            "case_id": "weak_refund_retrieval",
            "checks": [
                {
                    "kind": "knowledge_retrieval",
                    "name": "Weak retrieval quality",
                    "target": "knowledge_context",
                    "min_results": 2,
                    "required_chunk_ids": ["refund-policy#rules"],
                    "required_citation_ids": ["kb:hybrid-test:1"],
                    "required_source_paths": ["docs/policies/refund.md"],
                    "required_terms": ["Refund audit policy"],
                    "forbidden_terms": ["unverified shortcut"],
                    "max_citations": 1,
                    "max_context_chars": 30,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={
                "knowledge_context": {
                    "context": "Release notes mention an unverified shortcut for dashboards.",
                    "results": [
                        {
                            "citation_id": "kb:hybrid-test:9",
                            "chunk_id": "release-notes#overview",
                            "title": "Release Notes",
                            "source": "docs/releases/may.md",
                            "metadata": {"source_path": "docs/releases/may.md"},
                        }
                    ],
                    "citations": [
                        {"citation_id": "kb:hybrid-test:9"},
                        {"citation_id": "kb:hybrid-test:10"},
                    ],
                }
            },
            artifacts={},
        )

        actual = results[0]["actual"]
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("Expected at least 2 retrieval result", results[0]["message"])
        self.assertEqual(actual["result_count"], 1)
        self.assertEqual(actual["citation_count"], 2)
        self.assertEqual(actual["missing_chunk_ids"], ["refund-policy#rules"])
        self.assertEqual(actual["missing_citation_ids"], ["kb:hybrid-test:1"])
        self.assertEqual(actual["missing_source_paths"], ["docs/policies/refund.md"])
        self.assertEqual(actual["missing_terms"], ["Refund audit policy"])
        self.assertEqual(actual["forbidden_terms_found"], ["unverified shortcut"])
        self.assertGreater(actual["context_chars"], 30)

    def test_eval_check_executor_reports_failed_rule_and_missing_artifact(self) -> None:
        case = {
            "case_id": "unsafe_answer",
            "checks": [
                {"kind": "artifact", "name": "Missing markdown", "target": "final.md"},
                {
                    "kind": "rule",
                    "name": "No certainty",
                    "target": "public_response",
                    "forbidden": ["保证通过"],
                },
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={"public_response": "这份材料保证通过审批。"},
            artifacts={},
        )

        self.assertEqual([result["status"] for result in results], ["failed", "failed"])
        self.assertIn("Missing artifact", results[0]["message"])
        self.assertEqual(results[1]["actual"]["forbidden_found"], ["保证通过"])

    def test_eval_check_executor_skips_llm_judge_without_runner(self) -> None:
        case = {
            "case_id": "policy_answer",
            "checks": [
                {
                    "kind": "llm_judge",
                    "name": "Policy usefulness judge",
                    "rubric": "The answer should cite the policy and identify risks.",
                    "min_score": 0.7,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={"public_response": "Policy answer with [1]."},
            artifacts={},
        )

        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[0]["reviewer"], "llm_judge")
        self.assertIn("not enabled", results[0]["message"])

    def test_eval_check_executor_records_llm_judge_result_from_runner(self) -> None:
        seen: dict[str, object] = {}

        def fake_judge_runner(**kwargs):
            seen.update(kwargs)
            return {
                "status": "failed",
                "score": 0.4,
                "message": "The answer cites a source but does not explain operational risk.",
                "actual": {"verdict": "fail", "reason": "Missing risk explanation."},
                "details": {"model_ref": "test/judge-model", "latency_ms": 12},
            }

        case = {
            "case_id": "policy_answer",
            "expected": {"must_include": ["risk"]},
            "checks": [
                {
                    "kind": "llm_judge",
                    "name": "Risk-aware answer judge",
                    "target": "public_response",
                    "rubric": "Score whether the answer explains concrete operational risk.",
                    "min_score": 0.75,
                }
            ],
        }

        results = evaluate_case_checks(
            case,
            final_output={"public_response": "Policy answer with [1]."},
            artifacts={"final.md": {"path": "backend/data/outputs/run/final.md"}},
            judge_runner=fake_judge_runner,
        )

        self.assertEqual(seen["case"]["case_id"], "policy_answer")
        self.assertEqual(seen["check"]["name"], "Risk-aware answer judge")
        self.assertEqual(seen["final_output"], {"public_response": "Policy answer with [1]."})
        self.assertEqual(results[0]["kind"], "llm_judge")
        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["score"], 0.4)
        self.assertEqual(results[0]["reviewer"], "llm_judge")
        self.assertEqual(results[0]["expected"]["min_score"], 0.75)
        self.assertEqual(results[0]["actual"]["verdict"], "fail")
        self.assertEqual(results[0]["details"]["model_ref"], "test/judge-model")

    def test_llm_judge_runner_skips_when_no_model_is_configured(self) -> None:
        def fail_chat(**_kwargs):
            raise AssertionError("chat should not be called without a model ref")

        result = run_llm_judge(
            case={"case_id": "policy_answer"},
            check={"kind": "llm_judge", "name": "Policy judge"},
            final_output={"public_response": "Answer."},
            artifacts={},
            get_default_text_model_ref_func=lambda **_kwargs: "",
            chat_with_model_ref_with_meta_func=fail_chat,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["details"]["reason"], "missing_model_ref")

    def test_llm_judge_runner_invokes_model_and_parses_structured_judgment(self) -> None:
        seen: dict[str, object] = {}

        def fake_chat(**kwargs):
            seen.update(kwargs)
            return (
                '{"status":"passed","score":0.88,"message":"Useful and grounded.",'
                '"verdict":"pass","reason":"Cites a policy source."}',
                {"provider_id": "test", "model": "judge-model", "request_raw": {"secret": True}},
            )

        result = run_llm_judge(
            case={
                "case_id": "policy_answer",
                "input_values": {"question": "What changed?"},
                "expected": {"must_include": ["risk"]},
            },
            check={
                "kind": "llm_judge",
                "name": "Policy judge",
                "model_ref": "test/judge-model",
                "rubric": "The answer must be grounded and useful.",
            },
            final_output={"public_response": "Answer with [1]."},
            artifacts={},
            get_default_text_model_ref_func=lambda **_kwargs: "",
            chat_with_model_ref_with_meta_func=fake_chat,
        )

        self.assertEqual(seen["model_ref"], "test/judge-model")
        self.assertIn("structured_output_schema", seen)
        self.assertIn('"case_id": "policy_answer"', seen["user_prompt"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["score"], 0.88)
        self.assertEqual(result["actual"]["verdict"], "pass")
        self.assertEqual(result["details"]["model_ref"], "test/judge-model")
        self.assertEqual(result["details"]["model_meta"]["provider_id"], "test")
        self.assertNotIn("request_raw", result["details"]["model_meta"])

    def test_eval_store_records_suite_cases_runs_results_and_checks(self) -> None:
        with isolated_eval_database():
            suite = store.create_eval_suite(
                {
                    "suite_id": "buddy_loop_core",
                    "name": "Buddy loop core",
                    "description": "Core Buddy regression suite.",
                    "target_template_id": "buddy_autonomous_loop",
                    "tags": ["buddy", "capability_loop"],
                    "metadata": {"owner": "product"},
                }
            )
            case = store.create_eval_case(
                "buddy_loop_core",
                {
                    "case_id": "answers_with_citations",
                    "name": "Answers with citations",
                    "input_values": {"input_user_message": "Summarize the cited policy."},
                    "expected": {"must_include": ["citation"]},
                    "checks": [
                        {"kind": "schema", "name": "Final reply schema", "required": ["public_response"]},
                        {"kind": "citation", "name": "Citation present"},
                    ],
                    "metadata": {"priority": "p0"},
                },
            )
            eval_run = store.create_eval_run("buddy_loop_core", requested_by="unit-test", metadata={"reason": "regression"})
            pending_detail = store.load_eval_run(eval_run["eval_run_id"])

            self.assertEqual(suite["suite_id"], "buddy_loop_core")
            self.assertEqual(case["checks"][1]["kind"], "citation")
            self.assertEqual(pending_detail["case_results"][0]["status"], "pending")
            self.assertEqual(pending_detail["case_results"][0]["case_id"], "answers_with_citations")

            result = store.record_eval_case_result(
                eval_run["eval_run_id"],
                "answers_with_citations",
                {
                    "graph_run_id": "run_graph_123",
                    "status": "failed",
                    "final_output": {"public_response": "No citation."},
                    "error": "Missing citation.",
                    "artifacts": {"output_path": "backend/data/outputs/run_graph_123/final.md"},
                    "node_failures": [{"node_id": "citation_check", "error": "No citation ids found."}],
                    "check_results": [
                        {"kind": "schema", "name": "Final reply schema", "status": "passed", "score": 1},
                        {
                            "kind": "citation",
                            "name": "Citation present",
                            "status": "failed",
                            "score": 0,
                            "message": "No citation ids found.",
                            "expected": {"min_citations": 1},
                            "actual": {"citations": []},
                        },
                    ],
                    "human_review": {"reviewer": "qa", "decision": "needs_fix"},
                },
            )
            loaded = store.load_eval_run(eval_run["eval_run_id"])

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["graph_run_id"], "run_graph_123")
            self.assertEqual(result["node_failures"][0]["node_id"], "citation_check")
            self.assertEqual([check["status"] for check in result["check_results"]], ["passed", "failed"])
            self.assertEqual(loaded["status"], "failed")
            self.assertEqual(loaded["case_results"][0]["error"], "Missing citation.")
            self.assertEqual(loaded["case_results"][0]["human_review"]["decision"], "needs_fix")
            self.assertEqual(store.list_eval_suites()[0]["case_count"], 1)

    def test_eval_routes_create_and_report_suite_run_results(self) -> None:
        with isolated_eval_database():
            with TestClient(app) as client:
                suite_response = client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "template_quality",
                        "name": "Template quality",
                        "target_template_id": "policy_navigator_agent",
                        "tags": ["gallery"],
                    },
                )
                case_response = client.post(
                    "/api/evals/suites/template_quality/cases",
                    json={
                        "case_id": "policy_citation",
                        "name": "Policy citation",
                        "input_values": {"policy_text": "Policy text"},
                        "expected": {"citations": 1},
                        "checks": [{"kind": "citation", "name": "Has citation"}],
                    },
                )
                run_response = client.post(
                    "/api/evals/runs",
                    json={"suite_id": "template_quality", "requested_by": "route-test"},
                )
                eval_run_id = run_response.json()["eval_run_id"]
                result_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/policy_citation/result",
                    json={
                        "graph_run_id": "run_policy_1",
                        "status": "passed",
                        "final_output": {"answer": "Includes [1]."},
                        "artifacts": {"citations": ["kb:policy:1"]},
                        "check_results": [
                            {"kind": "citation", "name": "Has citation", "status": "passed", "score": 1}
                        ],
                    },
                )
                suites_response = client.get("/api/evals/suites")
                run_detail_response = client.get(f"/api/evals/runs/{eval_run_id}")

        self.assertEqual(suite_response.status_code, 200)
        self.assertEqual(case_response.status_code, 200)
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(result_response.status_code, 200)
        suites_by_id = {suite["suite_id"]: suite for suite in suites_response.json()}
        self.assertEqual(suites_by_id["template_quality"]["case_count"], 1)
        self.assertEqual(run_detail_response.json()["status"], "passed")
        self.assertEqual(run_detail_response.json()["case_results"][0]["graph_run_id"], "run_policy_1")
        self.assertEqual(run_detail_response.json()["case_results"][0]["check_results"][0]["kind"], "citation")

    def test_eval_routes_list_suite_runs_with_case_results(self) -> None:
        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "listable_suite",
                        "name": "Listable suite",
                        "target_template_id": "policy_navigator_agent",
                    },
                )
                client.post(
                    "/api/evals/suites/listable_suite/cases",
                    json={"case_id": "case_one", "name": "Case one"},
                )
                first_run = client.post("/api/evals/runs", json={"suite_id": "listable_suite"}).json()
                second_run = client.post("/api/evals/runs", json={"suite_id": "listable_suite"}).json()
                client.post(
                    f"/api/evals/runs/{second_run['eval_run_id']}/cases/case_one/result",
                    json={"graph_run_id": "run_case_one", "status": "passed"},
                )

                runs_response = client.get("/api/evals/suites/listable_suite/runs")

        self.assertEqual(runs_response.status_code, 200)
        runs = runs_response.json()
        self.assertEqual([run["eval_run_id"] for run in runs], [second_run["eval_run_id"], first_run["eval_run_id"]])
        self.assertEqual(runs[0]["status"], "passed")
        self.assertEqual(runs[0]["case_results"][0]["graph_run_id"], "run_case_one")

    def test_eval_route_runs_all_cases_for_eval_run(self) -> None:
        def fake_start(_eval_run, case_result, _case, **_kwargs):
            return {"run_id": f"run_{case_result['case_id']}"}

        with isolated_eval_database():
            with (
                patch("app.evaluator.runner.start_eval_case_graph_run", side_effect=fake_start),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "batch_run_suite",
                        "name": "Batch run suite",
                        "target_graph_id": "graph_batch",
                    },
                )
                client.post("/api/evals/suites/batch_run_suite/cases", json={"case_id": "case_one"})
                client.post("/api/evals/suites/batch_run_suite/cases", json={"case_id": "case_two"})
                run_response = client.post("/api/evals/runs", json={"suite_id": "batch_run_suite"})
                eval_run_id = run_response.json()["eval_run_id"]

                batch_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/run")
                run_detail_response = client.get(f"/api/evals/runs/{eval_run_id}")

        self.assertEqual(batch_response.status_code, 200)
        batch = batch_response.json()
        self.assertEqual(batch["started_count"], 2)
        self.assertEqual(batch["skipped_count"], 0)
        self.assertEqual(batch["errors"], [])
        self.assertEqual(
            {result["case_id"]: result["graph_run_id"] for result in batch["results"]},
            {"case_one": "run_case_one", "case_two": "run_case_two"},
        )
        self.assertEqual(run_detail_response.json()["status"], "running")
        self.assertEqual([result["status"] for result in run_detail_response.json()["case_results"]], ["running", "running"])

    def test_eval_route_collects_all_available_case_results(self) -> None:
        def fake_collect(_case, case_result):
            return {
                "graph_run_id": case_result["graph_run_id"],
                "status": "passed",
                "final_output": {"public_response": case_result["case_id"]},
                "artifacts": {},
                "node_failures": [],
                "check_results": [],
            }

        with isolated_eval_database():
            with (
                patch("app.evaluator.collector.collect_eval_case_result_payload", side_effect=fake_collect),
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "batch_collect_suite",
                        "name": "Batch collect suite",
                        "target_graph_id": "graph_batch",
                    },
                )
                client.post("/api/evals/suites/batch_collect_suite/cases", json={"case_id": "case_one"})
                client.post("/api/evals/suites/batch_collect_suite/cases", json={"case_id": "case_two"})
                run_response = client.post("/api/evals/runs", json={"suite_id": "batch_collect_suite"})
                eval_run_id = run_response.json()["eval_run_id"]
                client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/case_one/result",
                    json={"graph_run_id": "run_case_one", "status": "running"},
                )

                batch_response = client.post(f"/api/evals/runs/{eval_run_id}/cases/collect")

        self.assertEqual(batch_response.status_code, 200)
        batch = batch_response.json()
        self.assertEqual(batch["collected_count"], 1)
        self.assertEqual(batch["skipped_count"], 1)
        self.assertEqual(batch["errors"], [])
        self.assertEqual(batch["results"][0]["case_id"], "case_one")
        self.assertEqual(batch["results"][0]["status"], "passed")

    def test_eval_route_evaluates_and_records_case_checks(self) -> None:
        with isolated_eval_database():
            with TestClient(app) as client:
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "policy_quality",
                        "name": "Policy quality",
                        "target_template_id": "policy_navigator_agent",
                    },
                )
                client.post(
                    "/api/evals/suites/policy_quality/cases",
                    json={
                        "case_id": "policy_answer",
                        "name": "Policy answer",
                        "checks": [
                            {
                                "kind": "schema",
                                "name": "Final output fields",
                                "target": "final_output",
                                "required": ["public_response", "citations"],
                            },
                            {"kind": "artifact", "name": "Final artifact", "target": "final.md"},
                            {"kind": "citation", "name": "Citation present", "min_citations": 1},
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "policy_quality"})
                eval_run_id = run_response.json()["eval_run_id"]

                evaluate_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/policy_answer/evaluate",
                    json={
                        "graph_run_id": "run_policy_eval",
                        "final_output": {
                            "public_response": "结论引用 [1]，仍需人工确认。",
                            "citations": ["kb:policy:1"],
                        },
                        "artifacts": {"final.md": {"path": "backend/data/outputs/run_policy_eval/final.md"}},
                    },
                )
                run_detail_response = client.get(f"/api/evals/runs/{eval_run_id}")

        self.assertEqual(evaluate_response.status_code, 200)
        self.assertEqual(evaluate_response.json()["status"], "passed")
        self.assertEqual(
            [check["status"] for check in evaluate_response.json()["check_results"]],
            ["passed", "passed", "passed"],
        )
        self.assertEqual(run_detail_response.json()["status"], "passed")
        self.assertEqual(run_detail_response.json()["case_results"][0]["graph_run_id"], "run_policy_eval")

    def test_eval_route_runs_llm_judge_only_with_explicit_opt_in(self) -> None:
        def fake_create_judge_runner():
            return lambda **_kwargs: {
                "status": "passed",
                "score": 0.91,
                "message": "The response satisfies the rubric.",
                "actual": {"verdict": "pass"},
                "details": {"model_ref": "test/judge-model"},
            }

        with isolated_eval_database():
            with (
                patch("app.api.routes_evals.create_llm_judge_runner", side_effect=fake_create_judge_runner) as create_runner,
                TestClient(app) as client,
            ):
                client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "judge_quality",
                        "name": "Judge quality",
                        "target_template_id": "policy_navigator_agent",
                    },
                )
                client.post(
                    "/api/evals/suites/judge_quality/cases",
                    json={
                        "case_id": "judge_answer",
                        "name": "Judge answer",
                        "checks": [
                            {
                                "kind": "llm_judge",
                                "name": "Rubric judge",
                                "rubric": "The answer must be grounded and useful.",
                                "min_score": 0.8,
                            }
                        ],
                    },
                )
                run_response = client.post("/api/evals/runs", json={"suite_id": "judge_quality"})
                eval_run_id = run_response.json()["eval_run_id"]

                skipped_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/judge_answer/evaluate",
                    json={"final_output": {"public_response": "Grounded answer [1]."}},
                )
                judged_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/judge_answer/evaluate",
                    json={"run_llm_judge": True, "final_output": {"public_response": "Grounded answer [1]."}},
                )

        self.assertEqual(skipped_response.status_code, 200)
        self.assertEqual(skipped_response.json()["status"], "skipped")
        self.assertEqual(skipped_response.json()["check_results"][0]["status"], "skipped")
        self.assertEqual(judged_response.status_code, 200)
        self.assertEqual(judged_response.json()["status"], "passed")
        self.assertEqual(judged_response.json()["check_results"][0]["score"], 0.91)
        self.assertEqual(create_runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
