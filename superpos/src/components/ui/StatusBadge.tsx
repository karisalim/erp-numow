import React from 'react';
import { Badge } from './Badge';
import type { BadgeKind } from '../../types';

/**
 * Maps v3.6 document status wire values (types/index.ts status
 * vocabularies) to the prototype badge palette. Unknown values render a
 * neutral badge with the raw value — never a misleading fallback.
 */

type StatusDomain = 'posting' | 'payment' | 'return' | 'approval' | 'sync' | 'generic';

const MAPS: Record<StatusDomain, Record<string, [BadgeKind, string]>> = {
  posting: {
    draft:     ['gray',    'Draft'],
    posted:    ['success', 'Posted'],
    cancelled: ['danger',  'Cancelled'],
    void:      ['danger',  'Void'],
  },
  payment: {
    unpaid:         ['warn',    'Unpaid'],
    partially_paid: ['warn',    'Partially Paid'],
    paid:           ['success', 'Paid'],
    n_a:            ['gray',    'N/A'],
  },
  return: {
    not_returned:       ['gray',   'Not Returned'],
    partially_returned: ['warn',   'Partially Returned'],
    returned:           ['danger', 'Returned'],
  },
  approval: {
    not_required: ['gray',    'Not Required'],
    pending:      ['warn',    'Pending'],
    approved:     ['success', 'Approved'],
    rejected:     ['danger',  'Rejected'],
  },
  sync: {
    synced:       ['success', 'Synced'],
    pending_sync: ['warn',    'Pending Sync'],
    sync_failed:  ['danger',  'Sync Failed'],
  },
  generic: {
    active:    ['success', 'Active'],
    inactive:  ['gray',    'Inactive'],
    completed: ['success', 'Completed'],
    voided:    ['danger',  'Voided'],
    refunded:  ['warn',    'Refunded'],
  },
};

function labelize(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export const StatusBadge: React.FC<{
  value: string;
  domain?: StatusDomain;
}> = ({ value, domain = 'generic' }) => {
  const key = value.toLowerCase();
  const hit = MAPS[domain][key] ?? MAPS.generic[key];
  const [kind, label] = hit ?? (['gray', labelize(value)] as [BadgeKind, string]);
  return <Badge kind={kind}>{label}</Badge>;
};

/** Active / Inactive convenience badge for master-data rows. */
export const ActiveBadge: React.FC<{ active: boolean }> = ({ active }) => (
  <Badge kind={active ? 'success' : 'gray'}>{active ? 'Active' : 'Inactive'}</Badge>
);
