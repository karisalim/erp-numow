import type { Product, Transaction, AppUser } from '../types';

export const PRODUCTS: Product[] = [
  { id: 'p1',  barcode: '5410188006353', sku: 'BVR-001',     name: 'Coca-Cola 330ml',        category: 'Beverages',     price: 1.20, cost: 0.50, tax: 0.10, stock: 148, reorder: 50,  color: '#dc2626' },
  { id: 'p2',  barcode: '8410076473219', sku: 'BAK-014',     name: 'Bimbo White Bread 600g', category: 'Bakery',        price: 2.45, cost: 1.10, tax: 0.05, stock: 32,  reorder: 20,  color: '#f59e0b' },
  { id: 'p3',  barcode: '8480000200013', sku: 'DAR-007',     name: 'Hacendado Milk 1L',      category: 'Dairy',         price: 0.95, cost: 0.45, tax: 0.05, stock: 86,  reorder: 40,  color: '#60a5fa' },
  { id: 'p4',  barcode: '21100401234',   sku: 'MET-PLU1001', name: 'Beef Steak (kg)',         category: 'Meat',          price: 18.50,cost: 11.00,tax: 0.10, stock: 14,  reorder: 10,  color: '#991b1b', weighted: true, plu: '10040' },
  { id: 'p5',  barcode: '8410297121023', sku: 'SNK-022',     name: 'Lays Classic 150g',      category: 'Snacks',        price: 2.10, cost: 0.95, tax: 0.10, stock: 74,  reorder: 30,  color: '#facc15' },
  { id: 'p6',  barcode: '5449000000996', sku: 'BVR-003',     name: 'Sprite 500ml',           category: 'Beverages',     price: 1.45, cost: 0.55, tax: 0.10, stock: 9,   reorder: 25,  color: '#16a34a' },
  { id: 'p7',  barcode: '8001505005707', sku: 'PAS-008',     name: 'Barilla Spaghetti 500g', category: 'Pasta',         price: 1.85, cost: 0.80, tax: 0.05, stock: 122, reorder: 30,  color: '#1e40af' },
  { id: 'p8',  barcode: '5060337502016', sku: 'CHO-019',     name: 'Cadbury Dairy Milk 80g', category: 'Snacks',        price: 1.65, cost: 0.70, tax: 0.10, stock: 0,   reorder: 20,  color: '#7c2d12' },
  { id: 'p9',  barcode: '8410057014104', sku: 'PRD-002',     name: 'Bananas (kg)',            category: 'Produce',       price: 1.49, cost: 0.60, tax: 0.05, stock: 38,  reorder: 20,  color: '#eab308', weighted: true, plu: '10041' },
  { id: 'p10', barcode: '8480000823014', sku: 'HSE-031',     name: 'Olive Oil 1L',           category: 'Pantry',        price: 7.90, cost: 4.50, tax: 0.10, stock: 42,  reorder: 15,  color: '#65a30d' },
  { id: 'p11', barcode: '4009900522861', sku: 'CON-009',     name: 'Orbit Gum 14pcs',        category: 'Confectionery', price: 1.30, cost: 0.45, tax: 0.10, stock: 6,   reorder: 25,  color: '#06b6d4' },
  { id: 'p12', barcode: '8000500037560', sku: 'CHO-020',     name: 'Nutella 400g',           category: 'Pantry',        price: 4.95, cost: 2.80, tax: 0.10, stock: 54,  reorder: 20,  color: '#78350f' },
];

export const QUICK_GRID_IDS = ['p1', 'p3', 'p5', 'p2', 'p9', 'p7', 'p10', 'p12'];

export const QUICK_GRID: Product[] = QUICK_GRID_IDS.map(
  id => PRODUCTS.find(p => p.id === id) as Product
);

export const TRANSACTIONS: Transaction[] = [
  { id: 'TXN-481209', ts: '2026-05-11 14:32', cashier: 'Ahmed H.',  items: 4,  method: 'card',   total: 38.45,  status: 'Completed' },
  { id: 'TXN-481208', ts: '2026-05-11 14:28', cashier: 'Sara M.',   items: 7,  method: 'cash',   total: 52.10,  status: 'Completed' },
  { id: 'TXN-481207', ts: '2026-05-11 14:21', cashier: 'Ahmed H.',  items: 2,  method: 'wallet', total: 14.80,  status: 'Completed' },
  { id: 'TXN-481206', ts: '2026-05-11 14:15', cashier: 'Sara M.',   items: 11, method: 'card',   total: 87.30,  status: 'Completed' },
  { id: 'TXN-481205', ts: '2026-05-11 14:09', cashier: 'Ahmed H.',  items: 3,  method: 'cash',   total: 21.45,  status: 'Voided'    },
  { id: 'TXN-481204', ts: '2026-05-11 14:02', cashier: 'Karim O.',  items: 5,  method: 'card',   total: 45.90,  status: 'Completed' },
  { id: 'TXN-481203', ts: '2026-05-11 13:54', cashier: 'Sara M.',   items: 8,  method: 'cash',   total: 63.75,  status: 'Refunded'  },
  { id: 'TXN-481202', ts: '2026-05-11 13:48', cashier: 'Ahmed H.',  items: 1,  method: 'wallet', total: 7.90,   status: 'Completed' },
  { id: 'TXN-481201', ts: '2026-05-11 13:41', cashier: 'Karim O.',  items: 6,  method: 'card',   total: 34.20,  status: 'Completed' },
  { id: 'TXN-481200', ts: '2026-05-11 13:33', cashier: 'Sara M.',   items: 9,  method: 'cash',   total: 71.55,  status: 'Completed' },
  { id: 'TXN-481199', ts: '2026-05-11 13:24', cashier: 'Ahmed H.',  items: 4,  method: 'card',   total: 28.40,  status: 'Completed' },
  { id: 'TXN-481198', ts: '2026-05-11 13:18', cashier: 'Karim O.',  items: 12, method: 'card',   total: 104.85, status: 'Completed' },
  { id: 'TXN-481197', ts: '2026-05-11 13:09', cashier: 'Sara M.',   items: 2,  method: 'cash',   total: 12.30,  status: 'Completed' },
  { id: 'TXN-481196', ts: '2026-05-11 13:01', cashier: 'Ahmed H.',  items: 5,  method: 'wallet', total: 39.50,  status: 'Completed' },
  { id: 'TXN-481195', ts: '2026-05-11 12:54', cashier: 'Karim O.',  items: 7,  method: 'card',   total: 48.65,  status: 'Completed' },
];

// `branch` is now typed `number | null` on `AppUser` (backend FK id). The
// display label moved to `branch_name`; mock rows use `null` for the id so
// they still satisfy the type while preserving the original demo strings.
// `username` and `is_active` are also required by `AppUser` — derived from
// the existing email local-part and the legacy `active` flag respectively,
// so runtime behavior of any consumer is unchanged.
export const USERS: AppUser[] = [
  { id: 'u1', username: 'mohamed', name: 'Mohamed Sayed', email: 'mohamed@superpos.io', role: 'Owner',   branch: null, branch_name: 'All branches',        last: 'Active now',   active: true,  is_active: true  },
  { id: 'u2', username: 'layla',   name: 'Layla Hassan',  email: 'layla@superpos.io',   role: 'Admin',   branch: null, branch_name: 'Cairo Downtown #03',  last: '12 min ago',   active: true,  is_active: true  },
  { id: 'u3', username: 'ahmed',   name: 'Ahmed H.',      email: 'ahmed@superpos.io',   role: 'Cashier', branch: null, branch_name: 'Cairo Downtown #03',  last: 'Active now',   active: true,  is_active: true  },
  { id: 'u4', username: 'sara',    name: 'Sara Mostafa',  email: 'sara@superpos.io',    role: 'Cashier', branch: null, branch_name: 'Cairo Downtown #03',  last: 'Active now',   active: true,  is_active: true  },
  { id: 'u5', username: 'karim',   name: 'Karim Othman',  email: 'karim@superpos.io',   role: 'Cashier', branch: null, branch_name: 'Alexandria Port #01', last: '2 hours ago',  active: true,  is_active: true  },
  { id: 'u6', username: 'nadia',   name: 'Nadia Farouk',  email: 'nadia@superpos.io',   role: 'Manager', branch: null, branch_name: 'Alexandria Port #01', last: 'Yesterday',    active: true,  is_active: true  },
  { id: 'u7', username: 'omar',    name: 'Omar Khaled',   email: 'omar@superpos.io',    role: 'Manager', branch: null, branch_name: 'Giza Pyramids #02',   last: '3 days ago',   active: false, is_active: false },
  { id: 'u8', username: 'yasmin',  name: 'Yasmin Ali',    email: 'yasmin@superpos.io',  role: 'Cashier', branch: null, branch_name: 'Giza Pyramids #02',   last: '1 week ago',   active: false, is_active: false },
];

export const PERMISSIONS: Record<string, number[]> = {
  Owner:   [1, 1, 1, 1, 1, 1],
  Admin:   [1, 1, 1, 1, 1, 0],
  Manager: [1, 1, 1, 1, 0, 0],
  Cashier: [1, 0, 0, 0, 0, 0],
};

export const PERMISSION_LABELS = [
  'sales:create',
  'sales:void',
  'products:edit',
  'reports:view',
  'users:manage',
  'settings:edit',
];
