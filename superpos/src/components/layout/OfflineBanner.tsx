import React from 'react';
import { Icon } from '../ui/Icon';

interface OfflineBannerProps {
  pending: number;
}

export const OfflineBanner: React.FC<OfflineBannerProps> = ({ pending }) => (
  <div className="h-9 bg-warn-50 border-b border-warn-500/30 text-warn-700 px-6 flex items-center gap-2 text-[12.5px]">
    <Icon name="wifiOff" size={14} />
    <span className="font-semibold">Offline mode active.</span>
    <span>Transactions are saved locally and will sync when connection returns.</span>
    <span className="ms-auto flex items-center gap-2">
      <Icon name="sync" size={14} />
      <b>{pending}</b> pending
    </span>
  </div>
);
