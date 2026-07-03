import React from 'react';
import { Icon } from '../ui/Icon';

/**
 * Honest connectivity banner: shown when the browser reports no network.
 * There is no offline queue in this product — transactions can NOT be
 * saved locally, so the banner must say exactly that (audit P0-03).
 */
export const OfflineBanner: React.FC = () => (
  <div className="bg-warn-50 border-b border-warn-500/30 text-warn-700 px-4 py-2 flex items-center gap-2 text-[12.5px] font-semibold" role="alert">
    <Icon name="wifiOff" size={15} />
    No network connection. Sales and other actions cannot be posted until the connection is restored — nothing is saved locally.
  </div>
);
