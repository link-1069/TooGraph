from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


SELECTOR_ACTION_DIR = Path(__file__).resolve().parents[2] / "action" / "official" / "toograph_capability_selector"
SELECTOR_AFTER_LLM_PATH = SELECTOR_ACTION_DIR / "after_llm.py"
def _load_selector_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TooGraphCapabilitySelectorActionTests(unittest.TestCase):
    def test_manifest_declares_selection_inputs_and_capability_outputs(self) -> None:
        manifest = json.loads((SELECTOR_ACTION_DIR / "action.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["actionKey"], "toograph_capability_selector")
        self.assertEqual(manifest["timeoutSeconds"], 30)
        self.assertEqual(
            [field["key"] for field in manifest.get("stateInputSchema", [])],
            ["requirement", "capability_candidates", "origin"],
        )
        self.assertEqual(manifest.get("llmOutputSchema", []), [])
        self.assertEqual(
            [field["key"] for field in manifest["stateOutputSchema"]],
            ["capability", "found"],
        )
        self.assertNotIn("audit", [field["key"] for field in manifest["stateOutputSchema"]])

    def test_selector_package_has_no_pre_llm_complexity(self) -> None:
        self.assertFalse((SELECTOR_ACTION_DIR / "before_llm.py").exists())
        self.assertFalse((SELECTOR_ACTION_DIR / "capability_catalog.py").exists())

    def test_after_llm_selects_research_template_for_ai_news(self) -> None:
        selector = _load_selector_module(SELECTOR_AFTER_LLM_PATH, "toograph_capability_selector_after_test")

        result = selector.toograph_capability_selector(
            requirement="帮我整理最新 AI 新闻",
            capability_candidates={
                "templates": [
                    {
                        "kind": "subgraph",
                        "key": "advanced_web_research_loop",
                        "name": "高级联网搜索",
                        "description": "联网研究并整理信息。",
                    },
                    {
                        "kind": "subgraph",
                        "key": "toograph_page_operation_workflow",
                        "name": "操作 TooGraph 页面",
                        "description": "打开页面和操作 UI。",
                    },
                ],
                "actions": [{"kind": "action", "key": "web_search", "name": "联网搜索"}],
            },
        )

        self.assertEqual(result["capability"], {"kind": "subgraph", "key": "advanced_web_research_loop", "name": "高级联网搜索"})
        self.assertTrue(result["found"])

    def test_after_llm_selects_page_operation_only_for_page_requests(self) -> None:
        selector = _load_selector_module(SELECTOR_AFTER_LLM_PATH, "toograph_capability_selector_after_page_test")

        result = selector.toograph_capability_selector(
            requirement="打开知识库页面",
            capability_candidates={
                "templates": [
                    {
                        "kind": "subgraph",
                        "key": "advanced_web_research_loop",
                        "name": "高级联网搜索",
                        "description": "联网研究并整理信息。",
                    },
                    {
                        "kind": "subgraph",
                        "key": "toograph_page_operation_workflow",
                        "name": "操作 TooGraph 页面",
                        "description": "打开页面和操作 UI。",
                    },
                ],
                "actions": [],
            },
        )

        self.assertEqual(
            result["capability"],
            {"kind": "subgraph", "key": "toograph_page_operation_workflow", "name": "操作 TooGraph 页面"},
        )
        self.assertTrue(result["found"])

    def test_after_llm_returns_none_when_no_candidate_matches(self) -> None:
        selector = _load_selector_module(SELECTOR_AFTER_LLM_PATH, "toograph_capability_selector_after_none_test")

        result = selector.toograph_capability_selector(
            requirement="帮我控制咖啡机",
            capability_candidates={"templates": [], "actions": [], "tools": []},
        )

        self.assertEqual(result["capability"]["kind"], "none")
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
