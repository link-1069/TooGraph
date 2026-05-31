from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph_tools.definitions import list_tool_catalog


class ToolCatalogLocalizationTests(unittest.TestCase):
    def test_official_tool_catalog_exposes_localized_manifest_text(self) -> None:
        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog["memory_search_context_loader"]

        self.assertEqual(definition.localized["zh-CN"].name, "记忆搜索上下文加载器")
        self.assertIn("长期记忆", definition.localized["zh-CN"].description)
        self.assertEqual(definition.localized["en-US"].name, "Memory Search Context Loader")
        self.assertIn("long-term memories", definition.localized["en-US"].description)

        serialized = definition.model_dump(by_alias=True)
        self.assertEqual(serialized["localized"]["zh-CN"]["name"], "记忆搜索上下文加载器")


if __name__ == "__main__":
    unittest.main()
