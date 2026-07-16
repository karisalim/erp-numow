import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import apiClient from '../api/client';
import { usePosStore } from '../store/posStore';
import { useAuthStore } from '../store/authStore';
import { fmtDate } from '../utils/format';
import { absoluteMediaUrl } from '../utils/media';
import { saleDetailToTxn, type SaleDetail } from '../utils/sale';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Icon } from '../components/ui/Icon';
import { LoadingState } from '../components/ui/states';

// Currency formatter — uses the tenant's configured currency, fallback EGP.
const money = (n: number | string | null | undefined, currency: string): string => {
  const num = typeof n === 'number' ? n : Number(n ?? 0);
  return `${currency} ${Number.isFinite(num) ? num.toFixed(2) : '0.00'}`;
};

export const ReceiptPage: React.FC = () => {
  const navigate = useNavigate();
  const { saleUuid } = useParams<{ saleUuid: string }>();
  const { receiptTxn, setReceiptTxn } = usePosStore();
  const user = useAuthStore((s) => s.user);
  const currency = user?.tenant_currency || 'EGP';
  const showTax  = user?.tenant_show_tax_on_receipt !== false;
  const logoUrl  = absoluteMediaUrl(user?.tenant_logo);
  const phones   = (user?.tenant_phone ?? '')
    .split(/[,;]+/)
    .map((p) => p.trim())
    .filter(Boolean);

  // Durable receipt: when the in-memory transaction is gone (page refresh,
  // deep link) but the URL carries the sale UUID, refetch the sale and
  // rebuild the receipt instead of silently bouncing back to the POS.
  const needsFetch = !receiptTxn && !!saleUuid;
  const [fetching, setFetching]   = useState(needsFetch);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    if (!needsFetch) return;
    let cancelled = false;
    setFetching(true);
    apiClient.get<SaleDetail>(`/sales/${saleUuid}/`)
      .then((res) => { if (!cancelled) setReceiptTxn(saleDetailToTxn(res.data)); })
      .catch(() => { if (!cancelled) setFetchError('Could not load this receipt. It may not exist or you may not have access.'); })
      .finally(() => { if (!cancelled) setFetching(false); });
    return () => { cancelled = true; };
  }, [needsFetch, saleUuid, setReceiptTxn]);

  // Auto-trigger the browser's print dialog as soon as the receipt mounts.
  // Wrapped in a short timeout so the receipt has a frame to paint first.
  useEffect(() => {
    if (!receiptTxn) return;
    const t = setTimeout(() => window.print(), 250);
    return () => clearTimeout(t);
  }, [receiptTxn]);

  if (!receiptTxn) {
    if (fetching) {
      return <div className="flex-1 grid place-items-center"><LoadingState /></div>;
    }
    if (fetchError) {
      return (
        <div className="flex-1 grid place-items-center p-8">
          <Card className="p-6 max-w-[420px] text-center">
            <div className="text-[15px] font-semibold text-danger-600">{fetchError}</div>
            <Button className="mt-4" onClick={() => navigate('/pos')}>Back to POS</Button>
          </Card>
        </div>
      );
    }
    navigate('/pos', { replace: true });
    return null;
  }

  const txn = receiptTxn;
  const dStr = fmtDate(txn.ts);

  const fullId  = txn.sale_uuid ?? String(txn.id);
  const shortId = fullId.slice(-8);

  const storeName    = user?.tenant_name   || 'Supermarket';
  const branchName   = user?.branch_name   || 'Main Branch';
  const terminalName = txn.terminal        || user?.terminal_name || 'POS-01';

  const handleDone = () => {
    setReceiptTxn(null);
    navigate('/pos');
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-neutral-100">
      <Header
        title="Receipt preview"
        subtitle={`Transaction #${shortId}`}
        right={
          <Button variant="ghost" size="sm" onClick={handleDone}>
            <Icon name="x" size={14} /> Close
          </Button>
        }
      />
      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-[920px] mx-auto grid grid-cols-5 gap-6">
          {/* Receipt */}
          <div className="col-span-3">
            <div className="bg-white shadow-md rounded-md p-7 receipt print-area mx-auto" style={{ maxWidth: 380 }}>
              <div className="text-center">
                {logoUrl ? (
                  <img
                    src={logoUrl}
                    alt={storeName}
                    className="receipt-logo mx-auto mb-1"
                  />
                ) : (
                  <div className="text-[16px] font-bold tracking-wide uppercase">{storeName}</div>
                )}
                <div className="text-[12px]">{branchName}</div>
                {user?.tenant_address && (
                  <div className="text-[12px]">{user.tenant_address}</div>
                )}
                {showTax && user?.tenant_vat_number && (
                  <div className="text-[12px]">VAT: {user.tenant_vat_number}</div>
                )}
              </div>
              <div className="dashed" />
              <div className="text-[12px]">
                <div className="flex justify-between">
                  <span>{dStr}</span>
                  <span>#{shortId}</span>
                </div>
                <div className="flex justify-between">
                  <span>Cashier: {txn.cashier}</span>
                  <span>{terminalName}</span>
                </div>
              </div>
              <div className="dashed" />
              <div className="text-[12px]">
                <div className="flex font-bold pb-1">
                  <span className="flex-1">ITEM</span>
                  <span className="w-10 text-right">QTY</span>
                  <span className="w-20 text-right">TOTAL</span>
                </div>
                {txn.items.map((it, i) => {
                  // DRF returns Decimal as string ("12.50"); real API products use
                  // `tax_rate`, legacy mock items use `tax`. Coerce both safely.
                  const price = Number(it.price);
                  const taxRate = Number(it.tax ?? it.tax_rate ?? 0);
                  return (
                    <div key={i} className="py-0.5">
                      <div className="flex">
                        <span className="flex-1 truncate pr-1">
                          {it.name.toUpperCase()}{it.unitLabel ? ` (${it.unitLabel.toUpperCase()})` : ''}
                        </span>
                        <span className="w-10 text-right">{it.qty}{it.weighted ? 'kg' : ''}</span>
                        <span className="w-20 text-right">{(it.qty * price).toFixed(2)}</span>
                      </div>
                      <div className="text-[11px] text-[#666] pl-1">
                        @ {price.toFixed(2)}{it.weighted ? '/kg' : it.unitLabel ? `/${it.unitLabel}` : ''}
                        {showTax ? `  ·  VAT ${(taxRate * 100).toFixed(0)}%` : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="dashed" />
              <div className="text-[12px]">
                <div className="flex justify-between"><span>Subtotal</span><span>{txn.subtotal.toFixed(2)}</span></div>
                {showTax && (
                  <div className="flex justify-between"><span>VAT</span><span>{txn.tax.toFixed(2)}</span></div>
                )}
                {(txn.discount ?? 0) > 0 && (
                  <div className="flex justify-between"><span>Discount</span><span>-{(txn.discount ?? 0).toFixed(2)}</span></div>
                )}
                <div className="flex justify-between font-bold text-[14px] pt-1">
                  <span>TOTAL</span><span>{money(txn.total, currency)}</span>
                </div>
              </div>
              <div className="dashed" />
              <div className="text-[12px]">
                {txn.method === 'credit' ? (
                  <>
                    <div className="flex justify-between font-bold">
                      <span>ON CREDIT</span>
                      <span>{txn.total.toFixed(2)}</span>
                    </div>
                    {txn.customer_name && (
                      <div className="flex justify-between">
                        <span>Customer</span><span>{txn.customer_name}</span>
                      </div>
                    )}
                    <div className="text-[11px] text-[#666]">Added to customer balance — payable later</div>
                  </>
                ) : (
                  <>
                    <div className="flex justify-between">
                      <span>Paid ({txn.method.toUpperCase()})</span>
                      <span>{txn.paid.toFixed(2)}</span>
                    </div>
                    {txn.method === 'cash' && (
                      <div className="flex justify-between">
                        <span>Change</span><span>{txn.change.toFixed(2)}</span>
                      </div>
                    )}
                  </>
                )}
              </div>
              <div className="dashed" />
              <div className="text-center text-[12px]">
                {user?.tenant_receipt_footer ? (
                  user.tenant_receipt_footer.split('\n').map((line, i) => (
                    <div key={i}>{line}</div>
                  ))
                ) : (
                  <>
                    <div>Thank you for shopping!</div>
                    <div>Returns within 14 days w/ receipt</div>
                  </>
                )}
                {phones.length > 0 && (
                  <div className="mt-1">
                    {phones.map((p, i) => (
                      <div key={i} className="font-mono">{p}</div>
                    ))}
                  </div>
                )}
                <div className="mt-2 font-mono text-[10px] break-all">Ref: {fullId.toLowerCase()}</div>
                <div className="mt-2 text-[10px]">** CUSTOMER COPY **</div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="col-span-2 flex flex-col gap-3">
            <Card className="p-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-success-50 grid place-items-center text-success-600">
                  <Icon name="check" size={22} />
                </div>
                <div>
                  <div className="text-[15px] font-semibold">Sale recorded</div>
                  <div className="text-[12px] text-neutral-500">Inventory updated</div>
                </div>
              </div>
            </Card>

            {/* Printing goes through the browser's print dialog — there is no
                direct thermal-printer integration in this version, so no
                device status is shown. */}
            <Card className="p-5">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">Print</div>
              <p className="text-[12.5px] text-neutral-500 mb-3">
                Uses the browser print dialog and your system's default printer.
              </p>
              <Button variant="secondary" size="md" className="w-full" onClick={() => window.print()}>
                <Icon name="printer" size={16} /> Print Receipt
              </Button>
            </Card>

            <Card className="p-5">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-3">Summary</div>
              <div className="space-y-1.5 text-[13px]">
                <div className="flex justify-between">
                  <span className="text-neutral-500">Items</span>
                  <span className="font-mono tabular-nums">{txn.items.reduce((s, i) => s + i.qty, 0).toFixed(0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Method</span>
                  <span className="font-semibold capitalize">{txn.method}</span>
                </div>
                {txn.customer_name && (
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Customer</span>
                    <span className="font-semibold">{txn.customer_name}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-neutral-500">Total</span>
                  <span className="font-mono tabular-nums font-semibold">{money(txn.total, currency)}</span>
                </div>
                {txn.method === 'cash' && (
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Change</span>
                    <span className="font-mono tabular-nums">{money(txn.change, currency)}</span>
                  </div>
                )}
                {txn.method === 'credit' && (
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Payment</span>
                    <span className="font-semibold text-warn-700">On customer balance</span>
                  </div>
                )}
              </div>
            </Card>

            <Button size="xl" onClick={handleDone}>
              New transaction <Icon name="chevR" size={18} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
