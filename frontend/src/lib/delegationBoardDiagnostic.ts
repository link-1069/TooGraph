export type DelegationBoardDiagnostic = {
  visible: boolean;
  boardId: string;
  title: string;
  status: string;
  cardCount: number;
  statusLabels: string[];
  blockedLabels: string[];
  reviewLabels: string[];
  nextActionLabels: string[];
  sourceRefLabels: string[];
  evidenceLabels: string[];
};

export function buildDelegationBoardDiagnostic(value: unknown): DelegationBoardDiagnostic {
  const board = recordFromUnknown(value);
  const boardId = textFromUnknown(board.board_id ?? board.boardId);
  const title = textFromUnknown(board.title);
  const status = textFromUnknown(board.status);
  const cards = recordList(board.cards);
  const statusLabels = statusLabelsFromBoard(board);
  const blockedLabels = cardLabelsForLane(cards, "blocked");
  const reviewLabels = cardLabelsForLane(cards, "review");
  const nextActionLabels = nextActionLabelsFromBoard(board, cards);
  const sourceRefLabels = sourceRefLabelsFromBoard(board);
  const cardCount = cards.length > 0 ? cards.length : countCardsFromStatusLabels(statusLabels);
  const evidenceLabels = [
    boardId ? `board: ${boardId}` : "",
    status ? `status: ${status}` : "",
    cardCount > 0 ? `cards: ${cardCount}` : "",
    ...statusLabels,
    ...nextActionLabels,
  ].filter(Boolean);
  const visible = Boolean(
    boardId
    || title
    || status
    || cardCount > 0
    || statusLabels.length > 0
    || blockedLabels.length > 0
    || reviewLabels.length > 0
    || nextActionLabels.length > 0
    || sourceRefLabels.length > 0
  );

  return {
    visible,
    boardId,
    title,
    status,
    cardCount,
    statusLabels,
    blockedLabels,
    reviewLabels,
    nextActionLabels,
    sourceRefLabels,
    evidenceLabels,
  };
}

export function listDelegationBoardTraceLabels(value: unknown): string[] {
  return buildDelegationBoardDiagnostic(value).evidenceLabels;
}

function statusLabelsFromBoard(board: Record<string, unknown>) {
  const counts = recordFromUnknown(board.status_counts ?? board.statusCounts);
  return Object.entries(counts)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([lane, count]) => {
      const laneName = textFromUnknown(lane);
      const value = numberFromUnknown(count);
      return laneName && value !== null ? `lane: ${laneName}=${value}` : "";
    })
    .filter(Boolean);
}

function cardLabelsForLane(cards: Record<string, unknown>[], lane: string) {
  return cards
    .filter((card) => textFromUnknown(card.lane) === lane)
    .map((card) => {
      const taskId = textFromUnknown(card.task_id ?? card.taskId);
      if (!taskId) {
        return "";
      }
      const reason = lane === "blocked"
        ? textFromUnknown(card.block_reason ?? card.blockReason)
        : textFromUnknown(card.review_reason ?? card.reviewReason);
      return `${lane}: ${taskId}${reason ? ` (${reason})` : ""}`;
    })
    .filter(Boolean);
}

function nextActionLabelsFromBoard(board: Record<string, unknown>, cards: Record<string, unknown>[]) {
  const labels = recordList(board.next_actions ?? board.nextActions)
    .map((item) => {
      const taskId = textFromUnknown(item.task_id ?? item.taskId);
      const action = textFromUnknown(item.action);
      return taskId && action ? `next: ${taskId}=${action}` : "";
    })
    .filter(Boolean);

  for (const card of cards) {
    const taskId = textFromUnknown(card.task_id ?? card.taskId);
    const action = textFromUnknown(card.recommended_next_action ?? card.recommendedNextAction);
    if (taskId && action) {
      labels.push(`next: ${taskId}=${action}`);
    }
  }
  return uniqueTextList(labels);
}

function sourceRefLabelsFromBoard(board: Record<string, unknown>) {
  return recordList(board.source_refs ?? board.sourceRefs)
    .map((ref) => {
      const kind = textFromUnknown(ref.source_kind ?? ref.kind);
      const id = textFromUnknown(ref.source_id ?? ref.id);
      return kind && id ? `source: ${kind}:${id}` : "";
    })
    .filter(Boolean);
}

function countCardsFromStatusLabels(labels: string[]) {
  return labels.reduce((total, label) => {
    const match = label.match(/=(\d+)$/);
    return total + (match ? Number(match[1]) : 0);
  }, 0);
}

function uniqueTextList(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    if (!value || seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordList(value: unknown) {
  return Array.isArray(value) ? value.map(recordFromUnknown).filter((item) => Object.keys(item).length > 0) : [];
}

function textFromUnknown(value: unknown) {
  return typeof value === "string" ? value.trim() : value === null || value === undefined ? "" : String(value).trim();
}

function numberFromUnknown(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}
