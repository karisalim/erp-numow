import React, { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { LoadingState, QueryErrorState, AlertBanner } from '../../components/ui/states';
import { DocumentStatusHeader } from '../../components/erp/DocumentStatusHeader';
import { MovementEffectsCard, type MovementEffect } from '../../components/erp/MovementEffectsCard';
import { purchasesApi, inventoryCostApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { fmtDecimal } from '../../utils/format';
import type { InventoryCostMovement } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Purchase invoice detail. Posted invoices are READ-ONLY by contract —
 * there are no update/delete endpoints, so no edit actions are rendered.
 * ──────────────────────────────────────────────────────────────────────────── */

export const PurchaseDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const money = useMoney();

  const q = useQuery(() => purchasesApi.get(Number(id)), [id]);
  const inv = q.data;

  // Purchase invoice lines never carry before/after avg cost themselves
  // (that's an InventoryCostMovement concern, not a PurchaseInvoiceLine
  // field) — look it up separately per distinct stock-item product on the
  // invoice. This is a targeted, page-1-only lookup (not a full browse —
  // see ProductCostHistoryDrawer for that), so a very old/buried movement
  // for a high-volume product could in principle not surface here; the
  // generic sentence below is the graceful fallback for that case.
  const productIds = useMemo(() => {
    if (!inv) return [];
    const ids = new Set<number>();
    inv.lines.forEach((l) => { if (l.line_type === 'stock_item' && l.product) ids.add(l.product); });
    return Array.from(ids);
  }, [inv]);

  const movementsQ = useQuery(
    () => productIds.length === 0
      ? Promise.resolve<InventoryCostMovement[]>([])
      : Promise.all(productIds.map((pid) => inventoryCostApi.listMovements(pid).then((p) => p.results))).then((lists) => lists.flat()),
    [inv?.id],
  );

  const productNameById = useMemo(() => {
    const map = new Map<number, string>();
    inv?.lines.forEach((l) => { if (l.product) map.set(l.product, l.product_name); });
    return map;
  }, [inv]);

  const costMatches = useMemo(() => {
    if (!inv || !movementsQ.data) return [];
    const matches = movementsQ.data.filter(
      (m) => m.source_document_type === 'purchase_invoice' && m.source_document_id === inv.id,
    );
    const byProduct = new Map<number, InventoryCostMovement>();
    matches.forEach((m) => { if (!byProduct.has(m.product)) byProduct.set(m.product, m); });
    return Array.from(byProduct.values());
  }, [inv, movementsQ.data]);

  const effects: MovementEffect[] = [];
  if (inv && inv.posting_status === 'posted') {
    const stockLines = inv.lines.filter((l) => l.line_type === 'stock_item');
    if (stockLines.length > 0) {
      if (costMatches.length > 0) {
        costMatches.forEach((m) => {
          const name = productNameById.get(m.product) ?? `product #${m.product}`;
          effects.push({
            badge: 'Stock',
            badgeKind: 'brand',
            text: (
              <>
                AVCO cost for <b>{name}</b> moved {money(m.avg_cost_before)} → {money(m.avg_cost_after)}
                {m.quantity_received != null && <> (received {fmtDecimal(m.quantity_received)})</>}.
              </>
            ),
          });
        });
      } else {
        effects.push({
          badge: 'Stock',
          badgeKind: 'brand',
          text: <>PURCHASE_IN for {stockLines.length} line(s) — quantities received and moving-average cost updated.</>,
        });
      }
    }
    if (Number(inv.paid_amount) > 0) {
      effects.push({
        badge: 'Payment',
        badgeKind: 'success',
        text: <>{money(inv.paid_amount)} paid from source account{inv.source_account ? ` #${inv.source_account}` : ''}.</>,
      });
    }
    if (Number(inv.credit_amount) > 0) {
      effects.push({
        badge: 'AP',
        badgeKind: 'warn',
        text: <>SupplierAPMovement +{money(inv.credit_amount)} — remainder owed to {inv.supplier_name}.</>,
      });
    }
    if (Number(inv.tax_total) > 0) {
      effects.push({
        badge: 'Tax',
        badgeKind: 'gray',
        text: <>Tax total {money(inv.tax_total)} recorded on the document (no separate tax ledger posting in this slice).</>,
      });
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Purchase invoice" subtitle={inv ? `PUR-${inv.id} · ${inv.supplier_name}` : ''} />
      <div className="p-5 max-w-[980px] w-full mx-auto">
        <Button variant="ghost" size="sm" className="mb-3" onClick={() => navigate('/purchases')}>
          <Icon name="chevL" size={15} className="rtl:rotate-180" /> Back to purchases
        </Button>

        {q.loading && <LoadingState />}
        {q.error && <QueryErrorState error={q.error} onRetry={q.refetch} />}

        {inv && (
          <div className="space-y-4">
            <Card>
              <DocumentStatusHeader
                docNumber={`PUR-${inv.id}`}
                context={
                  <>
                    {inv.supplier_name} · {inv.branch_name}
                    {inv.posted_at && <> · posted {new Date(inv.posted_at).toLocaleString()}</>}
                    {inv.reference && <> · ref {inv.reference}</>}
                  </>
                }
                postingStatus={inv.posting_status}
                paymentStatus={inv.payment_status}
              />
              <div className="px-5 py-2">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px]">
                    <thead>
                      <tr>
                        {['Product', 'Qty', 'Unit cost', 'Discount', 'Tax', 'Line total'].map((h, i) => (
                          <th key={h} className={`text-[11px] uppercase tracking-wider text-neutral-500 font-bold py-2 border-b border-neutral-200 ${i === 0 ? 'text-start' : 'text-end'}`}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {inv.lines.map((l) => (
                        <tr key={l.id}>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] font-semibold">{l.product_name}</td>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] text-end font-mono">{fmtDecimal(l.qty)}</td>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] text-end font-mono">{money(l.unit_cost)}</td>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] text-end font-mono">{Number(l.discount_amount) ? money(l.discount_amount) : '—'}</td>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] text-end font-mono">{Number(l.tax_amount) ? money(l.tax_amount) : '—'}</td>
                          <td className="py-2.5 border-b border-neutral-100 text-[13.5px] text-end font-mono font-bold">{money(l.line_total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="py-3 space-y-1 text-[13px]">
                  <div className="flex justify-between"><span className="text-neutral-500">Subtotal</span><span className="font-mono">{money(inv.subtotal)}</span></div>
                  {Number(inv.discount_total) > 0 && (
                    <div className="flex justify-between"><span className="text-neutral-500">Discount</span><span className="font-mono">−{money(inv.discount_total)}</span></div>
                  )}
                  {Number(inv.tax_total) > 0 && (
                    <div className="flex justify-between"><span className="text-neutral-500">Tax</span><span className="font-mono">{money(inv.tax_total)}</span></div>
                  )}
                  <div className="flex justify-between pt-2 border-t border-neutral-200 text-[15px] font-extrabold">
                    <span>Total</span><span className="font-mono">{money(inv.total_amount)}</span>
                  </div>
                  <div className="flex justify-between"><span className="text-neutral-500">Paid</span><span className="font-mono">{money(inv.paid_amount)}</span></div>
                  <div className="flex justify-between"><span className="text-neutral-500">On credit (AP)</span><span className="font-mono">{money(inv.credit_amount)}</span></div>
                </div>
              </div>
            </Card>

            {inv.notes && (
              <Card>
                <CardHeader title="Notes" />
                <CardBody className="text-[13px] text-neutral-700 whitespace-pre-wrap">{inv.notes}</CardBody>
              </Card>
            )}

            <MovementEffectsCard effects={effects} />

            {inv.posting_status === 'posted' && (
              <AlertBanner tone="info">
                Posted invoices are read-only. Corrections require a compensating document (purchase return — future slice).
              </AlertBanner>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
