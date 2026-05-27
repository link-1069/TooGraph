from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database
from app.evaluator import store
from app.evaluator.official_seed import seed_official_eval_suites


@contextmanager
def isolated_eval_database():
    old_data_dir = database.DATA_DIR
    old_db_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "toograph.db"
        try:
            yield
        finally:
            database.DATA_DIR = old_data_dir
            database.DB_PATH = old_db_path


class OfficialEvalSeedTests(unittest.TestCase):
    def test_seed_official_eval_suites_covers_core_buddy_web_action_and_business_templates(self) -> None:
        with isolated_eval_database():
            first_summary = seed_official_eval_suites()
            second_summary = seed_official_eval_suites()
            suite_ids = {suite["suite_id"] for suite in store.list_eval_suites()}

            expected_suite_ids = {
                "buddy_autonomous_loop_core",
                "buddy_autonomous_review_core",
                "buddy_capability_curator_core",
                "buddy_context_compaction_core",
                "delegation_kanban_board_eval_core",
                "delegation_worker_batch_eval_core",
                "delegation_worker_eval_core",
                "buddy_hybrid_recall_eval_core",
                "buddy_improvement_review_workflow_core",
                "buddy_memory_recall_eval_core",
                "embedding_maintenance_core",
                "llm_runtime_fallback_eval_core",
                "provider_fallback_eval_core",
                "scheduler_retry_delivery_eval_core",
                "tool_runtime_fallback_eval_core",
                "video_segmenter_eval_core",
                "workspace_executor_eval_core",
                "toograph_page_operation_workflow_core",
                "toograph_action_creation_workflow_core",
                "toograph_graph_template_creation_workflow_core",
                "advanced_web_research_loop_core",
                "policy_navigator_agent_lightweight",
            }
            self.assertTrue(expected_suite_ids.issubset(suite_ids))

            buddy_case = store.load_eval_case("buddy_autonomous_loop_core", "buddy-main-loop-clarifies-ambiguous-request")
            selector_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-selector-fallback-after-recent-failures",
            )
            buddy_live_fallback_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-recovers-from-live-tool-failure-with-fallback",
            )
            buddy_provider_fallback_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-recovers-from-provider-model-fallback",
            )
            buddy_subgraph_fallback_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-recovers-from-subgraph-failure-with-fallback",
            )
            buddy_permission_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-pauses-for-action-permission-required",
            )
            buddy_context_overflow_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-compacts-context-overflow-before-reply",
            )
            buddy_context_overflow_tool_combo_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-compacts-context-overflow-then-recovers-from-tool-failure",
            )
            buddy_context_overflow_subgraph_combo_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-compacts-context-overflow-then-recovers-from-subgraph-failure",
            )
            buddy_context_overflow_permission_combo_case = store.load_eval_case(
                "buddy_autonomous_loop_core",
                "buddy-main-loop-compacts-context-overflow-then-pauses-for-action-permission-required",
            )
            review_case = store.load_eval_case(
                "buddy_autonomous_review_core",
                "background-review-source-run-produces-review-artifacts",
            )
            compaction_case = store.load_eval_case(
                "buddy_context_compaction_core",
                "context-compaction-protects-recent-history",
            )
            embedding_case = store.load_eval_case(
                "embedding_maintenance_core",
                "embedding-maintenance-empty-queue-reports-counts",
            )
            curator_case = store.load_eval_case(
                "buddy_capability_curator_core",
                "capability-curator-reports-health-and-candidates",
            )
            improvement_case = store.load_eval_case(
                "buddy_improvement_review_workflow_core",
                "improvement-review-requires-approval-for-template-change",
            )
            recall_case = store.load_eval_case(
                "buddy_memory_recall_eval_core",
                "memory-recall-finds-fixture-memory-with-source-refs",
            )
            memory_rerank_case = store.load_eval_case(
                "buddy_memory_recall_eval_core",
                "memory-recall-rerank-promotes-most-relevant-memory",
            )
            scheduler_case = store.load_eval_case(
                "scheduler_retry_delivery_eval_core",
                "scheduler-run-records-retry-and-delivery",
            )
            delegation_case = store.load_eval_case(
                "delegation_worker_eval_core",
                "delegation-worker-packages-task-result",
            )
            delegation_batch_case = store.load_eval_case(
                "delegation_worker_batch_eval_core",
                "delegation-worker-batch-merges-subgraph-results",
            )
            delegation_board_case = store.load_eval_case(
                "delegation_kanban_board_eval_core",
                "delegation-kanban-board-projects-worker-state",
            )
            hybrid_recall_case = store.load_eval_case(
                "buddy_hybrid_recall_eval_core",
                "hybrid-recall-finds-session-and-memory-fixtures",
            )
            provider_fallback_case = store.load_eval_case(
                "provider_fallback_eval_core",
                "provider-fallback-selects-compatible-model",
            )
            tool_runtime_fallback_case = store.load_eval_case(
                "tool_runtime_fallback_eval_core",
                "tool-runtime-fallback-routes-to-fallback-tool",
            )
            workspace_executor_case = store.load_eval_case(
                "workspace_executor_eval_core",
                "workspace-executor-searches-roadmap-through-action",
            )
            video_segmenter_case = store.load_eval_case(
                "video_segmenter_eval_core",
                "video-segmenter-splits-fixture-video-through-tool",
            )
            graph_template_case = store.load_eval_case(
                "toograph_graph_template_creation_workflow_core",
                "graph-template-creation-requires-user-template-write-and-validation",
            )
            action_case = store.load_eval_case("toograph_action_creation_workflow_core", "action-creation-clarifies-unsafe-write")
            policy_case = store.load_eval_case(
                "policy_navigator_agent_lightweight",
                "policy-navigator-mock-housing-subsidy",
            )

        self.assertGreaterEqual(first_summary["suite_count"], 12)
        self.assertEqual(second_summary["created_or_updated_case_count"], first_summary["created_or_updated_case_count"])
        self.assertEqual(buddy_case["input_values"]["user_message"], "帮我优化当前图，让它以后能自动改自己。")
        self.assertEqual(buddy_case["checks"][0]["kind"], "schema")
        self.assertEqual(buddy_case["checks"][1]["kind"], "llm_judge")
        self.assertEqual(buddy_case["checks"][1]["details"]["original_kind"], "rule")
        selector_graph_run_check = next(check for check in selector_case["checks"] if check["kind"] == "graph_run")
        selector_selection_check = next(check for check in selector_case["checks"] if check["kind"] == "capability_selection")
        self.assertEqual(
            selector_graph_run_check["required_metadata"]["eval"]["target_template_id"],
            "buddy_autonomous_loop",
        )
        self.assertEqual(selector_selection_check["required_selected"], {"kind": "action", "key": "web_search"})
        self.assertEqual(
            selector_case["metadata"]["fixture_capability_usage_entries"][0]["capability"]["key"],
            "advanced_web_research_loop",
        )
        self.assertEqual(buddy_live_fallback_case["metadata"]["fixture_agent_model_ref"], "eval-primary/gpt-primary")
        live_fallback_graph_run_check = next(
            check for check in buddy_live_fallback_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "provider_fallback_resolver",
                "status": "failed",
                "error_type": "eval_tool_timeout",
            },
            live_fallback_graph_run_check["required_tool_invocations"],
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "runtime_context_loader",
                "status": "succeeded",
            },
            live_fallback_graph_run_check["required_tool_invocations"],
        )
        self.assertEqual(
            buddy_provider_fallback_case["metadata"]["fixture_model_runtime"]["failures"]["eval-primary/gpt-primary"][
                "error_type"
            ],
            "provider_timeout",
        )
        provider_fallback_check = next(
            check for check in buddy_provider_fallback_case["checks"] if check["kind"] == "provider_fallback"
        )
        self.assertEqual(
            provider_fallback_check["required_selected"],
            {"provider_id": "eval-fallback", "model": "gpt-fallback"},
        )
        self.assertEqual(
            provider_fallback_check["required_requested"],
            {"provider_id": "eval-primary", "model": "gpt-primary"},
        )
        subgraph_graph_run_check = next(
            check for check in buddy_subgraph_fallback_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "subgraph_key": "advanced_web_research_loop",
                "status": "failed",
                "error_type": "missing_required_input",
            },
            subgraph_graph_run_check["required_subgraph_invocations"],
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "runtime_context_loader",
                "status": "succeeded",
            },
            subgraph_graph_run_check["required_tool_invocations"],
        )
        permission_graph_run_check = next(
            check for check in buddy_permission_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            buddy_permission_case["metadata"]["fixture_graph_metadata"]["capability_permission_policy"],
            {"approval_required_permission_tiers": ["risky"]},
        )
        self.assertEqual(permission_graph_run_check["required_status"], "awaiting_human")
        self.assertEqual(
            permission_graph_run_check["required_metadata"]["pending_permission_approval"]["capability_key"],
            "local_workspace_executor",
        )
        self.assertEqual(
            permission_graph_run_check["required_metadata"]["pending_permission_approval"]["permissions"],
            ["file_write"],
        )
        context_overflow_graph_run_check = next(
            check for check in buddy_context_overflow_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            buddy_context_overflow_case["metadata"]["fixture_graph_metadata"]["runtime_context"],
            {
                "buddy_session_id": "session_eval_context_overflow",
                "buddy_current_message_id": "msg_eval_context_overflow_current",
            },
        )
        self.assertEqual(
            buddy_context_overflow_case["metadata"]["fixture_buddy_sessions"][0]["session_id"],
            "session_eval_context_overflow",
        )
        self.assertIn("run_context_compaction", context_overflow_graph_run_check["required_node_ids"])
        self.assertIn("context_compaction_report", context_overflow_graph_run_check["required_state_keys"])
        self.assertIn(
            {
                "node_id": "check_context_pressure",
                "tool_key": "buddy_context_pressure_check",
                "status": "succeeded",
            },
            context_overflow_graph_run_check["required_tool_invocations"],
        )
        combo_graph_run_check = next(
            check for check in buddy_context_overflow_tool_combo_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            buddy_context_overflow_tool_combo_case["metadata"]["fixture_graph_metadata"]["runtime_context"],
            {
                "buddy_session_id": "session_eval_context_overflow_tool_combo",
                "buddy_current_message_id": "msg_eval_context_overflow_tool_combo_current",
            },
        )
        self.assertEqual(
            buddy_context_overflow_tool_combo_case["metadata"]["fixture_buddy_sessions"][0]["session_id"],
            "session_eval_context_overflow_tool_combo",
        )
        self.assertIn("fixture_tool_runtime", buddy_context_overflow_tool_combo_case["metadata"])
        self.assertIn("run_context_compaction", combo_graph_run_check["required_node_ids"])
        self.assertIn("execute_capability", combo_graph_run_check["required_node_ids"])
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "provider_fallback_resolver",
                "status": "failed",
                "error_type": "eval_tool_timeout",
            },
            combo_graph_run_check["required_tool_invocations"],
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "runtime_context_loader",
                "status": "succeeded",
            },
            combo_graph_run_check["required_tool_invocations"],
        )
        combo_subgraph_graph_run_check = next(
            check for check in buddy_context_overflow_subgraph_combo_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            buddy_context_overflow_subgraph_combo_case["metadata"]["fixture_graph_metadata"]["runtime_context"],
            {
                "buddy_session_id": "session_eval_context_overflow_subgraph_combo",
                "buddy_current_message_id": "msg_eval_context_overflow_subgraph_combo_current",
            },
        )
        self.assertEqual(
            buddy_context_overflow_subgraph_combo_case["metadata"]["fixture_buddy_sessions"][0]["session_id"],
            "session_eval_context_overflow_subgraph_combo",
        )
        self.assertIn("fixture_tool_runtime", buddy_context_overflow_subgraph_combo_case["metadata"])
        self.assertIn("run_context_compaction", combo_subgraph_graph_run_check["required_node_ids"])
        self.assertIn("execute_capability", combo_subgraph_graph_run_check["required_node_ids"])
        self.assertIn(
            {
                "node_id": "execute_capability",
                "subgraph_key": "advanced_web_research_loop",
                "status": "failed",
                "error_type": "missing_required_input",
            },
            combo_subgraph_graph_run_check["required_subgraph_invocations"],
        )
        self.assertIn(
            {
                "node_id": "execute_capability",
                "tool_key": "runtime_context_loader",
                "status": "succeeded",
            },
            combo_subgraph_graph_run_check["required_tool_invocations"],
        )
        combo_permission_graph_run_check = next(
            check for check in buddy_context_overflow_permission_combo_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            buddy_context_overflow_permission_combo_case["metadata"]["fixture_graph_metadata"]["runtime_context"],
            {
                "buddy_session_id": "session_eval_context_overflow_permission_combo",
                "buddy_current_message_id": "msg_eval_context_overflow_permission_combo_current",
            },
        )
        self.assertEqual(
            buddy_context_overflow_permission_combo_case["metadata"]["fixture_graph_metadata"]["graph_permission_mode"],
            "ask_first",
        )
        self.assertEqual(
            buddy_context_overflow_permission_combo_case["metadata"]["fixture_buddy_sessions"][0]["session_id"],
            "session_eval_context_overflow_permission_combo",
        )
        self.assertEqual(combo_permission_graph_run_check["required_status"], "awaiting_human")
        self.assertIn("run_context_compaction", combo_permission_graph_run_check["required_node_ids"])
        self.assertIn("execute_capability", combo_permission_graph_run_check["required_node_ids"])
        self.assertEqual(
            combo_permission_graph_run_check["required_metadata"]["pending_permission_approval"]["capability_key"],
            "local_workspace_executor",
        )
        self.assertEqual(
            combo_permission_graph_run_check["required_metadata"]["pending_permission_approval"]["permissions"],
            ["file_write"],
        )
        self.assertEqual(review_case["metadata"]["fixture_runs"][0]["run_id"], "run_eval_buddy_review_source")
        self.assertEqual(compaction_case["input_values"]["current_session_id"], "session_eval_compaction")
        self.assertEqual(embedding_case["checks"][0]["kind"], "schema")
        self.assertEqual(curator_case["checks"][1]["kind"], "llm_judge")
        self.assertEqual(improvement_case["input_values"]["source_run_id"], "run_eval_improvement_source")
        self.assertEqual(recall_case["checks"][0]["kind"], "memory_retrieval")
        self.assertEqual(
            recall_case["metadata"]["fixture_memory_entries"][0]["memory_id"],
            "mem_eval_recall_preference",
        )
        self.assertEqual(memory_rerank_case["input_values"]["reranker_model_ref"], "local-rerank/bge-reranker-v2")
        self.assertEqual(memory_rerank_case["checks"][0]["kind"], "memory_retrieval")
        self.assertEqual(memory_rerank_case["checks"][0]["required_top_memory_id"], "mem_eval_rerank_precise")
        self.assertEqual(scheduler_case["checks"][0]["kind"], "scheduler_run")
        self.assertEqual(
            scheduler_case["metadata"]["fixture_scheduled_graph_jobs"][0]["job_id"],
            "sched_eval_retry_delivery",
        )
        self.assertEqual(
            scheduler_case["checks"][0]["required_graph_permission_mode"],
            "ask_first",
        )
        self.assertEqual(
            scheduler_case["checks"][0]["required_permission_policy"],
            {"approval_required_permission_tiers": ["risky"]},
        )
        self.assertEqual(
            scheduler_case["metadata"]["fixture_runs"][0]["metadata"]["capability_permission_policy"][
                "approval_required_permission_tiers"
            ],
            ["risky"],
        )
        delegation_worker_check = next(check for check in delegation_case["checks"] if check["kind"] == "delegation_worker")
        delegation_graph_run_check = next(check for check in delegation_case["checks"] if check["kind"] == "graph_run")
        self.assertEqual(delegation_worker_check["target"], "worker_result_package")
        self.assertEqual(delegation_graph_run_check["required_metadata"]["eval"]["target_template_id"], "delegation_worker_eval")
        self.assertEqual(delegation_case["input_values"]["worker_task_packet"]["task_id"], "worker_eval_research_1")
        delegation_batch_check = next(
            check for check in delegation_batch_case["checks"] if check["kind"] == "worker_merge_review"
        )
        delegation_batch_graph_run_check = next(
            check for check in delegation_batch_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            delegation_batch_graph_run_check["required_metadata"]["eval"]["target_template_id"],
            "delegation_worker_batch_eval",
        )
        self.assertEqual(delegation_batch_check["target"], "worker_merge_review_package")
        self.assertEqual(delegation_batch_case["input_values"]["worker_statuses"], ["succeeded", "failed"])
        self.assertEqual(delegation_batch_case["input_values"]["worker_budget_usages"][1]["used_steps"], 3)
        self.assertIn("worker_budget_exhausted", delegation_batch_check["required_terms"])
        self.assertEqual(delegation_board_case["checks"][0]["kind"], "schema")
        self.assertEqual(delegation_board_case["checks"][0]["target"], "delegation_board_snapshot")
        self.assertIn("columns.blocked", delegation_board_case["checks"][0]["required"])
        self.assertEqual(hybrid_recall_case["checks"][0]["kind"], "hybrid_recall")
        self.assertIn(
            "session_eval_hybrid_history",
            [fixture["session_id"] for fixture in hybrid_recall_case["metadata"]["fixture_buddy_sessions"]],
        )
        provider_graph_run_check = next(check for check in provider_fallback_case["checks"] if check["kind"] == "graph_run")
        provider_fallback_check = next(
            check for check in provider_fallback_case["checks"] if check["kind"] == "provider_fallback"
        )
        self.assertEqual(provider_graph_run_check["required_metadata"]["eval"]["target_template_id"], "provider_fallback_eval")
        self.assertEqual(provider_fallback_check["required_selected"], {"provider_id": "local", "model": "backup-model"})
        self.assertEqual(provider_fallback_case["input_values"]["requested_model_ref"], "openai/gpt-primary")
        tool_runtime_graph_run_check = next(
            check for check in tool_runtime_fallback_case["checks"] if check["kind"] == "graph_run"
        )
        self.assertEqual(
            tool_runtime_graph_run_check["required_tool_invocations"][0]["error_type"],
            "eval_tool_timeout",
        )
        self.assertEqual(
            tool_runtime_fallback_case["metadata"]["fixture_tool_runtime"]["responses"]["fallback_guard_tool"][
                "tool_key"
            ],
            "agent_loop_guard",
        )
        workspace_graph_run_check = next(check for check in workspace_executor_case["checks"] if check["kind"] == "graph_run")
        self.assertEqual(
            workspace_graph_run_check["required_action_invocations"][0]["action_key"],
            "local_workspace_executor",
        )
        self.assertEqual(
            workspace_executor_case["metadata"]["fixture_model_runtime"]["responses"]["eval-primary/gpt-primary"][
                "meta"
            ]["response_id"],
            "workspace-action-fixture",
        )
        video_graph_run_check = next(check for check in video_segmenter_case["checks"] if check["kind"] == "graph_run")
        self.assertEqual(video_graph_run_check["required_tool_invocations"][0]["tool_key"], "video_segmenter")
        self.assertEqual(
            video_segmenter_case["metadata"]["fixture_video_files"][0]["state_key"],
            "source_video",
        )
        graph_template_graph_run_check = next(check for check in graph_template_case["checks"] if check["kind"] == "graph_run")
        self.assertEqual(
            [item["action_key"] for item in graph_template_graph_run_check["required_action_invocations"]],
            [
                "toograph_graph_template_reader",
                "toograph_graph_template_validator",
                "toograph_graph_template_writer",
            ],
        )
        self.assertEqual(graph_template_case["metadata"]["fixture_agent_model_ref"], "eval-primary/gpt-primary")
        self.assertTrue(graph_template_case["metadata"]["fixture_graph_template_workspace"])
        self.assertEqual(action_case["metadata"]["template_id"], "toograph_action_creation_workflow")
        self.assertIn("policy_sources", policy_case["input_values"])
        self.assertEqual(policy_case["checks"][0]["kind"], "llm_judge")
        self.assertEqual(policy_case["checks"][0]["details"]["original_kind"], "schema")

    def test_seed_official_eval_suites_keeps_executable_knowledge_retrieval_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "rag_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "rag_quality_template",
                  "label": "RAG Quality Template",
                  "description": "Fixture template for RAG eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "rag_quality_template_official",
                  "cases": [
                    {
                      "case_id": "refund-retrieval-quality",
                      "checks": [
                        {
                          "kind": "knowledge_retrieval",
                          "target": "knowledge_context",
                          "min_results": 1,
                          "required_chunk_ids": ["refund-policy#rules"],
                          "required_terms": ["refund"]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("rag_quality_template_official", "refund-retrieval-quality")

        self.assertEqual(case["checks"][0]["kind"], "knowledge_retrieval")
        self.assertEqual(case["checks"][0]["required_chunk_ids"], ["refund-policy#rules"])

    def test_seed_official_eval_suites_keeps_executable_capability_selection_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "selector_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "selector_quality_template",
                  "label": "Selector Quality Template",
                  "description": "Fixture template for capability selector eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "selector_quality_template_official",
                  "cases": [
                    {
                      "case_id": "selector-fallback-quality",
                      "checks": [
                        {
                          "kind": "capability_selection",
                          "target": "capability_selection_trace",
                          "required_selected": {"kind": "action", "key": "web_search_backup"},
                          "required_rejected": [
                            {
                              "kind": "action",
                              "key": "raw_search",
                              "reason": "recent_failures_fallback_preferred"
                            }
                          ]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("selector_quality_template_official", "selector-fallback-quality")

        self.assertEqual(case["checks"][0]["kind"], "capability_selection")
        self.assertEqual(case["checks"][0]["required_selected"], {"kind": "action", "key": "web_search_backup"})

    def test_seed_official_eval_suites_keeps_executable_graph_run_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "graph_run_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "graph_run_quality_template",
                  "label": "Graph Run Quality Template",
                  "description": "Fixture template for graph run eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "graph_run_quality_template_official",
                  "cases": [
                    {
                      "case_id": "graph-run-contract",
                      "checks": [
                        {
                          "kind": "graph_run",
                          "target": "graph_run",
                          "required_status": "completed",
                          "required_template_id": "graph_run_quality_template",
                          "required_state_keys": ["public_response"],
                          "required_node_ids": ["reply"],
                          "min_node_executions": 1
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("graph_run_quality_template_official", "graph-run-contract")

        self.assertEqual(case["checks"][0]["kind"], "graph_run")
        self.assertEqual(case["checks"][0]["required_template_id"], "graph_run_quality_template")
        self.assertEqual(case["checks"][0]["required_state_keys"], ["public_response"])

    def test_seed_official_eval_suites_keeps_executable_scheduler_run_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "scheduler_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "scheduler_quality_template",
                  "label": "Scheduler Quality Template",
                  "description": "Fixture template for scheduler eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "scheduler_quality_template_official",
                  "cases": [
                    {
                      "case_id": "scheduler-retry-delivery-quality",
                      "checks": [
                        {
                          "kind": "scheduler_run",
                          "target": "scheduler_run_report",
                          "required_job_id": "sched_eval_retry_delivery",
                          "required_retry_decision": {"action": "scheduled"},
                          "required_delivery_result": {"status": "delivered"}
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("scheduler_quality_template_official", "scheduler-retry-delivery-quality")

        self.assertEqual(case["checks"][0]["kind"], "scheduler_run")
        self.assertEqual(case["checks"][0]["required_job_id"], "sched_eval_retry_delivery")

    def test_seed_official_eval_suites_keeps_executable_delegation_worker_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "delegation_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "delegation_quality_template",
                  "label": "Delegation Quality Template",
                  "description": "Fixture template for delegation worker eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "delegation_quality_template_official",
                  "cases": [
                    {
                      "case_id": "delegation-worker-quality",
                      "checks": [
                        {
                          "kind": "delegation_worker",
                          "target": "worker_result_package",
                          "required_task_id": "worker_eval_research_1",
                          "required_status": "succeeded",
                          "required_output_keys": ["findings"]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("delegation_quality_template_official", "delegation-worker-quality")

        self.assertEqual(case["checks"][0]["kind"], "delegation_worker")
        self.assertEqual(case["checks"][0]["required_task_id"], "worker_eval_research_1")

    def test_seed_official_eval_suites_keeps_executable_worker_merge_review_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "delegation_merge_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "delegation_merge_quality_template",
                  "label": "Delegation Merge Quality Template",
                  "description": "Fixture template for delegation merge eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "delegation_merge_quality_template_official",
                  "cases": [
                    {
                      "case_id": "delegation-worker-merge-quality",
                      "checks": [
                        {
                          "kind": "worker_merge_review",
                          "target": "worker_merge_review_package",
                          "required_status": "partial",
                          "required_output_keys": ["findings"]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case(
                "delegation_merge_quality_template_official",
                "delegation-worker-merge-quality",
            )

        self.assertEqual(case["checks"][0]["kind"], "worker_merge_review")
        self.assertEqual(case["checks"][0]["target"], "worker_merge_review_package")

    def test_seed_official_eval_suites_keeps_executable_hybrid_recall_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "hybrid_recall_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "hybrid_recall_quality_template",
                  "label": "Hybrid Recall Quality Template",
                  "description": "Fixture template for hybrid recall eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "hybrid_recall_quality_template_official",
                  "cases": [
                    {
                      "case_id": "hybrid-recall-quality",
                      "checks": [
                        {
                          "kind": "hybrid_recall",
                          "target": "hybrid_recall_report",
                          "min_memory_results": 1,
                          "min_session_results": 1,
                          "required_memory_ids": ["mem_eval_hybrid_preference"],
                          "required_message_ids": ["msg_eval_hybrid_user"]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("hybrid_recall_quality_template_official", "hybrid-recall-quality")

        self.assertEqual(case["checks"][0]["kind"], "hybrid_recall")
        self.assertEqual(case["checks"][0]["required_message_ids"], ["msg_eval_hybrid_user"])

    def test_seed_official_eval_suites_keeps_executable_provider_fallback_checks(self) -> None:
        with isolated_eval_database(), tempfile.TemporaryDirectory() as temp_dir:
            template_root = Path(temp_dir) / "official"
            template_dir = template_root / "provider_fallback_quality_template"
            template_dir.mkdir(parents=True)
            (template_dir / "template.json").write_text(
                """
                {
                  "template_id": "provider_fallback_quality_template",
                  "label": "Provider Fallback Quality Template",
                  "description": "Fixture template for provider fallback eval checks.",
                  "metadata": {"category": "test"}
                }
                """,
                encoding="utf-8",
            )
            (template_dir / "eval_cases.json").write_text(
                """
                {
                  "suite_id": "provider_fallback_quality_template_official",
                  "cases": [
                    {
                      "case_id": "provider-fallback-quality",
                      "checks": [
                        {
                          "kind": "provider_fallback",
                          "target": "provider_fallback_trace",
                          "required_requested": {"provider_id": "openai", "model": "gpt-primary"},
                          "required_selected": {"provider_id": "local", "model": "backup-model"},
                          "required_failed": {"provider_id": "openai", "error_type": "provider_timeout"},
                          "required_capabilities": ["chat", "structured_output"],
                          "required_permissions": ["text_generation"],
                          "min_fallbacks": 1
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            seed_official_eval_suites(template_root)
            case = store.load_eval_case("provider_fallback_quality_template_official", "provider-fallback-quality")

        self.assertEqual(case["checks"][0]["kind"], "provider_fallback")
        self.assertEqual(case["checks"][0]["required_selected"]["model"], "backup-model")


if __name__ == "__main__":
    unittest.main()
