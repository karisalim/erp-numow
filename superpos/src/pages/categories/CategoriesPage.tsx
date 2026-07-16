import React, { useMemo, useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Tabs } from '../../components/ui/Tabs';
import { FormField, SelectField, FieldError } from '../../components/ui/FormField';
import { categoriesApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { flattenTree, descendantIds } from '../../utils/tree';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { productVisual } from '../../utils/categoryVisual';
import type { CategoryTreeNode } from '../../types/erp';

type TreeKind = 'sales' | 'inventory';

const TreeFormModal: React.FC<{
  kind: TreeKind;
  nodes: CategoryTreeNode[];
  initial?: CategoryTreeNode;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (values: { name: string; parent: number | null }) => void;
  onClose: () => void;
}> = ({ kind, nodes, initial, busy, error, onSubmit, onClose }) => {
  const [name, setName] = useState(initial?.name ?? '');
  const [parent, setParent] = useState<string>(initial?.parent != null ? String(initial.parent) : '');

  // Exclude the node itself and its own descendants from the parent picker —
  // a fast client-side mirror of the backend's cycle guard.
  const excluded = useMemo(
    () => initial ? new Set([initial.id, ...descendantIds(nodes, initial.id)]) : new Set<number>(),
    [nodes, initial],
  );
  const parentOptions = flattenTree(nodes).filter(({ node }) => !excluded.has(node.id));

  return (
    <Modal title={initial ? `Edit ${initial.name}` : `New ${kind} category`} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) onSubmit({ name: name.trim(), parent: parent ? Number(parent) : null });
        }}
        className="p-5 space-y-4"
      >
        <FormField
          label="Name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={error?.fieldErrors.name}
        />
        <SelectField
          label="Parent (optional)"
          value={parent}
          onChange={(e) => setParent(e.target.value)}
          error={error?.fieldErrors.parent}
          hint="Leave blank for a top-level category."
        >
          <option value="">— Root level —</option>
          {parentOptions.map(({ node, depth }) => (
            <option key={node.id} value={String(node.id)}>
              {'  '.repeat(depth)}{depth > 0 ? '↳ ' : ''}{node.name}
            </option>
          ))}
        </SelectField>
        {error && !error.fieldErrors.name && !error.fieldErrors.parent && <FieldError error={error.message} />}
        <div className="flex gap-2 pt-1">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" className="flex-1" disabled={busy || !name.trim()}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

export const CategoriesPage: React.FC = () => {
  const [tab, setTab] = useState<TreeKind>('sales');

  const salesQ     = useQuery(() => categoriesApi.listSales().then(asResults), []);
  const inventoryQ = useQuery(() => categoriesApi.listInventory().then(asResults), []);

  const activeQ = tab === 'sales' ? salesQ : inventoryQ;
  const nodes = activeQ.data ?? [];
  const flat = useMemo(() => flattenTree(nodes), [nodes]);
  const depthById = useMemo(() => new Map(flat.map(({ node, depth }) => [node.id, depth])), [flat]);
  const rows = flat.map((f) => f.node);

  const [form, setForm] = useState<'create' | 'edit' | null>(null);
  const [selected, setSelected] = useState<CategoryTreeNode | null>(null);
  const [deactivating, setDeactivating] = useState<CategoryTreeNode | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const api = tab === 'sales'
    ? { create: categoriesApi.createSales, update: categoriesApi.updateSales, deactivate: categoriesApi.deactivateSales }
    : { create: categoriesApi.createInventory, update: categoriesApi.updateInventory, deactivate: categoriesApi.deactivateInventory };

  const submit = async (values: { name: string; parent: number | null }) => {
    setBusy(true);
    setFormError(null);
    try {
      if (form === 'edit' && selected) {
        await api.update(selected.id, values);
      } else {
        await api.create(values);
      }
      setForm(null);
      activeQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmDeactivate = async () => {
    if (!deactivating) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.deactivate(deactivating.id);
      setDeactivating(null);
      activeQ.refetch();
    } catch (err) {
      setActionError(parseApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<CategoryTreeNode>[] = [
    {
      key: 'name', header: 'Name',
      render: (n) => {
        const depth = depthById.get(n.id) ?? 0;
        const { emoji, gradient } = productVisual(n.name, n.name);
        return (
          <span style={{ paddingInlineStart: depth * 20 }} className="inline-flex items-center gap-2">
            {depth > 0 && <span className="text-neutral-300">↳</span>}
            <span className={`w-6 h-6 rounded-md grid place-items-center text-[12px] shrink-0 bg-gradient-to-br ${gradient}`}>
              <span aria-hidden>{emoji}</span>
            </span>
            <span className="font-semibold">{n.name}</span>
          </span>
        );
      },
    },
    { key: 'status', header: 'Status', render: (n) => <ActiveBadge active={n.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (n) => (
        <div className="flex justify-end gap-1">
          <button
            onClick={() => { setSelected(n); setFormError(null); setForm('edit'); }}
            className="w-7 h-7 rounded grid place-items-center text-neutral-500 hover:bg-neutral-100 focus-ring"
            aria-label="Edit"
          >
            <Icon name="edit" size={14} />
          </button>
          {n.is_active && (
            <button
              onClick={() => setDeactivating(n)}
              className="w-7 h-7 rounded grid place-items-center text-danger-500 hover:bg-danger-50 focus-ring"
              aria-label="Deactivate"
            >
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Categories"
        subtitle="Sales and Inventory classification trees — independent of each other and of the legacy flat category"
        right={
          <Button size="sm" onClick={() => { setFormError(null); setForm('create'); }}>
            <Icon name="plus" size={14} /> New category
          </Button>
        }
      />
      <div className="p-5 max-w-[900px] w-full mx-auto space-y-4">
        <Tabs
          value={tab}
          onChange={setTab}
          options={[
            { value: 'sales', label: 'Sales categories' },
            { value: 'inventory', label: 'Inventory categories' },
          ]}
        />
        <DataTable<CategoryTreeNode>
          columns={columns}
          rows={rows}
          rowKey={(n) => n.id}
          loading={activeQ.loading}
          error={activeQ.error}
          onRetry={activeQ.refetch}
          emptyTitle={`No ${tab} categories yet`}
          emptyHint="Products keep using the legacy flat category until you assign them to this tree — nothing breaks by leaving it empty."
        />
      </div>

      {form && (
        <TreeFormModal
          kind={tab}
          nodes={nodes}
          initial={form === 'edit' ? selected ?? undefined : undefined}
          busy={busy}
          error={formError}
          onSubmit={submit}
          onClose={() => setForm(null)}
        />
      )}

      {deactivating && (
        <ConfirmDialog
          title={`Deactivate ${deactivating.name}?`}
          message="Products already linked to it stay linked, but it can no longer be chosen for new ones, and it will no longer accept new child categories."
          confirmLabel="Deactivate"
          busy={busy}
          error={actionError}
          onConfirm={confirmDeactivate}
          onCancel={() => { setDeactivating(null); setActionError(null); }}
        />
      )}
    </div>
  );
};
