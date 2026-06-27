import { create } from 'zustand';

interface AppState {
  online: boolean;
  pendingSync: number;
  currentRoute: string;
  setOnline: (value: boolean | ((prev: boolean) => boolean)) => void;
  incrementPendingSync: () => void;
  setRoute: (route: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  online: true,
  pendingSync: 0,
  currentRoute: 'pos',

  setOnline: (value) => {
    set(state => ({
      online: typeof value === 'function' ? value(state.online) : value,
    }));
  },

  incrementPendingSync: () => {
    set(state => ({ pendingSync: state.pendingSync + 1 }));
  },

  setRoute: (route: string) => set({ currentRoute: route }),
}));
