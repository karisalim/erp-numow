export interface TreeNodeLike {
  id: number;
  parent: number | null;
  is_active: boolean;
}

export interface FlattenedNode<T> {
  node: T;
  depth: number;
}

/**
 * Flatten a parent-linked list into depth-first, indented order (roots
 * first, each node's children immediately after it). Used for both the
 * Categories admin tree view and category `<select>` pickers elsewhere.
 * Tolerant of orphaned/cyclic data (defensive — the backend already
 * prevents cycles, this just guarantees the function terminates).
 */
export function flattenTree<T extends TreeNodeLike>(nodes: T[]): FlattenedNode<T>[] {
  const byParent = new Map<number | null, T[]>();
  for (const n of nodes) {
    const list = byParent.get(n.parent) ?? [];
    list.push(n);
    byParent.set(n.parent, list);
  }

  const out: FlattenedNode<T>[] = [];
  const visited = new Set<number>();

  function walk(parentId: number | null, depth: number) {
    for (const n of byParent.get(parentId) ?? []) {
      if (visited.has(n.id)) continue; // guard against corrupt/cyclic data
      visited.add(n.id);
      out.push({ node: n, depth });
      walk(n.id, depth + 1);
    }
  }

  walk(null, 0);
  // Any nodes whose parent wasn't found (shouldn't happen with clean data)
  // still get listed, at depth 0, rather than silently dropped.
  for (const n of nodes) {
    if (!visited.has(n.id)) out.push({ node: n, depth: 0 });
  }
  return out;
}

/** All descendant ids of `nodeId` (not including itself) — used to exclude
 * a node's own subtree from its "choose a new parent" picker, giving a fast
 * client-side rejection ahead of the backend's own cycle guard. */
export function descendantIds<T extends TreeNodeLike>(nodes: T[], nodeId: number): Set<number> {
  const children = new Map<number | null, T[]>();
  for (const n of nodes) {
    const list = children.get(n.parent) ?? [];
    list.push(n);
    children.set(n.parent, list);
  }
  const out = new Set<number>();
  function walk(id: number) {
    for (const child of children.get(id) ?? []) {
      if (out.has(child.id)) continue;
      out.add(child.id);
      walk(child.id);
    }
  }
  walk(nodeId);
  return out;
}
