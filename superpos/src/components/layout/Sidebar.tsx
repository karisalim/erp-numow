import React, { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useAppStore } from '../../store/appStore';
import { roleAtLeast, ROUTE_MIN_ROLE } from '../../auth/permissions';
import { Icon } from '../ui/Icon';
import type { UserRole } from '../../types';

interface NavItem {
  path: string;
  labelKey: string;   // i18next key under `nav.*`
  fallback: string;   // English fallback when the key is missing
  icon: string;
}

interface NavGroup {
  labelKey?: string;
  fallback?: string;
  items: NavItem[];
}

/**
 * Grouped navigation following the approved prototype sidebar. Route
 * visibility mirrors ROUTE_MIN_ROLE — but hiding a link is cosmetic
 * only; the real enforcement is RequireRole on the route plus backend
 * 403s.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { path: '/pos',       labelKey: 'nav.pos',       fallback: 'Point of Sale', icon: 'pos' },
      { path: '/dashboard', labelKey: 'nav.dashboard', fallback: 'Dashboard',     icon: 'chart' },
    ],
  },
  {
    labelKey: 'nav.groupOperations', fallback: 'Operations',
    items: [
      { path: '/sales',     labelKey: 'nav.sales',     fallback: 'Sales',     icon: 'receipt' },
      { path: '/purchases', labelKey: 'nav.purchases', fallback: 'Purchases', icon: 'truck' },
      { path: '/customers', labelKey: 'nav.customers', fallback: 'Customers', icon: 'users' },
      { path: '/suppliers', labelKey: 'nav.suppliers', fallback: 'Suppliers', icon: 'box' },
    ],
  },
  {
    labelKey: 'nav.groupCatalog', fallback: 'Catalog & Stock',
    items: [
      { path: '/products',   labelKey: 'nav.products',   fallback: 'Products',   icon: 'tag' },
      { path: '/inventory',  labelKey: 'nav.inventory',  fallback: 'Inventory',  icon: 'layers' },
      { path: '/warehouses', labelKey: 'nav.warehouses', fallback: 'Warehouses', icon: 'archive' },
      { path: '/scale',      labelKey: 'nav.scale',      fallback: 'Scale / PLU', icon: 'barcode' },
    ],
  },
  {
    labelKey: 'nav.groupFinance', fallback: 'Finance',
    items: [
      { path: '/finance', labelKey: 'nav.finance', fallback: 'Treasury / Finance', icon: 'bank' },
    ],
  },
  {
    labelKey: 'nav.groupAdmin', fallback: 'Admin',
    items: [
      { path: '/users',    labelKey: 'nav.users',    fallback: 'Users',    icon: 'shield' },
      { path: '/settings', labelKey: 'nav.settings', fallback: 'Settings', icon: 'gear' },
    ],
  },
];

function visibleGroups(role: UserRole | undefined): NavGroup[] {
  return NAV_GROUPS
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => {
        const min = ROUTE_MIN_ROLE[i.path];
        return !min || roleAtLeast(role, min);
      }),
    }))
    .filter((g) => g.items.length > 0);
}

export const Sidebar: React.FC = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const setSidebarOpen = useAppStore((s) => s.setSidebarOpen);
  const groups = visibleGroups(user?.role);

  // Close the overlay whenever the route changes (tap a link → navigate).
  useEffect(() => { setSidebarOpen(false); }, [pathname, setSidebarOpen]);

  const nav = (
    <aside className="w-[220px] h-full shrink-0 bg-white border-e border-neutral-200 flex flex-col">
      <div className="h-16 px-4 flex items-center gap-2.5 border-b border-neutral-200 shrink-0">
        <div className="w-[34px] h-[34px] rounded-[9px] bg-gradient-to-br from-brand-500 to-brand-700 grid place-items-center text-white font-extrabold text-[16px] shadow-sm">
          {(user?.tenant_name || 'S').charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="font-extrabold text-[14px] tracking-tight leading-tight truncate">
            {user?.tenant_name || 'SuperPOS'}
          </div>
          {user?.branch_name && (
            <div className="text-[9px] tracking-widest uppercase text-neutral-400 font-bold truncate">
              {user.branch_name}
            </div>
          )}
        </div>
      </div>
      <nav className="p-2.5 flex-1 overflow-y-auto flex flex-col gap-px">
        {groups.map((g, gi) => (
          <React.Fragment key={gi}>
            {g.labelKey && (
              <div className="text-[10px] tracking-widest uppercase text-neutral-400 font-bold px-2.5 pt-3 pb-1">
                {t(g.labelKey, g.fallback ?? '')}
              </div>
            )}
            {g.items.map((item) => {
              const active = pathname === item.path
                || pathname.startsWith(item.path + '/')
                || (item.path === '/pos' && pathname === '/');
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  aria-current={active ? 'page' : undefined}
                  className={`h-[38px] px-2.5 rounded-md flex items-center gap-2.5 text-[13.5px] focus-ring text-start w-full shrink-0
                    ${active
                      ? 'bg-brand-50 text-brand-700 font-semibold'
                      : 'text-neutral-600 hover:bg-neutral-100'
                    }`}
                >
                  <Icon name={item.icon} size={18} />
                  <span className="truncate">{t(item.labelKey, item.fallback)}</span>
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </nav>
    </aside>
  );

  return (
    <>
      {/* Static sidebar ≥lg */}
      <div className="hidden lg:block h-full">{nav}</div>
      {/* Overlay sidebar <lg */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-[1000] bg-black/40 lg:hidden fade-in"
          onClick={(e) => { if (e.target === e.currentTarget) setSidebarOpen(false); }}
        >
          <div className="h-full w-[240px] shadow-lg">{nav}</div>
        </div>
      )}
    </>
  );
};
