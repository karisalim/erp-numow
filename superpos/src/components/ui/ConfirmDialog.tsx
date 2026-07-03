import React from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { AlertBanner } from './states';

/**
 * Confirmation modal for destructive / posting actions. Busy state
 * disables both buttons so a double-click can't double-submit.
 */
export const ConfirmDialog: React.FC<{
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'danger' | 'primary' | 'warn';
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy,
  error,
  onConfirm,
  onCancel,
}) => (
  <Modal title={title} onClose={busy ? () => undefined : onCancel} maxWidth="max-w-[440px]">
    <div className="p-6">
      <div className="text-[13.5px] text-neutral-700">{message}</div>
      {error && <AlertBanner tone="danger" className="mt-3">{error}</AlertBanner>}
    </div>
    <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
      <Button variant="secondary" onClick={onCancel} disabled={busy}>
        {cancelLabel}
      </Button>
      <Button
        variant={tone === 'danger' ? 'danger' : tone === 'warn' ? 'secondary' : 'primary'}
        onClick={onConfirm}
        disabled={busy}
      >
        {busy ? 'Working…' : confirmLabel}
      </Button>
    </div>
  </Modal>
);
