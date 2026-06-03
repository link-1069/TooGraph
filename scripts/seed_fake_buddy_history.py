from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.buddy.fake_history import FakeHistoryOptions, build_fake_history_dataset, seed_fake_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic Buddy chat history for retrieval and embedding experiments.")
    parser.add_argument("--batch-id", default="", help="Stable batch id. Defaults to timestamped synthetic batch.")
    parser.add_argument("--sessions", type=int, default=60, help="Number of synthetic sessions to create.")
    parser.add_argument("--min-turns", type=int, default=6, help="Minimum user/assistant turns per session.")
    parser.add_argument("--max-turns", type=int, default=12, help="Maximum user/assistant turns per session.")
    parser.add_argument("--seed", type=int, default=3488, help="Deterministic content seed.")
    parser.add_argument("--dry-run", action="store_true", help="Only print planned counts and preview, do not write database rows.")
    parser.add_argument("--full-output", action="store_true", help="Print all generated session and message ids.")
    args = parser.parse_args()

    batch_id = args.batch_id.strip() or f"embedding_seed_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')}"
    options = FakeHistoryOptions(
        batch_id=batch_id,
        session_count=args.sessions,
        min_turns=args.min_turns,
        max_turns=args.max_turns,
        seed=args.seed,
    )
    if args.dry_run:
        dataset = build_fake_history_dataset(options)
        message_count = sum(len(session["messages"]) for session in dataset)
        print(
            json.dumps(
                {
                    "kind": "synthetic_buddy_history_plan",
                    "batch_id": batch_id,
                    "session_count": len(dataset),
                    "message_count": message_count,
                    "first_session": dataset[0] if dataset else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = seed_fake_history(options)
    if not args.full_output:
        result = {
            key: value
            for key, value in result.items()
            if key not in {"session_ids", "message_ids"}
        } | {
            "first_session_id": result["session_ids"][0] if result["session_ids"] else "",
            "last_session_id": result["session_ids"][-1] if result["session_ids"] else "",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
