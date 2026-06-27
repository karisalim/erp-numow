import React from 'react';
import { Icon } from '../ui/Icon';
import { useAuthStore } from '../../store/authStore';

interface HeaderProps {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  online: boolean;
  pendingSync: number;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle, right, online, pendingSync }) => {
  const user = useAuthStore(s => s.user);

  return (
    <header className="h-16 px-6 border-b border-neutral-200 bg-white flex items-center justify-between">
      <div className="min-w-0">
        <div className="text-[15px] font-semibold text-neutral-900 truncate">{title}</div>
        {subtitle && <div className="text-[12px] text-neutral-500 truncate">{subtitle}</div>}
      </div>
      <div className="flex items-center gap-3">
        {right}
        <div
          className={`flex items-center gap-2 px-3 h-9 rounded-md border text-[12px] font-medium
            ${online
              ? 'bg-success-50 border-success-500/30 text-success-700'
              : 'bg-warn-50 border-warn-500/30 text-warn-700'
            }`}
        >
          <Icon name={online ? 'wifi' : 'wifiOff'} size={14} />
          {online ? 'Online' : <>Offline · {pendingSync} pending</>}
        </div>
        <div className="flex items-center gap-2 ps-3 border-s border-neutral-200">
          <div className="w-8 h-8 rounded-full bg-neutral-200 grid place-items-center text-[12px] font-semibold text-neutral-700">
            {user?.initials ?? 'AH'}
          </div>
          <div className="text-[13px] hidden md:block">
            <div className="font-semibold leading-tight">{user?.name ?? 'Ahmed H.'}</div>
            <div className="text-neutral-500 leading-tight">{user?.role ?? 'Cashier'} · {user?.terminal ?? 'POS-01'}</div>
          </div>
        </div>
      </div>
    </header>
  );
};
