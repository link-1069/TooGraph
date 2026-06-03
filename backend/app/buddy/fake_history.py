from __future__ import annotations

from dataclasses import dataclass
import random
import re
import sqlite3
from typing import Any

from app.buddy import store
from app.core.storage.database import get_connection


SYNTHETIC_SESSION_SOURCE = "synthetic_buddy_history"


@dataclass(frozen=True)
class FakeHistoryOptions:
    batch_id: str = "embedding_seed"
    session_count: int = 40
    min_turns: int = 6
    max_turns: int = 12
    seed: int = 3488


_TOPICS: list[dict[str, Any]] = [
    {
        "key": "embedding_architecture",
        "title": "Embedding 架构梳理",
        "user_goals": [
            "我想把记忆召回和知识库检索放到同一套底座里，但又不想混淆来源。",
            "帮我判断 session summary 是不是应该参与 embedding。",
            "我需要确认 chunk、document、source package 之间的关系。",
        ],
        "assistant_actions": [
            "我会把事实源、索引层和语义记忆层拆开看，先确认边界再谈实现。",
            "这里应该让 session summary 成为 retrieval source，但它仍然只是上下文摘要，不是长期记忆。",
            "可以把 document 理解为可检索文档，chunk 是其中最小的可召回文本块。",
        ],
    },
    {
        "key": "buddy_memory",
        "title": "Buddy 记忆复盘",
        "user_goals": [
            "我不想每轮对话都复盘，担心会产生很多低质量记忆。",
            "如果我明确说以后都这样回复，应该马上写入长期记忆吗？",
            "后台复盘应该能区分 USER.md、MEMORY.md 和结构化 memory entry。",
        ],
        "assistant_actions": [
            "低信号对话可以只记录 skipped audit，高信号或周期触发时再跑完整复盘图。",
            "明确的长期偏好可以进入低风险写回，但仍然要留下 evidence 和 revision。",
            "USER.md 更适合稳定协作偏好，MEMORY.md 更适合长期项目事实和决策。",
        ],
    },
    {
        "key": "knowledge_document",
        "title": "知识库入库",
        "user_goals": [
            "如果我给一个文件夹，里面有很多 Markdown、PDF 和聊天导出，应该怎么入库？",
            "知识库 chunk 和记忆 chunk 我觉得应该分开，避免后面召回混乱。",
            "我想知道文件变更后是不是需要重新生成所有 embedding。",
        ],
        "assistant_actions": [
            "文件夹应该先变成 local_folder source package，再由 ingestion 图解析和切分。",
            "事实源应该分开，统一 retrieval 索引层用 source_kind、authority 和 scope 隔离。",
            "只要 content_hash 没变，就不需要重新生成同模型 embedding。",
        ],
    },
    {
        "key": "model_provider",
        "title": "模型供应商配置",
        "user_goals": [
            "本地 embedding 模型应该放在 Model Providers 页面里吗？",
            "LM Studio 里发现的 embedding 模型不要被误选成聊天模型。",
            "我希望默认检索 embedding 模型能同时用于记忆和知识库。",
        ],
        "assistant_actions": [
            "Provider 管连接和凭据，Model 管 chat、embedding、rerank 等能力。",
            "模型能力识别可以自动推断，但必须允许用户手动覆盖。",
            "第一版可以用一个默认 retrieval embedding，后面再分 memory 和 knowledge 策略。",
        ],
    },
    {
        "key": "graph_templates",
        "title": "图模板表达",
        "user_goals": [
            "整个 ingestion 到 retrieval 的流程能不能用图模板表达？",
            "一个 LLM 节点是不是只能选择一个 Action 或 capability？",
            "我想让 Buddy 的召回阶段在回复前显式发生，而不是藏在能力选择里。",
        ],
        "assistant_actions": [
            "图模板可以表达 ingestion、retrieval query、compaction 和 background review 四条链路。",
            "一个 LLM 节点只准备一次 capability 输入，多个能力调用应该用多个节点和边表达。",
            "回复前可以加入 recall planner，再把检索结果作为 context package 输入主回复节点。",
        ],
    },
    {
        "key": "product_quality",
        "title": "产品体验与可审计性",
        "user_goals": [
            "用户应该能看到哪些内容被入库、哪些被召回、哪些被跳过。",
            "我想在 Run Detail 里看到 retrieval ranking report。",
            "自动写入记忆必须可以回滚，不然我不放心。",
        ],
        "assistant_actions": [
            "UI 应展示 source、document、chunk、embedding job、query audit 和 revision。",
            "Run Detail 可以展示 query、filters、score、source refs、budget 和 omitted reason。",
            "所有自动写入都应该走 command/revision 路径，并保留旧值恢复能力。",
        ],
    },
]

_PREFERENCE_SIGNALS = [
    "以后回答这类架构问题，先给结论，再给表结构或流程图。",
    "我更喜欢中文术语，但保留关键英文名，比如 chunk、embedding、retrieval。",
    "如果只是文档改动，不需要每次都启动项目。",
    "不要把一次性任务状态写成长期记忆。",
    "涉及本地数据写入时，先说明会写到哪里。",
]


def build_fake_history_dataset(options: FakeHistoryOptions | None = None) -> list[dict[str, Any]]:
    normalized = _normalize_options(options)
    rng = random.Random(normalized.seed)
    sessions: list[dict[str, Any]] = []
    topic_cycle = list(_TOPICS)
    rng.shuffle(topic_cycle)

    for session_index in range(1, normalized.session_count + 1):
        topic = topic_cycle[(session_index - 1) % len(topic_cycle)]
        turn_count = rng.randint(normalized.min_turns, normalized.max_turns)
        session_id = f"synthetic_{_slug(normalized.batch_id)}_s{session_index:04d}"
        messages: list[dict[str, Any]] = []
        for turn_index in range(1, turn_count + 1):
            user_content = _build_user_message(rng, topic, turn_index)
            assistant_content = _build_assistant_message(rng, topic, turn_index)
            base_metadata = {
                "synthetic": True,
                "synthetic_batch_id": normalized.batch_id,
                "synthetic_topic": topic["key"],
                "synthetic_session_index": session_index,
                "synthetic_turn_index": turn_index,
            }
            messages.append(
                {
                    "message_id": f"{session_id}_m{len(messages) + 1:04d}",
                    "role": "user",
                    "content": user_content,
                    "metadata": {**base_metadata, "synthetic_role": "user"},
                    "include_in_context": True,
                }
            )
            messages.append(
                {
                    "message_id": f"{session_id}_m{len(messages) + 1:04d}",
                    "role": "assistant",
                    "content": assistant_content,
                    "metadata": {**base_metadata, "synthetic_role": "assistant"},
                    "include_in_context": True,
                }
            )
        sessions.append(
            {
                "session_id": session_id,
                "title": f"[synthetic] {topic['title']} {session_index:04d}",
                "source": SYNTHETIC_SESSION_SOURCE,
                "topic": topic["key"],
                "messages": messages,
            }
        )
    return sessions


def seed_fake_history(options: FakeHistoryOptions | None = None) -> dict[str, Any]:
    dataset = build_fake_history_dataset(options)
    created_session_ids: list[str] = []
    created_message_ids: list[str] = []
    for session in dataset:
        try:
            store.create_chat_session(
                {
                    "session_id": session["session_id"],
                    "title": session["title"],
                    "source": session["source"],
                },
                changed_by="synthetic_history_seed",
                change_reason="生成 embedding 与 retrieval 测试用历史聊天记录。",
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Synthetic session already exists: {session['session_id']}. "
                "Use a different batch_id for a new fixture batch."
            ) from exc
        created_session_ids.append(str(session["session_id"]))
        for index, message in enumerate(session["messages"], start=1):
            saved = store.append_chat_message(
                str(session["session_id"]),
                {
                    "message_id": message["message_id"],
                    "role": message["role"],
                    "content": message["content"],
                    "client_order": float(index),
                    "include_in_context": message["include_in_context"],
                    "metadata": message["metadata"],
                },
                changed_by="synthetic_history_seed",
                change_reason="生成 embedding 与 retrieval 测试用历史聊天记录。",
            )
            created_message_ids.append(str(saved["message_id"]))

    retrieval_chunk_count = _count_rows_for_sources(
        "retrieval_chunks",
        source_kind="buddy_message",
        source_ids=created_message_ids,
    )
    embedding_job_count = _count_rows_for_sources(
        "embedding_jobs",
        source_kind="buddy_message",
        source_ids=created_message_ids,
    )
    return {
        "kind": "synthetic_buddy_history_seed",
        "batch_id": _normalize_options(options).batch_id,
        "session_count": len(created_session_ids),
        "message_count": len(created_message_ids),
        "retrieval_chunk_count": retrieval_chunk_count,
        "embedding_job_count": embedding_job_count,
        "session_ids": created_session_ids,
        "message_ids": created_message_ids,
    }


def _normalize_options(options: FakeHistoryOptions | None) -> FakeHistoryOptions:
    source = options or FakeHistoryOptions()
    batch_id = str(source.batch_id or "embedding_seed").strip() or "embedding_seed"
    session_count = _bounded_int(source.session_count, default=40, minimum=1, maximum=500)
    min_turns = _bounded_int(source.min_turns, default=6, minimum=1, maximum=80)
    max_turns = _bounded_int(source.max_turns, default=12, minimum=min_turns, maximum=100)
    seed = _bounded_int(source.seed, default=3488, minimum=0, maximum=2**31 - 1)
    return FakeHistoryOptions(
        batch_id=batch_id,
        session_count=session_count,
        min_turns=min_turns,
        max_turns=max_turns,
        seed=seed,
    )


def _build_user_message(rng: random.Random, topic: dict[str, Any], turn_index: int) -> str:
    base = rng.choice(topic["user_goals"])
    if turn_index % 5 == 0:
        return f"{base}\n\n顺便记一下偏好：{rng.choice(_PREFERENCE_SIGNALS)}"
    if turn_index % 3 == 0:
        return f"{base}\n\n这次先别实现，我想先把边界想清楚。"
    return base


def _build_assistant_message(rng: random.Random, topic: dict[str, Any], turn_index: int) -> str:
    action = rng.choice(topic["assistant_actions"])
    follow_up = rng.choice(
        [
            "我会把它当作 context_only，而不是新的系统规则。",
            "这条链路最好走图模板和受控写入，方便之后审计。",
            "如果后面要实验 embedding，可以用这批历史材料验证召回质量。",
            "这里最重要的是保留 source refs，不要只保存模型改写后的摘要。",
        ]
    )
    if turn_index % 4 == 0:
        return f"{action}\n\n我建议把这个判断记录到测试材料里，后续可以检查召回是否命中。{follow_up}"
    return f"{action}\n\n{follow_up}"


def _count_rows_for_sources(table_name: str, *, source_kind: str, source_ids: list[str]) -> int:
    if table_name not in {"retrieval_chunks", "embedding_jobs"}:
        raise ValueError("Unsupported synthetic count table.")
    normalized_ids = [item for item in dict.fromkeys(str(source_id or "").strip() for source_id in source_ids) if item]
    if not normalized_ids:
        return 0
    placeholders = ",".join("?" for _ in normalized_ids)
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name} WHERE source_kind = ? AND source_id IN ({placeholders})",
            (source_kind, *normalized_ids),
        ).fetchone()
    return int(row["count"] if row is not None else 0)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:48] or "embedding_seed"
