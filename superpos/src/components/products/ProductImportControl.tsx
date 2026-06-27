import React, { useRef, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

interface ImportError {
  row: number;
  error: string;
}

interface ImportResponse {
  total_rows: number;
  created:    number;
  updated:    number;
  errors:     ImportError[];
}

interface Props {
  /** Called with a status banner message after the upload completes. */
  onComplete: (banner: { kind: 'success' | 'warn' | 'error'; message: string }) => void;
  /** Called after a successful upload (any non-zero created/updated) so the parent can refetch. */
  onChanged: () => void;
}

export const ProductImportControl: React.FC<Props> = ({ onComplete, onChanged }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [errorsModal, setErrorsModal] = useState<ImportResponse | null>(null);

  const trigger = () => {
    if (uploading) return;
    inputRef.current?.click();
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset the input value immediately so re-selecting the same file later still fires onChange.
    if (e.target) e.target.value = '';
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.csv')) {
      onComplete({ kind: 'error', message: 'Please select a .csv file.' });
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await apiClient.post<ImportResponse>('/products/import/', formData, {
        // Let axios set the multipart boundary header automatically.
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const { total_rows, created, updated, errors } = data;
      const touched = created + updated;
      if (touched > 0) onChanged();

      if (errors.length === 0) {
        onComplete({
          kind: 'success',
          message: `✅ Imported ${created} product${created === 1 ? '' : 's'}, updated ${updated}.`,
        });
      } else {
        // Show the modal with full error list, plus a summary banner.
        setErrorsModal(data);
        onComplete({
          kind: 'warn',
          message: `⚠️ ${errors.length} of ${total_rows} row${total_rows === 1 ? '' : 's'} failed (created ${created}, updated ${updated}).`,
        });
      }
    } catch (err) {
      let msg = 'Import failed. Please try again.';
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        if (typeof data?.detail === 'string') msg = data.detail;
        else if (err.response?.status === 403) msg = 'You do not have permission to import products.';
        else if (err.response?.status === 401) msg = 'Session expired. Please sign in again.';
      }
      onComplete({ kind: 'error', message: msg });
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        onChange={handleFile}
        className="hidden"
      />
      <Button variant="secondary" size="sm" onClick={trigger} disabled={uploading}>
        {uploading ? (
          <>
            <span className="w-3.5 h-3.5 border-2 border-neutral-400 border-t-brand-500 rounded-full spin" />
            Importing…
          </>
        ) : 'Import CSV'}
      </Button>

      {errorsModal && (
        <Modal
          title={`Import errors · ${errorsModal.errors.length} of ${errorsModal.total_rows} rows failed`}
          onClose={() => setErrorsModal(null)}
          maxWidth="max-w-[640px]"
        >
          <div className="px-6 py-4 flex flex-col gap-3">
            <div className="flex gap-4 text-[13px]">
              <SummaryStat label="Rows"    value={errorsModal.total_rows} />
              <SummaryStat label="Created" value={errorsModal.created} tone="success" />
              <SummaryStat label="Updated" value={errorsModal.updated} tone="info" />
              <SummaryStat label="Failed"  value={errorsModal.errors.length} tone="danger" />
            </div>

            <div className="border border-neutral-200 rounded-md max-h-[320px] overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-start font-semibold w-20">Row</th>
                    <th className="px-4 py-2 text-start font-semibold">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {errorsModal.errors.map((e, i) => (
                    <tr key={i} className="border-t border-neutral-100">
                      <td className="px-4 py-2 font-mono text-neutral-600">{e.row}</td>
                      <td className="px-4 py-2 text-danger-700">{e.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end">
            <Button size="sm" onClick={() => setErrorsModal(null)}>Close</Button>
          </div>
        </Modal>
      )}
    </>
  );
};

const SummaryStat: React.FC<{
  label: string; value: number; tone?: 'success' | 'info' | 'danger';
}> = ({ label, value, tone }) => {
  const color =
    tone === 'success' ? 'text-success-600' :
    tone === 'info'    ? 'text-brand-600'   :
    tone === 'danger'  ? 'text-danger-600'  :
                         'text-neutral-800';
  return (
    <div className="flex flex-col">
      <span className="text-[11.5px] uppercase tracking-wider text-neutral-500">{label}</span>
      <span className={`text-[18px] font-semibold tabular-nums ${color}`}>{value}</span>
    </div>
  );
};
