import React, { Suspense } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import './i18n';                              // initialise i18next once at boot
import { useLanguageSync } from './i18n/useLanguageSync';
import { useAuthStore } from './store/authStore';
import { useAppStore } from './store/appStore';
import { Sidebar } from './components/layout/Sidebar';
import { OfflineBanner } from './components/layout/OfflineBanner';
import { RequireRole } from './auth/RequireRole';
import { LoadingState } from './components/ui/states';
import { LoginPage } from './pages/LoginPage';
import { POSPage } from './pages/POSPage';
import { ReceiptPage } from './pages/ReceiptPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProductsPage } from './pages/ProductsPage';
import { InventoryPage } from './pages/InventoryPage';
import { SalesPage } from './pages/SalesPage';
import { UsersPage } from './pages/UsersPage';
import { SettingsPage } from './pages/SettingsPage';
import { ScalePage } from './pages/ScalePage';
import { SubscriptionBlockPage } from './pages/SubscriptionBlockPage';
import type { UserRole } from './types';

// New ERP modules are lazy-loaded so the POS-critical main bundle stays lean.
const CustomersPage  = React.lazy(() => import('./pages/customers/CustomersPage').then(m => ({ default: m.CustomersPage })));
const SuppliersPage  = React.lazy(() => import('./pages/suppliers/SuppliersPage').then(m => ({ default: m.SuppliersPage })));

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const online = useAppStore((s) => s.online);
  return (
    <div className="flex h-screen overflow-hidden bg-neutral-100">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        {!online && <OfflineBanner />}
        <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
};

/** Auth + shell + optional role floor, in one wrapper. */
const Guarded: React.FC<{ children: React.ReactNode; min?: UserRole }> = ({ children, min }) => (
  <ProtectedRoute>
    <AppShell>
      {min ? <RequireRole min={min}>{children}</RequireRole> : children}
    </AppShell>
  </ProtectedRoute>
);

const Lazy: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Suspense fallback={<div className="flex-1 grid place-items-center"><LoadingState /></div>}>
    {children}
  </Suspense>
);

export const App: React.FC = () => {
  // Keep i18next + <html dir> in sync with the tenant's saved language and
  // fetch any tenant-uploaded translation overrides on auth/language change.
  useLanguageSync();

  // Hard-block the entire app shell when the backend has flagged the tenant
  // as suspended (or its trial has expired). Rendering before <Routes> means
  // no sidebar, no route content, no leakage of sensitive data.
  const blocked = useAuthStore((s) => s.subscriptionBlocked);
  if (blocked) {
    return <SubscriptionBlockPage />;
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Cashier-accessible routes */}
      <Route path="/pos" element={<Guarded><POSPage /></Guarded>} />
      <Route path="/receipt" element={<Guarded><ReceiptPage /></Guarded>} />
      <Route path="/receipt/:saleUuid" element={<Guarded><ReceiptPage /></Guarded>} />
      <Route path="/sales" element={<Guarded><SalesPage /></Guarded>} />

      {/* Manager+ routes — RequireRole renders an explicit access-denied
          screen for direct-URL attempts; the backend still 403s the APIs. */}
      <Route path="/dashboard" element={<Guarded min="Manager"><DashboardPage /></Guarded>} />
      <Route path="/products" element={<Guarded min="Manager"><ProductsPage /></Guarded>} />
      <Route path="/inventory" element={<Guarded min="Manager"><InventoryPage /></Guarded>} />
      <Route path="/scale" element={<Guarded min="Manager"><ScalePage /></Guarded>} />
      <Route path="/users" element={<Guarded min="Manager"><UsersPage /></Guarded>} />
      <Route path="/settings" element={<Guarded min="Manager"><SettingsPage /></Guarded>} />

      <Route path="/customers" element={<Guarded min="Manager"><Lazy><CustomersPage /></Lazy></Guarded>} />
      <Route path="/suppliers" element={<Guarded min="Manager"><Lazy><SuppliersPage /></Lazy></Guarded>} />

      <Route path="/" element={<Navigate to="/pos" replace />} />
      <Route path="*" element={<Navigate to="/pos" replace />} />
    </Routes>
  );
};
