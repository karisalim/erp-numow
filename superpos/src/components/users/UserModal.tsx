import React, { useEffect, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import type { AppUser, UserRole } from '../../types';

/* ─────────────────────────────────────────────────────────────────────────────
 * Permission matrix — drives the "Permissions for <Role>" preview below the
 * form. Truthy → green tick; falsy → red cross. The same matrix is also used
 * on the page itself if we ever want to gate UI actions.
 * ──────────────────────────────────────────────────────────────────────────── */
export const PERMISSION_LABELS: { key: string; label: string }[] = [
  { key: 'sales:create',     label: 'sales:create'     },
  { key: 'sales:void',       label: 'sales:void'       },
  { key: 'products:view',    label: 'products:view'    },
  { key: 'products:edit',    label: 'products:edit'    },
  { key: 'inventory:manage', label: 'inventory:manage' },
  { key: 'reports:view',     label: 'reports:view'     },
  { key: 'users:manage',     label: 'users:manage'     },
  { key: 'settings:manage',  label: 'settings:manage'  },
];

export const PERMISSION_MATRIX: Record<UserRole, Record<string, boolean>> = {
  Owner:   { 'sales:create': true,  'sales:void': true,  'products:view': true,  'products:edit': true,  'inventory:manage': true,  'reports:view': true,  'users:manage': true,  'settings:manage': true  },
  Admin:   { 'sales:create': true,  'sales:void': true,  'products:view': true,  'products:edit': true,  'inventory:manage': true,  'reports:view': true,  'users:manage': true,  'settings:manage': false },
  Manager: { 'sales:create': true,  'sales:void': true,  'products:view': true,  'products:edit': true,  'inventory:manage': true,  'reports:view': true,  'users:manage': false, 'settings:manage': false },
  Cashier: { 'sales:create': true,  'sales:void': false, 'products:view': true,  'products:edit': false, 'inventory:manage': false, 'reports:view': false, 'users:manage': false, 'settings:manage': false },
};

const ROLE_OPTIONS: UserRole[] = ['Owner', 'Admin', 'Manager', 'Cashier'];

export interface BranchLite {
  id: number;
  name: string;
}

interface FormState {
  name:      string;
  email:     string;
  role:      UserRole;
  branch:    string;          // '' = no branch
  pin_code:  string;
  is_active: boolean;
}

interface Props {
  mode: 'add' | 'edit';
  user?: AppUser | null;
  branches: BranchLite[];
  onClose: () => void;
  onSuccess: (action: 'created' | 'updated', user: AppUser) => void;
}

function blank(): FormState {
  return { name: '', email: '', role: 'Cashier', branch: '', pin_code: '', is_active: true };
}

function fromUser(u: AppUser): FormState {
  const branchId = typeof u.branch === 'number' ? String(u.branch) : '';
  return {
    name:      u.full_name || u.name || '',
    email:     u.email || '',
    role:      u.role,
    branch:    branchId,
    pin_code:  '',
    is_active: u.is_active ?? u.active ?? true,
  };
}

function parseErrors(err: unknown): { fieldErrors: Record<string, string>; formError: string | null } {
  const fieldErrors: Record<string, string> = {};
  let formError: string | null = null;
  if (err instanceof AxiosError) {
    const data = err.response?.data;
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      for (const [key, val] of Object.entries(data as Record<string, unknown>)) {
        const msg = Array.isArray(val) ? String(val[0]) : String(val);
        if (key === 'detail' || key === 'non_field_errors') formError = msg;
        else fieldErrors[key] = msg;
      }
    } else if (err.response?.status === 403) {
      formError = 'You do not have permission to manage users.';
    } else {
      formError = err.message || 'Request failed. Please try again.';
    }
  } else {
    formError = 'Unexpected error.';
  }
  return { fieldErrors, formError };
}

export const UserModal: React.FC<Props> = ({ mode, user, branches, onClose, onSuccess }) => {
  const [form, setForm] = useState<FormState>(() =>
    mode === 'edit' && user ? fromUser(user) : blank(),
  );
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  // Keep state in sync if the parent swaps the user mid-flight.
  useEffect(() => {
    if (mode === 'edit' && user) setForm(fromUser(user));
  }, [mode, user]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    if (fieldErrors[k]) {
      setFieldErrors((fe) => { const c = { ...fe }; delete c[k]; return c; });
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    setFieldErrors({});

    if (!form.name.trim())  { setFormError('Full name is required.'); return; }
    if (!form.email.trim()) { setFormError('Email is required.');     return; }
    if (form.pin_code && form.pin_code.length < 4) {
      setFormError('PIN must be at least 4 digits.');
      return;
    }

    const payload: Record<string, unknown> = {
      name:      form.name.trim(),
      email:     form.email.trim(),
      role:      form.role,
      is_active: form.is_active,
    };
    if (form.branch) payload.branch = Number(form.branch);
    else             payload.branch = null;
    if (form.pin_code) payload.pin_code = form.pin_code;

    setSaving(true);
    try {
      const resp = mode === 'edit' && user
        ? await apiClient.patch<AppUser>(`/auth/users/${user.id}/`, payload)
        : await apiClient.post<AppUser>('/auth/users/', payload);
      onSuccess(mode === 'edit' ? 'updated' : 'created', resp.data);
    } catch (err) {
      const { fieldErrors: fe, formError: fmErr } = parseErrors(err);
      setFieldErrors(fe);
      setFormError(fmErr);
    } finally {
      setSaving(false);
    }
  };

  const perms = PERMISSION_MATRIX[form.role] ?? PERMISSION_MATRIX.Cashier;
  const title = mode === 'add'
    ? 'Add team member'
    : `Edit ${form.name || user?.username || 'user'}`;

  return (
    <Modal title={title} onClose={onClose} maxWidth="max-w-[600px]">
      <form onSubmit={submit}>
        {formError && (
          <div className="mx-6 mt-4 flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Full name" required error={fieldErrors.name}>
              <input
                type="text" value={form.name} disabled={saving}
                onChange={(e) => set('name', e.target.value)}
                className={inputCls(!!fieldErrors.name)}
                autoFocus
              />
            </Field>

            <Field label="Email" required error={fieldErrors.email}>
              <input
                type="email" value={form.email} disabled={saving}
                onChange={(e) => set('email', e.target.value)}
                className={inputCls(!!fieldErrors.email)}
              />
            </Field>

            <Field label="Role" error={fieldErrors.role}>
              <select
                value={form.role} disabled={saving}
                onChange={(e) => set('role', e.target.value as UserRole)}
                className={inputCls(!!fieldErrors.role)}
              >
                {ROLE_OPTIONS.map((r) => <option key={r}>{r}</option>)}
              </select>
            </Field>

            <Field label="Branch" error={fieldErrors.branch}>
              <select
                value={form.branch} disabled={saving}
                onChange={(e) => set('branch', e.target.value)}
                className={inputCls(!!fieldErrors.branch)}
              >
                <option value="">— All branches —</option>
                {branches.map((b) => (
                  <option key={b.id} value={String(b.id)}>{b.name}</option>
                ))}
              </select>
            </Field>

            <Field
              label={mode === 'edit' ? 'New PIN (leave blank to keep)' : 'PIN code (4+ digits)'}
              error={fieldErrors.pin_code}
              className="col-span-2"
            >
              <input
                type="password"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                placeholder="••••"
                value={form.pin_code} disabled={saving}
                onChange={(e) => set('pin_code', e.target.value.replace(/\D/g, ''))}
                className={`${inputCls(!!fieldErrors.pin_code)} w-32 font-mono tracking-[0.5em]`}
              />
            </Field>
          </div>

          <label className="flex items-center gap-2 text-[13px]">
            <input
              type="checkbox" checked={form.is_active} disabled={saving}
              onChange={(e) => set('is_active', e.target.checked)}
              className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
            />
            Account active
          </label>

          {/* Dynamic permission preview */}
          <div>
            <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">
              Permissions for {form.role}
            </div>
            <div className="grid grid-cols-2 gap-2 bg-neutral-50 rounded-md p-3 border border-neutral-200">
              {PERMISSION_LABELS.map((p) => {
                const allowed = !!perms[p.key];
                return (
                  <div key={p.key} className="flex items-center gap-2 text-[12.5px] font-mono">
                    <span className={allowed ? 'text-success-600' : 'text-danger-500'}>
                      {allowed ? '✓' : '✗'}
                    </span>
                    {p.label}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                Saving…
              </>
            ) : mode === 'edit' ? 'Save changes' : 'Create user'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

const Field: React.FC<React.PropsWithChildren<{
  label: string; required?: boolean; error?: string; className?: string;
}>> = ({ label, required, error, className = '', children }) => (
  <label className={`flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700 ${className}`}>
    <span>
      {label}
      {required && <span className="text-danger-600 ms-0.5">*</span>}
    </span>
    {children}
    {error && <span className="text-[12px] font-normal text-danger-600">{error}</span>}
  </label>
);

function inputCls(hasError: boolean): string {
  return [
    'h-10 px-3 rounded-md border bg-white text-[14px] focus-ring',
    hasError ? 'border-danger-500' : 'border-neutral-300',
  ].join(' ');
}
