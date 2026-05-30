import type { ModelLogEntry, ModelLogTreeNode } from "@/types/model-log";

export type ModelLogTreeItem = {
  key: string;
  kind: "run" | "graph_node" | "model_call" | "loop_group";
  depth: number;
  treeNode?: ModelLogTreeNode;
  log?: ModelLogEntry;
  loopIndex?: number;
  logIds: string[];
  selectable: boolean;
  hasChildren: boolean;
  expanded: boolean;
};

export function buildModelLogTreeItems(
  nodes: ModelLogTreeNode[],
  logIndex: Map<string, ModelLogEntry>,
  expandedKeys: ReadonlySet<string>,
  depth = 0,
  path = "root",
): ModelLogTreeItem[] {
  const items: ModelLogTreeItem[] = [];
  nodes.forEach((node, index) => {
    items.push(...buildModelLogTreeNodeItems(node, logIndex, expandedKeys, depth, `${path}.${index}`));
  });
  return items;
}

export function collectExpandableModelLogTreeKeys(nodes: ModelLogTreeNode[]): Set<string> {
  const keys = new Set<string>();
  collectExpandableKeysForNodes(nodes, keys, "root");
  return keys;
}

export function collectModelLogIds(node: ModelLogTreeNode): string[] {
  const ids = [...(node.model_log_ids || [])];
  for (const child of node.children || []) {
    ids.push(...collectModelLogIds(child));
  }
  return Array.from(new Set(ids));
}

function buildModelLogTreeNodeItems(
  node: ModelLogTreeNode,
  logIndex: Map<string, ModelLogEntry>,
  expandedKeys: ReadonlySet<string>,
  depth: number,
  path: string,
): ModelLogTreeItem[] {
  const directLogs = (node.model_log_ids || [])
    .map((logId) => logIndex.get(logId))
    .filter((log): log is ModelLogEntry => Boolean(log));
  const logIds = collectModelLogIds(node);
  const hasChildren = directLogs.length > 0 || (node.children || []).length > 0;
  const key = modelLogTreeNodeKey(node, path);
  const expanded = hasChildren && expandedKeys.has(key);
  const items: ModelLogTreeItem[] = [
    {
      key,
      kind: node.kind,
      depth,
      treeNode: node,
      logIds,
      selectable: logIds.length > 0,
      hasChildren,
      expanded,
    },
  ];
  if (!expanded) {
    return items;
  }
  for (const log of directLogs) {
    items.push({
      key: `model:${log.id}`,
      kind: "model_call",
      depth: depth + 1,
      log,
      logIds: [log.id],
      selectable: true,
      hasChildren: false,
      expanded: false,
    });
  }
  items.push(...buildModelLogTreeChildItems(node.children || [], logIndex, expandedKeys, depth + 1, key));
  return items;
}

function buildModelLogTreeChildItems(
  nodes: ModelLogTreeNode[],
  logIndex: Map<string, ModelLogEntry>,
  expandedKeys: ReadonlySet<string>,
  depth: number,
  parentKey: string,
): ModelLogTreeItem[] {
  const items: ModelLogTreeItem[] = [];
  let loopIndex = 1;
  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    const nextNode = nodes[index + 1];
    if (nextNode && isCapabilityLoopStart(node, nextNode)) {
      const key = capabilityLoopKey(parentKey, loopIndex, node, nextNode, index);
      const logIds = Array.from(new Set([...(node.model_log_ids || []), ...(nextNode.model_log_ids || [])]));
      const expanded = expandedKeys.has(key);
      items.push({
        key,
        kind: "loop_group",
        depth,
        loopIndex,
        logIds,
        selectable: logIds.length > 0,
        hasChildren: true,
        expanded,
      });
      if (expanded) {
        items.push(
          ...buildModelLogTreeNodeItems(node, logIndex, expandedKeys, depth + 1, `${key}.reply`),
          ...buildModelLogTreeNodeItems(nextNode, logIndex, expandedKeys, depth + 1, `${key}.execute`),
        );
      }
      loopIndex += 1;
      index += 1;
      continue;
    }
    items.push(...buildModelLogTreeNodeItems(node, logIndex, expandedKeys, depth, `${parentKey}.${index}`));
  }
  return items;
}

function collectExpandableKeysForNodes(nodes: ModelLogTreeNode[], keys: Set<string>, path: string) {
  nodes.forEach((node, index) => collectExpandableKeysForNode(node, keys, `${path}.${index}`));
}

function collectExpandableKeysForNode(node: ModelLogTreeNode, keys: Set<string>, path: string) {
  const key = modelLogTreeNodeKey(node, path);
  if ((node.model_log_ids || []).length > 0 || (node.children || []).length > 0) {
    keys.add(key);
  }
  collectExpandableKeysForChildNodes(node.children || [], keys, key);
}

function collectExpandableKeysForChildNodes(nodes: ModelLogTreeNode[], keys: Set<string>, parentKey: string) {
  let loopIndex = 1;
  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    const nextNode = nodes[index + 1];
    if (nextNode && isCapabilityLoopStart(node, nextNode)) {
      const key = capabilityLoopKey(parentKey, loopIndex, node, nextNode, index);
      keys.add(key);
      collectExpandableKeysForNode(node, keys, `${key}.reply`);
      collectExpandableKeysForNode(nextNode, keys, `${key}.execute`);
      loopIndex += 1;
      index += 1;
      continue;
    }
    collectExpandableKeysForNode(node, keys, `${parentKey}.${index}`);
  }
}

function modelLogTreeNodeKey(node: ModelLogTreeNode, path: string) {
  if (node.kind === "run") {
    return node.id || node.run_id || path;
  }
  if (node.execution_id) {
    return `${node.id}:exec:${node.execution_id}`;
  }
  return `${node.id}:path:${path}`;
}

function capabilityLoopKey(
  parentKey: string,
  loopIndex: number,
  replyNode: ModelLogTreeNode,
  executeNode: ModelLogTreeNode,
  siblingIndex: number,
) {
  return [
    "loop",
    parentKey,
    loopIndex,
    replyNode.execution_id || replyNode.id || siblingIndex,
    executeNode.execution_id || executeNode.id || siblingIndex + 1,
  ].join(":");
}

function isCapabilityLoopStart(node: ModelLogTreeNode, nextNode: ModelLogTreeNode) {
  return node.node_id === "reply_and_select_capability" && nextNode.node_id === "execute_capability";
}
