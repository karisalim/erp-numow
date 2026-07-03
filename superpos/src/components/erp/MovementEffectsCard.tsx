import React from 'react';
import { Card, CardHeader, CardBody } from '../ui/Card';
import { Badge } from '../ui/Badge';
import type { BadgeKind } from '../../types';

/* ─────────────────────────────────────────────────────────────────────────────
 * "Movement effects" card (prototype invoice detail): explains what a
 * posted document actually did — payment routing, stock movements, tax,
 * AR/AP effects. Rows are supplied by the page from real document data.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface MovementEffect {
  badge: string;
  badgeKind?: BadgeKind;
  text: React.ReactNode;
}

export const MovementEffectsCard: React.FC<{
  effects: MovementEffect[];
  className?: string;
}> = ({ effects, className = '' }) => (
  <Card className={className}>
    <CardHeader
      title="Movement effects"
      actions={<span className="text-[11.5px] text-neutral-400">ledger-driven</span>}
    />
    <CardBody className="flex flex-col gap-2.5">
      {effects.length === 0 ? (
        <div className="text-[12.5px] text-neutral-400">No ledger effects recorded for this document.</div>
      ) : (
        effects.map((e, i) => (
          <div key={i} className="flex items-center gap-2.5 text-[13px]">
            <Badge kind={e.badgeKind ?? 'brand'}>{e.badge}</Badge>
            <span className="min-w-0">{e.text}</span>
          </div>
        ))
      )}
    </CardBody>
  </Card>
);
