import { create } from 'zustand';
import type { CartItem, Product, CompletedTransaction } from '../types';

export type PosPaymentMode = 'choose' | 'cash' | 'card' | 'wallet' | 'credit' | null;
export type PosDiscountType = 'percent' | 'fixed';

/** Minimal customer snapshot attached to the running sale. */
export interface PosCustomer {
  id: number;
  name: string;
  credit_limit: string;
}

interface PosState {
  cart: CartItem[];
  barcode: string;
  paymentMode: PosPaymentMode;
  lineCounter: number;
  flashId: string | null;
  error: string | null;
  receiptTxn: CompletedTransaction | null;
  /** Selected customer (null = walk-in). Required for credit sales. */
  customer: PosCustomer | null;
  /** Invoice-level discount (mirrors backend discount_type/discount_value). */
  discountType: PosDiscountType | null;
  discountValue: number;

  addItem: (product: Product, qty?: number) => void;
  removeItem: (lineId: string) => void;
  updateQty: (lineId: string, delta: number) => void;
  clearCart: () => void;
  setBarcode: (value: string) => void;
  setPaymentMode: (mode: PosPaymentMode) => void;
  setError: (msg: string | null) => void;
  setFlashId: (id: string | null) => void;
  setReceiptTxn: (txn: CompletedTransaction | null) => void;
  setCustomer: (customer: PosCustomer | null) => void;
  setDiscount: (type: PosDiscountType | null, value: number) => void;
}

function playBeep() {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const a = new AudioCtx();
    const o = a.createOscillator();
    const g = a.createGain();
    o.frequency.value = 880;
    o.type = 'sine';
    g.gain.value = 0.04;
    o.connect(g);
    g.connect(a.destination);
    o.start();
    o.stop(a.currentTime + 0.08);
  } catch (_) { /* silent fail */ }
}

export const usePosStore = create<PosState>((set, get) => ({
  cart: [],
  barcode: '',
  paymentMode: null,
  lineCounter: 1,
  flashId: null,
  error: null,
  receiptTxn: null,
  customer: null,
  discountType: null,
  discountValue: 0,

  addItem: (product: Product, qty = 1) => {
    const { cart, lineCounter } = get();
    playBeep();
    // Group repeats of the same product onto the same line — including
    // weighted items (multiple bananas weigh-ins should accumulate kg).
    // toFixed(3) keeps floating-point math clean for sub-gram precision.
    const existing = cart.find(x => x.id === product.id);
    if (existing) {
      set(state => ({
        cart: state.cart.map(x =>
          x.lineId === existing.lineId
            ? { ...x, qty: +(x.qty + qty).toFixed(3) }
            : x
        ),
        flashId: existing.lineId,
      }));
      setTimeout(() => set({ flashId: null }), 600);
    } else {
      const lineId = 'L' + lineCounter;
      set(state => ({
        cart: [...state.cart, { ...product, lineId, qty: +qty.toFixed(3) }],
        lineCounter: state.lineCounter + 1,
        flashId: lineId,
      }));
      setTimeout(() => set({ flashId: null }), 600);
    }
  },

  removeItem: (lineId: string) => {
    set(state => ({ cart: state.cart.filter(x => x.lineId !== lineId) }));
  },

  updateQty: (lineId: string, delta: number) => {
    set(state => ({
      cart: state.cart.map(x => {
        if (x.lineId !== lineId) return x;
        const step = x.weighted ? delta * 0.1 : delta;
        const newQty = Math.max(x.weighted ? 0.001 : 1, +(x.qty + step).toFixed(3));
        return { ...x, qty: newQty };
      }),
    }));
  },

  clearCart: () => {
    // A new sale starts clean: no carried-over customer or discount.
    set({ cart: [], barcode: '', customer: null, discountType: null, discountValue: 0 });
  },

  setBarcode: (value: string) => set({ barcode: value }),

  setPaymentMode: (mode) => set({ paymentMode: mode }),

  setError: (msg) => {
    set({ error: msg });
    if (msg) setTimeout(() => set({ error: null }), 2500);
  },

  setFlashId: (id) => set({ flashId: id }),

  setReceiptTxn: (txn) => set({ receiptTxn: txn }),

  setCustomer: (customer) => set({ customer }),

  setDiscount: (type, value) =>
    set({ discountType: type, discountValue: type ? Math.max(0, value) : 0 }),
}));
