import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import './i18n';                              // initialise i18next once at boot
import { useLanguageSync } from './i18n/useLanguageSync';
import { useAuthStore } from './store/authStore';
import { useAppStore } from './store/appStore';
import { Sidebar } from './components/layout/Sidebar';
import { OfflineBanner } from './components/layout/OfflineBanner';
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

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { online, pendingSync } = useAppStore();
  return (
    <div className="flex h-screen overflow-hidden bg-neutral-100">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        {!online && <OfflineBanner pending={pendingSync} />}
        <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
};

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
      <Route
        path="/pos"
        element={
          <ProtectedRoute>
            <AppShell>
              <POSPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/receipt"
        element={
          <ProtectedRoute>
            <AppShell>
              <ReceiptPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <AppShell>
              <DashboardPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/products"
        element={
          <ProtectedRoute>
            <AppShell>
              <ProductsPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/inventory"
        element={
          <ProtectedRoute>
            <AppShell>
              <InventoryPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/sales"
        element={
          <ProtectedRoute>
            <AppShell>
              <SalesPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/users"
        element={
          <ProtectedRoute>
            <AppShell>
              <UsersPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <AppShell>
              <SettingsPage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/scale"
        element={
          <ProtectedRoute>
            <AppShell>
              <ScalePage />
            </AppShell>
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate to="/pos" replace />} />
      <Route path="*" element={<Navigate to="/pos" replace />} />
    </Routes>
  );
};
