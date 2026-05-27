from __future__ import annotations

import unittest


class OfficialToolEvalBindingTests(unittest.TestCase):
    def test_official_tools_declare_relevant_eval_suites(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog

        expected_suites = {
            "agent_loop_guard": ["buddy_autonomous_loop_core", "tool_runtime_fallback_eval_core"],
            "buddy_context_pressure_check": ["buddy_autonomous_loop_core", "buddy_context_compaction_core"],
            "buddy_history_context_loader": ["buddy_autonomous_loop_core", "buddy_context_compaction_core"],
            "buddy_home_context_loader": [
                "buddy_autonomous_loop_core",
                "buddy_autonomous_review_core",
                "buddy_context_compaction_core",
            ],
            "buddy_review_context_loader": ["buddy_autonomous_review_core"],
            "capability_context_loader": ["buddy_autonomous_loop_core"],
            "capability_curator_context_loader": ["buddy_capability_curator_core"],
            "delegation_kanban_board_builder": ["delegation_kanban_board_eval_core"],
            "delegation_worker_result_merger": ["delegation_worker_batch_eval_core"],
            "delegation_worker_result_packager": ["delegation_worker_eval_core"],
            "embedding_job_processor": ["embedding_maintenance_core"],
            "embedding_model_registry": ["embedding_maintenance_core"],
            "hybrid_recall_context_loader": ["buddy_hybrid_recall_eval_core"],
            "knowledge_context_loader": ["policy_navigator_agent_lightweight"],
            "memory_search_context_loader": ["buddy_memory_recall_eval_core"],
            "page_context_loader": ["toograph_page_operation_workflow_core"],
            "provider_fallback_resolver": ["provider_fallback_eval_core", "tool_runtime_fallback_eval_core"],
            "runtime_context_loader": ["buddy_autonomous_loop_core"],
            "scheduler_run_context_loader": ["scheduler_retry_delivery_eval_core"],
            "session_search_context_loader": ["buddy_hybrid_recall_eval_core"],
            "video_segmenter": ["game_creative_factory_official", "video_segmenter_eval_core"],
            "web_context_loader": ["advanced_web_research_loop_core"],
        }
        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}

        self.assertEqual(set(catalog), set(expected_suites))
        for tool_key, suites in expected_suites.items():
            with self.subTest(tool_key=tool_key):
                self.assertEqual(catalog[tool_key].verification_eval_suites, suites)


if __name__ == "__main__":
    unittest.main()
