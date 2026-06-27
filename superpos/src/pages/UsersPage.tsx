import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import type { AppUser, BadgeKind, UserRole } from '../types';
import { initials } from '../utils/format';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../components/ui/Icon';
import { Modal } from '../components/ui/Modal';
import { UserModal, type BranchLite } from '../components/users/UserModal';

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

type Toast = { kind: 'success' | 'error'; message: string };

const roleBadge = (r: UserRole): BadgeKind => {
  const map: Record<UserRole, BadgeKind> = {
    Owner:   'brand',
    Admin:   'info',
    Manager: 'warn',
    Cashier: 'success',
  };
  return map[r] ?? 'gray';
};

const fmtLastLogin = (iso: string | null | undefined): string => {
  if (!iso) return 'Never';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Never';
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 5)  return 'Active now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return d.toLocaleDateString();
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Row-actions menu (self-contained, mirrors the Products one).
 * ──────────────────────────────────────────────────────────────────────────── */
type RowAction = 'edit' | 'toggle' | 'delete';

const RowActionsMenu: React.FC<{
  active: boolean;
  onSelect: (action: RowAction) => void;
}> = ({ active, onSelect }) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const choose = (a: RowAction) => { setOpen(false); onSelect(a); };

  return (
    <div ref={wrapRef} className="relative inline-block text-start">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="w-7 h-7 grid place-items-center rounded text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 focus-ring"
        aria-label="Row actions"
      >
        ⋮
      </button>
      {open && (
        <div role="menu" className="absolute end-0 mt-1 z-30 w-44 rounded-md border border-neutral-200 bg-white shadow-lg py-1 text-[13px] fade-in">
          <MenuItem onClick={() => choose('edit')}   icon="gear">Edit</MenuItem>
          <MenuItem onClick={() => choose('toggle')} icon={active ? 'eyeOff' : 'eye'}>
            {active ? 'Deactivate' : 'Activate'}
          </MenuItem>
          <div className="my-1 border-t border-neutral-100" />
          <MenuItem onClick={() => choose('delete')} icon="trash" tone="danger">Delete</MenuItem>
        </div>
      )}
    </div>
  );
};

const MenuItem: React.FC<React.PropsWithChildren<{
  onClick: () => void; icon: string; tone?: 'danger';
}>> = ({ onClick, icon, tone, children }) => (
  <button
    type="button"
    role="menuitem"
    onClick={onClick}
    className={`w-full flex items-center gap-2 px-3 py-1.5 text-start hover:bg-neutral-50 focus-ring
      ${tone === 'danger' ? 'text-danger-600 hover:bg-danger-50' : 'text-neutral-700'}`}
  >
    <Icon name={icon} size={14} />
    {children}
  </button>
);

/* ─────────────────────────────────────────────────────────────────────────────
 * UsersPage
 * ──────────────────────────────────────────────────────────────────────────── */
export const UsersPage: React.FC = () => {
  const { online, pendingSync } = useAppStore();
  const me = useAuthStore((s) => s.user);

  const [users,    setUsers]    = useState<AppUser[]>([]);
  const [branches, setBranches] = useState<BranchLite[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [modal,         setModal]         = useState<{ mode: 'add' | 'edit'; user?: AppUser } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<AppUser | null>(null);
  const [deleting,      setDeleting]      = useState(false);
  const [toast,         setToast]         = useState<Toast | null>(null);

  const refetch = () => setRefreshKey((k) => k + 1);

  /* ─── Fetch users on mount/refresh ────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .get<PaginatedResponse<AppUser> | AppUser[]>('/auth/users/', { params: { page_size: 100 } })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : res.data?.results ?? [];
        setUsers(list);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        let msg = 'Failed to load users.';
        if (err instanceof AxiosError) {
          if (err.response?.status === 403) msg = 'You do not have permission to view users.';
          else if (typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
        }
        setError(msg);
        setUsers([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  /* ─── Fetch branches once (used by both Add and Edit) ─────────────────── */
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<PaginatedResponse<BranchLite> | BranchLite[]>('/auth/branches/', { params: { page_size: 100 } })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : res.data?.results ?? [];
        setBranches(list);
      })
      .catch(() => { /* picker still usable with "All branches" */ });
    return () => { cancelled = true; };
  }, []);

  /* ─── Auto-dismiss toast ──────────────────────────────────────────────── */
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /* ─── KPI tiles, derived ──────────────────────────────────────────────── */
  const stats = useMemo(() => {
    const active = users.filter((u) => (u.is_active ?? u.active) !== false).length;
    const roles  = new Set(users.map((u) => u.role)).size;
    return [
      { l: 'Total users', v: String(users.length) },
      { l: 'Active',      v: String(active) },
      { l: 'Roles',       v: String(roles) },
    ];
  }, [users]);

  /* ─── Row-action handlers ─────────────────────────────────────────────── */
  const handleRowAction = (u: AppUser, action: RowAction) => {
    if (action === 'edit')   setModal({ mode: 'edit', user: u });
    if (action === 'toggle') toggleActive(u);
    if (action === 'delete') setConfirmDelete(u);
  };

  const toggleActive = async (u: AppUser) => {
    const wasActive = (u.is_active ?? u.active) !== false;
    try {
      await apiClient.patch(`/auth/users/${u.id}/`, { is_active: !wasActive });
      setToast({
        kind: 'success',
        message: `${wasActive ? 'Deactivated' : 'Activated'} "${u.full_name || u.username}".`,
      });
      refetch();
    } catch (err) {
      let msg = 'Failed to update user.';
      if (err instanceof AxiosError) {
        if (err.response?.status === 403) msg = 'You do not have permission.';
        else if (typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
      }
      setToast({ kind: 'error', message: msg });
    }
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await apiClient.delete(`/auth/users/${confirmDelete.id}/`);
      setToast({
        kind: 'success',
        message: `Deleted "${confirmDelete.full_name || confirmDelete.username}".`,
      });
      setConfirmDelete(null);
      refetch();
    } catch (err) {
      let msg = 'Failed to delete user.';
      if (err instanceof AxiosError) {
        if (err.response?.status === 403) msg = 'You do not have permission.';
        else if (typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
      }
      setToast({ kind: 'error', message: msg });
    } finally {
      setDeleting(false);
    }
  };

  const branchNameFor = (u: AppUser): string => {
    if (u.branch_name) return u.branch_name;
    if (typeof u.branch === 'number') {
      const b = branches.find((x) => x.id === u.branch);
      return b ? b.name : '—';
    }
    return '—';
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Users & Team"
        subtitle="Role-based access control"
        online={online}
        pendingSync={pendingSync}
        right={
          <Button size="sm" onClick={() => setModal({ mode: 'add' })}>
            <Icon name="plus" size={14} /> Add user
          </Button>
        }
      />

      <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
        {toast && (
          <div
            role={toast.kind === 'success' ? 'status' : 'alert'}
            className={`flex items-start gap-2 rounded-md border px-3 py-2.5 text-[13px] ${
              toast.kind === 'success'
                ? 'border-success-600/30 bg-success-50 text-success-700'
                : 'border-danger-500/30 bg-danger-50 text-danger-700'
            }`}
          >
            <Icon name={toast.kind === 'success' ? 'check' : 'alert'} size={16} className="mt-0.5 shrink-0" />
            <span className="flex-1">{toast.message}</span>
            <button onClick={() => setToast(null)} className="shrink-0 hover:opacity-70 focus-ring rounded" aria-label="Dismiss">
              <Icon name="x" size={14} />
            </button>
          </div>
        )}

        <div className="grid grid-cols-3 gap-4">
          {stats.map((s) => (
            <Card key={s.l} className="p-5">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">{s.l}</div>
              <div className="text-[28px] font-bold tabular-nums mt-1.5 font-mono">{s.v}</div>
            </Card>
          ))}
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            {error}
          </div>
        )}

        <Card className="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div className="overflow-auto flex-1">
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">User</th>
                  <th className="text-start font-semibold">Email</th>
                  <th className="text-start font-semibold">Role</th>
                  <th className="text-start font-semibold">Branch</th>
                  <th className="text-start font-semibold">Last login</th>
                  <th className="px-4 text-start font-semibold">Status</th>
                  <th className="px-4 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-neutral-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                        Loading users…
                      </span>
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-neutral-500">
                      No users yet.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => {
                    const active = (u.is_active ?? u.active) !== false;
                    return (
                      <tr
                        key={u.id}
                        className="border-t border-neutral-100 hover:bg-neutral-50 cursor-pointer"
                        style={{ height: 36 }}
                        onClick={() => setModal({ mode: 'edit', user: u })}
                      >
                        <td className="px-4">
                          <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-full bg-neutral-200 grid place-items-center text-[10px] font-bold text-neutral-700">
                              {initials(u.full_name || u.username)}
                            </div>
                            <span className="font-semibold">{u.full_name || u.username}</span>
                          </div>
                        </td>
                        <td className="text-neutral-600 font-mono text-[12.5px]">{u.email}</td>
                        <td><Badge kind={roleBadge(u.role)}>{u.role}</Badge></td>
                        <td className="text-neutral-600">{branchNameFor(u)}</td>
                        <td className="text-neutral-500 text-[12.5px]">{fmtLastLogin(u.last_login)}</td>
                        <td className="px-4"><Badge kind={active ? 'success' : 'gray'}>{active ? 'Active' : 'Inactive'}</Badge></td>
                        <td className="px-4 text-end" onClick={(e) => e.stopPropagation()}>
                          {String(u.id) !== String(me?.id) ? (
                            <RowActionsMenu active={active} onSelect={(a) => handleRowAction(u, a)} />
                          ) : (
                            <span className="text-[11px] text-neutral-400">you</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {modal && (
        <UserModal
          mode={modal.mode}
          user={modal.user}
          branches={branches}
          onClose={() => setModal(null)}
          onSuccess={(action, saved) => {
            setModal(null);
            setToast({
              kind: 'success',
              message: action === 'created'
                ? `Created "${saved.full_name || saved.username}".`
                : `Updated "${saved.full_name || saved.username}".`,
            });
            refetch();
          }}
        />
      )}

      {confirmDelete && (
        <Modal
          title="Delete user"
          onClose={() => !deleting && setConfirmDelete(null)}
          maxWidth="max-w-[420px]"
        >
          <div className="px-6 py-5 text-[14px] text-neutral-700">
            Are you sure you want to delete{' '}
            <b className="text-neutral-900">"{confirmDelete.full_name || confirmDelete.username}"</b>? This action cannot be undone.
          </div>
          <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => setConfirmDelete(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button type="button" variant="danger" size="sm" onClick={doDelete} disabled={deleting}>
              {deleting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                  Deleting…
                </>
              ) : 'Delete user'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
};
