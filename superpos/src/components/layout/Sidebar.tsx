import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { Icon } from '../ui/Icon';
import type { UserRole } from '../../types';

interface NavItem {
  path: string;
  labelKey: string;   // i18next key under `nav.*`
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/pos',       labelKey: 'nav.pos',       icon: 'pos'     },
  { path: '/dashboard', labelKey: 'nav.dashboard', icon: 'chart'   },
  { path: '/products',  labelKey: 'nav.products',  icon: 'box'     },
  { path: '/inventory', labelKey: 'nav.inventory', icon: 'archive' },
  { path: '/scale',     labelKey: 'nav.scale',     icon: 'barcode' },
  { path: '/sales',     labelKey: 'nav.sales',     icon: 'receipt' },
  { path: '/users',     labelKey: 'nav.users',     icon: 'users'   },
  { path: '/settings',  labelKey: 'nav.settings',  icon: 'gear'    },
];

// Cashiers only see POS + Sales. Manager/Admin/Owner see everything.
const CASHIER_ALLOWED = new Set<string>(['/pos', '/sales']);

function navFor(role: UserRole | undefined): NavItem[] {
  if (role === 'Cashier') return NAV_ITEMS.filter((i) => CASHIER_ALLOWED.has(i.path));
  return NAV_ITEMS;
}

export const Sidebar: React.FC = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { logout } = useAuthStore();
  const role = useAuthStore((s) => s.user?.role);
  const items = navFor(role);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside className="w-[220px] shrink-0 bg-white border-e border-neutral-200 flex flex-col">
      <div className="h-16 px-5 flex items-center gap-2 border-b border-neutral-200">
        <div className="w-8 h-8 rounded-md bg-brand-500 grid place-items-center text-white font-bold">S</div>
        <div className="font-semibold text-[15px] tracking-tight">SuperPOS</div>
      </div>
      <nav className="p-3 flex-1 flex flex-col gap-0.5">
        {items.map(item => {
          const active = pathname === item.path || (item.path === '/pos' && pathname === '/');
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`h-11 px-3 rounded-md flex items-center gap-3 text-[14px] focus-ring text-start w-full
                ${active
                  ? 'bg-brand-50 text-brand-700 font-semibold'
                  : 'text-neutral-600 hover:bg-neutral-100'
                }`}
            >
              <Icon name={item.icon} size={20} />
              <span>{t(item.labelKey)}</span>
            </button>
          );
        })}
        <div className="mt-auto pt-3 border-t border-neutral-200">
          <button
            onClick={handleLogout}
            className="w-full h-11 px-3 rounded-md flex items-center gap-3 text-[14px] text-neutral-600 hover:bg-neutral-100 focus-ring"
          >
            <Icon name="logout" size={20} />
            <span>{t('nav.signOut')}</span>
          </button>
        </div>
      </nav>
    </aside>
  );
};
