import type { UserRole } from '../types';

/**
 * Frontend mirror of the backend role ladder
 * (accounts/permissions.py: IsCashierOrAbove < IsManagerOrAbove <
 * IsAdminOrAbove < IsOwner). The backend remains authoritative — these
 * helpers only decide what UI to render; every API call still gets a
 * real 403 if the role is insufficient.
 */
const ROLE_RANK: Record<UserRole, number> = {
  Cashier: 1,
  Manager: 2,
  Admin: 3,
  Owner: 4,
};

export function roleAtLeast(role: UserRole | undefined, min: UserRole): boolean {
  if (!role) return false;
  return (ROLE_RANK[role] ?? 0) >= ROLE_RANK[min];
}

export const isManagerOrAbove = (role: UserRole | undefined) => roleAtLeast(role, 'Manager');
export const isCashier = (role: UserRole | undefined) => role === 'Cashier';

/**
 * Minimum role per route path. Anything not listed only requires
 * authentication. Mirrors backend endpoint permissions:
 *  - /sales, /pos, /receipt → Cashier+ (cashiers see only their own data)
 *  - everything else → Manager+ (backend list/write endpoints are
 *    IsManagerOrAbove, or expose tenant-wide data cashiers must not see)
 */
export const ROUTE_MIN_ROLE: Record<string, UserRole> = {
  '/dashboard': 'Manager',
  '/products': 'Manager',
  '/inventory': 'Manager',
  '/warehouses': 'Manager',
  '/scale': 'Manager',
  '/users': 'Manager',
  '/settings': 'Manager',
  '/customers': 'Manager',
  '/suppliers': 'Manager',
  '/purchases': 'Manager',
  '/finance': 'Manager',
};
