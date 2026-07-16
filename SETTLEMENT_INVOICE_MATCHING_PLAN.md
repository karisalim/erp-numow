# خطة: مطابقة الدفعات على مستوى الفاتورة (Settlement Invoice Matching)

**الحالة: تخطيط فقط — لم يُنفَّذ أي كود بعد.** بُنيت هذه الخطة بعد مقارنة مباشرة
بين شاشتَي "دفع نقدية" / "استلام نقدية" في DEXEF وشاشاتنا المكافئة
(`SettlementFormModal.tsx` + `CustomerReceipt`/`SupplierPayment` في الباك إند).

---

## 1. الفجوة بالضبط

نظامنا الحالي: الدفعة/الاستلام مبلغ واحد يُقيَّد على **الرصيد الجاري**
للعميل/المورد (`CustomerARMovement`/`SupplierAPMovement`) — تمامًا زي حساب بنكي.
لا يوجد أي ربط بين الدفعة وفاتورة بيع/شراء بعينها. مؤكَّد من الكود:
`CustomerReceipt`/`SupplierPayment` (`accounts/models.py:956-1000`) لا يحملان أي FK
لـ `Sale` أو `PurchaseInvoice`، ولا يوجد جدول تخصيص (allocation) في المشروع كله.

DEXEF: كل دفعة/استلام تُطابَق صراحةً مقابل مستند أو أكثر من المستندات المفتوحة —
جدول كامل بكل الفواتير غير المسوّاة، مع إمكانية تحديد ("تم") أي فواتير بالظبط
تتغطى بالمبلغ، أو زرار "تسوية تلقائية" يوزّع المبلغ تلقائيًا (الأقدم أولًا عادة).

هذا فرق معماري حقيقي، مش مجرد نقص في الفرونت إند — الـ API نفسه لا يحمل
البيانات اللازمة لهذا التطابق.

---

## 2. التصميم المقترح (Backend)

### 2.1 موديلان جديدان (additive فقط، بدون أي تعديل على الموديلات الحالية)

يتبعان نفس نمط الثنائيات الموجود فعليًا (`CustomerReceipt`/`SupplierPayment`
كثنائي مبني على `_SettlementDocumentBase`) — ثنائي مماثل بدل FK عام
(GenericForeignKey) غير مستخدم في أي مكان بالمشروع حاليًا:

```python
class CustomerReceiptAllocation(models.Model):
    tenant          = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='+')
    receipt         = models.ForeignKey(CustomerReceipt, on_delete=models.CASCADE, related_name='allocations')
    sale            = models.ForeignKey('pos.Sale', on_delete=models.PROTECT, related_name='receipt_allocations')
    applied_amount  = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(applied_amount__gt=0), name='cra_amount_positive'),
        ]

class SupplierPaymentAllocation(models.Model):
    tenant          = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='+')
    payment         = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, related_name='allocations')
    purchase_invoice = models.ForeignKey('pos.PurchaseInvoice', on_delete=models.PROTECT, related_name='payment_allocations')
    applied_amount  = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(applied_amount__gt=0), name='spa_amount_positive'),
        ]
```

- `sum(allocations.applied_amount) == receipt.amount` — يُتحقَّق منه في service
  layer (constraint متعدد الصفوف مش ممكن كـ DB CHECK)، مش في الـ serializer،
  بنفس فلسفة `create_customer_receipt`/`create_supplier_payment` الحاليين.
- Migration واحدة إضافية بحتة — لا تعديل على أي جدول موجود، لا بيانات.

### 2.2 Endpoint جديد: "الفواتير المفتوحة"

```
GET /api/customers/<id>/open-invoices/
GET /api/suppliers/<id>/open-invoices/
```

يرجّع كل `Sale`/`PurchaseInvoice` لهذا العميل/المورد التي `remaining_due > 0`
(المبلغ الإجمالي − مجموع التخصيصات المرحّلة عليها حتى الآن)، بترتيب الأقدم أولًا:

```json
[{ "id": 953, "doc_number": "SALE-953", "date": "2023-12-06",
   "total": "100.00", "paid_so_far": "0.00", "remaining_due": "100.00" }]
```

`remaining_due` محسوبة (annotate)، مش عمود مخزَّن — نفس فلسفة `AccountBalance`
الحالية (`/finance/accounts/<id>/balance/`) اللي بتحسب من حركات الليدجر بدل
تخزين رصيد مباشر.

### 2.3 تمديد إنشاء الدفعة/الاستلام (اختياري تمامًا، توافق خلفي كامل)

`create_customer_receipt`/`create_supplier_payment` يقبلوا حقل إضافي اختياري:

```json
{ "amount": "150.00", "allocations": [
    { "sale": 953, "amount": "100.00" },
    { "sale": 948, "amount": "50.00" }
], "auto_allocate": false }
```

- لو `allocations` مش موجودة أو فاضية → **نفس السلوك الحالي بالظبط** (رصيد جاري
  بس، بدون أي صف تخصيص) — صفر كسر توافق مع أي دفعة قديمة أو مسار حالي.
- لو `auto_allocate: true` → دالة خدمة جديدة توزّع المبلغ تلقائيًا على الفواتير
  المفتوحة الأقدم أولًا (FIFO)، بنفس روح زرار "تسوية الاستحقاقات تلقائياً" في
  DEXEF.
- تحقق: مجموع `allocations` يساوي `amount` بالظبط، كل فاتورة تخص نفس العميل/المورد
  ونفس التينانت، `applied_amount` لا يتجاوز `remaining_due` وقت الإرسال.

---

## 3. التصميم المقترح (Frontend)

- توسعة `SettlementFormModal.tsx`: بعد اختيار الطريقة/الحساب/المبلغ، خطوة تانية
  اختيارية — جدول الفواتير المفتوحة (`customersApi.openInvoices` /
  `suppliersApi.openInvoices`)، كل صف فيه checkbox أو حقل مبلغ قابل للتعديل،
  وإجمالي "المخصَّص" لازم يساوي المبلغ المدخل قبل ما زرار الحفظ يتفعّل.
- زرار "تسوية تلقائية" يبعت `auto_allocate: true` بدل بناء القايمة يدويًا.
- لو المستخدم مش عاوز يخصص (زي السلوك الحالي بالظبط) — يسيب الجدول فاضي ويحفظ
  عادي، بيترحّل كرصيد جاري زي ما هو دلوقتي.

---

## 4. حجم العمل التقريبي

| الجزء | التقدير |
|---|---|
| موديلين + migration | صغير |
| `open-invoices` endpoints (×2) + `remaining_due` annotation | متوسط |
| تمديد `create_customer_receipt`/`create_supplier_payment` + auto-allocate + اختبارات | متوسط–كبير |
| فرونت إند (جدول التخصيص + زرار التسوية التلقائية) | متوسط |
| **الإجمالي** | يعادل تقريبًا حجم دفعة Sprint 2 واحدة من اللي نفذناها (زي Batch 5a) |

---

## 5. خارج نطاق هذه الخطة

- ربط `Customer.price_tier_id`/`BranchSettings.default_price_tier_id` — غير
  متعلق، مذكور في خطة Sprint 2 سابقة بشكل منفصل.
- عرض عملات متعددة لكل خزينة في نفس الشاشة (DEXEF بتعرض EGP/USD/SAR في نفس
  القائمة) — نظامنا الحالي عملة واحدة لكل حساب، توسعته موضوع منفصل.
