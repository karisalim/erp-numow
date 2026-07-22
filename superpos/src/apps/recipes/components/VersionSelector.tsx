import React from 'react';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { formatDate } from '../utils/format';
import type { RecipeVersion } from '../types';

const statusBadge = (status: RecipeVersion['status']) => {
  if (status === 'active') return <Badge kind="success">Active</Badge>;
  if (status === 'draft') return <Badge kind="warn">Draft</Badge>;
  return <Badge kind="gray">Archived</Badge>;
};

/**
 * Lists a recipe's versions (newest first, as returned by the backend) and
 * lets the caller select one to view, or activate a draft. Promoting a
 * version is a single backend call (`RecipeVersionActivateView`) that
 * atomically archives whatever was previously active — this component
 * only triggers it, the server owns the actual state transition.
 */
export const VersionSelector: React.FC<{
  versions: RecipeVersion[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onActivate?: (id: number) => void;
  activating?: boolean;
}> = ({ versions, selectedId, onSelect, onActivate, activating }) => {
  if (versions.length === 0) return null;
  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-sm divide-y divide-neutral-100">
      {versions.map((v) => (
        <div
          key={v.id}
          className={`flex items-center justify-between gap-3 px-3.5 py-2.5 ${selectedId === v.id ? 'bg-brand-50/50' : ''}`}
        >
          <button
            onClick={() => onSelect(v.id)}
            className="flex items-center gap-2 text-start focus-ring rounded min-w-0"
          >
            <span className="text-[13.5px] font-semibold">v{v.version_no}</span>
            {statusBadge(v.status)}
            <span className="text-[11.5px] text-neutral-400 truncate">{formatDate(v.created_at)}</span>
          </button>
          {v.status !== 'active' && onActivate && (
            <Button size="sm" variant="secondary" disabled={activating} onClick={() => onActivate(v.id)}>
              {activating ? 'Activating…' : 'Activate'}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
};
