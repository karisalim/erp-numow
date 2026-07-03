import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Icon } from '../ui/Icon';
import { useAuthStore } from '../../store/authStore';
import { useAppStore } from '../../store/appStore';

interface HeaderProps {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}

/**
 * 64px app header (prototype): page title + subtitle, page-specific
 * actions, honest connectivity pill (real navigator.onLine — no fake
 * sync counts), and the profile dropdown. Reads shell state itself so
 * pages no longer have to thread online/pendingSync props through.
 */
export const Header: React.FC<HeaderProps> = ({ title, subtitle, right }) => {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const online = useAppStore((s) => s.online);
  const setSidebarOpen = useAppStore((s) => s.setSidebarOpen);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuOpen]);

  const handleLogout = () => {
    setMenuOpen(false);
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 shrink-0 px-4 sm:px-6 border-b border-neutral-200 bg-white flex items-center justify-between gap-3 relative z-30">
      <div className="flex items-center gap-2 min-w-0">
        <button
          onClick={() => setSidebarOpen(true)}
          aria-label="Open menu"
          className="lg:hidden w-9 h-9 grid place-items-center rounded-md hover:bg-neutral-100 text-neutral-600 focus-ring shrink-0"
        >
          <Icon name="menu" size={20} />
        </button>
        <div className="min-w-0">
          <div className="text-[15px] font-bold text-neutral-900 truncate leading-tight">{title}</div>
          {subtitle && <div className="text-[12px] text-neutral-500 truncate">{subtitle}</div>}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {right}
        <div
          className={`hidden sm:flex items-center gap-2 px-3 h-[34px] rounded-md border text-[12px] font-semibold
            ${online
              ? 'bg-success-50 border-success-500/30 text-success-700'
              : 'bg-warn-50 border-warn-500/30 text-warn-700'
            }`}
          title={online ? undefined : 'No network connection detected by the browser.'}
        >
          <Icon name={online ? 'wifi' : 'wifiOff'} size={14} />
          {online ? t('header.online', 'Online') : t('header.offline', 'Offline')}
        </div>
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="flex items-center gap-2 ps-3 border-s border-neutral-200 focus-ring rounded-md"
          >
            <div className="w-[34px] h-[34px] rounded-full bg-neutral-800 grid place-items-center text-[12px] font-bold text-white">
              {user?.initials ?? '?'}
            </div>
            <div className="text-[13px] hidden md:block text-start">
              <div className="font-bold leading-tight">{user?.name ?? ''}</div>
              <div className="text-neutral-500 leading-tight text-[11.5px]">
                {user?.role ?? ''}{user?.branch_name ? ` · ${user.branch_name}` : ''}
              </div>
            </div>
            <Icon name="chevD" size={14} className="text-neutral-400 hidden md:inline-flex" />
          </button>
          {menuOpen && (
            <div className="absolute end-0 top-[46px] w-72 bg-white border border-neutral-200 rounded-xl shadow-lg overflow-hidden z-40">
              <div className="px-4 py-3.5 border-b border-neutral-200 flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-neutral-800 grid place-items-center text-[13px] font-bold text-white shrink-0">
                  {user?.initials ?? '?'}
                </div>
                <div className="min-w-0">
                  <div className="font-bold text-[13.5px] truncate">{user?.name}</div>
                  <div className="text-[12px] text-neutral-500 truncate">
                    {user?.role}
                    {user?.branch_name ? ` · ${user.branch_name}` : ''}
                    {user?.terminal_name ? ` · ${user.terminal_name}` : ''}
                  </div>
                </div>
              </div>
              <div className="p-1.5">
                <button
                  onClick={handleLogout}
                  className="w-full h-10 px-3 rounded-md flex items-center gap-3 text-[13.5px] text-neutral-600 hover:bg-neutral-100 focus-ring"
                >
                  <Icon name="logout" size={17} />
                  {t('nav.signOut', 'Sign out')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
