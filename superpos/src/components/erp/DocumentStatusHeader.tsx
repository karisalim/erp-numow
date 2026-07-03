import React from 'react';
import { StatusBadge } from '../ui/StatusBadge';

/**
 * Document detail header (prototype invoice detail): big document number,
 * context line, and the document status badge set. Only statuses that
 * exist on the document are rendered — no invented placeholders.
 */
export const DocumentStatusHeader: React.FC<{
  docNumber: string;
  context?: React.ReactNode;
  postingStatus?: string;
  paymentStatus?: string;
  returnStatus?: string;
  approvalStatus?: string;
  syncStatus?: string;
  extraBadges?: React.ReactNode;
}> = ({ docNumber, context, postingStatus, paymentStatus, returnStatus, approvalStatus, syncStatus, extraBadges }) => (
  <div className="px-5 py-4 border-b border-neutral-200 flex items-start justify-between flex-wrap gap-3">
    <div className="min-w-0">
      <div className="text-[19px] font-extrabold">{docNumber}</div>
      {context && <div className="text-[12.5px] text-neutral-500 mt-0.5">{context}</div>}
    </div>
    <div className="flex items-center gap-1.5 flex-wrap">
      {postingStatus && <StatusBadge domain="posting" value={postingStatus} />}
      {paymentStatus && <StatusBadge domain="payment" value={paymentStatus} />}
      {returnStatus && <StatusBadge domain="return" value={returnStatus} />}
      {approvalStatus && <StatusBadge domain="approval" value={approvalStatus} />}
      {syncStatus && <StatusBadge domain="sync" value={syncStatus} />}
      {extraBadges}
    </div>
  </div>
);
