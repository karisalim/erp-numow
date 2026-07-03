import React from 'react';
import { useAuthStore } from '../store/authStore';
import { roleAtLeast } from './permissions';
import { PermissionDeniedState } from '../components/ui/states';
import type { UserRole } from '../types';

/**
 * Route-level permission guard. Renders the access-denied state instead
 * of the children when the signed-in role is below `min`. Used INSIDE
 * ProtectedRoute (authentication is already guaranteed).
 *
 * Deliberately renders a denied screen rather than redirecting: a
 * cashier typing /users into the URL bar should see an explicit denial,
 * not silently land on POS and wonder what happened.
 */
export const RequireRole: React.FC<{ min: UserRole; children: React.ReactNode }> = ({
  min,
  children,
}) => {
  const role = useAuthStore((s) => s.user?.role);
  if (!roleAtLeast(role, min)) {
    return (
      <div className="flex-1 grid place-items-center p-6">
        <PermissionDeniedState />
      </div>
    );
  }
  return <>{children}</>;
};
