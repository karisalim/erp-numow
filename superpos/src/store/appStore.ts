import { create } from 'zustand';

/**
 * App shell state.
 *
 * `online` reflects the real browser connectivity signal
 * (navigator.onLine + online/offline events). It is display-only — there
 * is NO offline queue: sales always post to the backend, and the UI must
 * never claim local persistence that doesn't exist. The previous manually
 * toggled offline simulation and fake pending-sync counter were removed
 * (frontend audit P0-03).
 */
interface AppState {
  online: boolean;
  sidebarOpen: boolean;      // mobile/tablet overlay sidebar
  currentRoute: string;
  setOnline: (value: boolean) => void;
  setSidebarOpen: (open: boolean) => void;
  setRoute: (route: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  online: typeof navigator !== 'undefined' ? navigator.onLine : true,
  sidebarOpen: false,
  currentRoute: 'pos',

  setOnline: (value) => set({ online: value }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setRoute: (route: string) => set({ currentRoute: route }),
}));

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => useAppStore.getState().setOnline(true));
  window.addEventListener('offline', () => useAppStore.getState().setOnline(false));
}
