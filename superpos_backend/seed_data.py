"""
Seed script — run with:  python seed_data.py
(from inside superpos_backend/)
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'superpos_backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Tenant, Branch, Terminal
from pos.models import Category, Product, InventoryBatch, Sale, SaleItem, StockMovement

User = get_user_model()

# ── Load fixtures ──────────────────────────────────────────────────────────────
tenant   = Tenant.objects.get(pk=1)
branch   = Branch.objects.get(pk=1)
terminal = Terminal.objects.get(pk=2)
karim    = User.objects.get(pk=1)
ziad     = User.objects.get(pk=2)
mohamed  = User.objects.get(pk=4)

now       = timezone.now()
today     = now.replace(hour=0, minute=0, second=0, microsecond=0)

print("[1] Users and tenant loaded")

# ── Categories ─────────────────────────────────────────────────────────────────

cat_burgers = Category.objects.get(pk=1)
cat_drinks  = Category.objects.get(pk=2)
for c in [cat_burgers, cat_drinks]:
    if not c.tenant_id:
        c.tenant = tenant
        c.save()

cat_dairy,  _ = Category.objects.get_or_create(name="Dairy",   defaults={"tenant": tenant})
cat_snacks, _ = Category.objects.get_or_create(name="Snacks",  defaults={"tenant": tenant})
cat_fruits, _ = Category.objects.get_or_create(name="Fruits & Vegetables", defaults={"tenant": tenant})

print("[2] Categories ready")

# ── Products ───────────────────────────────────────────────────────────────────

def make_product(barcode, sku, name, cat, price, cost, stock, reorder,
                 tax=Decimal("0.14"), weighted=False,
                 unit=None, color="#2563eb"):
    if unit is None:
        unit = Product.Unit.PIECE
    p, created = Product.objects.get_or_create(
        barcode=barcode,
        defaults=dict(
            tenant=tenant, sku=sku, name=name, category=cat,
            price=Decimal(str(price)), cost=Decimal(str(cost)),
            tax_rate=tax, stock=stock, reorder=reorder,
            weighted=weighted, unit=unit, color=color, active=True,
        ),
    )
    if not created:
        p.stock  = stock
        p.tenant = tenant
        p.save(update_fields=["stock", "tenant"])
    return p


# Fix existing Burger
Product.objects.filter(pk=1).update(tenant=tenant)
burger = Product.objects.get(pk=1)

pepsi    = make_product("6001069030001", "DRK-001", "Pepsi 330ml",         cat_drinks,  7.00,  4.50,  80, 20, color="#dc2626")
sprite   = make_product("6001069030002", "DRK-002", "Sprite 330ml",        cat_drinks,  7.00,  4.50,  60, 20, color="#16a34a")
water    = make_product("6111042100399", "DRK-003", "Water 500ml",         cat_drinks,  3.00,  1.50, 200, 50, color="#0ea5e9")
juice    = make_product("5449000133328", "DRK-004", "Orange Juice 250ml",  cat_drinks,  9.00,  6.00,  40, 10, color="#ea580c")

milk     = make_product("6224001052020", "DRY-001", "Fresh Milk 1L",       cat_dairy,   8.50,  6.00,  50, 15, color="#f8fafc")
yogurt   = make_product("6224002050019", "DRY-002", "Yogurt 200g",         cat_dairy,   5.00,  3.20,  60, 20, color="#fef9c3")
cheese   = make_product("6224009001028", "DRY-003", "White Cheese 200g",   cat_dairy,  14.00,  9.50,  30, 10, color="#fef3c7")
butter   = make_product("6224003060017", "DRY-004", "Butter 200g",         cat_dairy,  18.00, 13.00,  25,  8, color="#fde68a")

chips    = make_product("6291003512014", "SNK-001", "Chips",               cat_snacks,  7.50,  5.00,  70, 20, color="#f59e0b")
kitkat   = make_product("6294003612016", "SNK-002", "KitKat",              cat_snacks,  8.00,  5.50,  50, 15, color="#92400e")
biscuits = make_product("6294006512010", "SNK-003", "Biscuits",            cat_snacks,  6.00,  4.00,  80, 25, color="#d97706")
sandwich = make_product("6001234567890", "BGR-002", "Chicken Sandwich",    cat_burgers,10.00,  7.00,  30, 10, color="#b45309")

banana   = make_product("4011000000001", "FRT-001", "Banana 1kg",          cat_fruits,  9.00,  6.00,  40, 10,
                         weighted=True, unit=Product.Unit.KG, color="#eab308")
apple    = make_product("4131000000001", "FRT-002", "Apple 1kg",           cat_fruits, 14.00,  9.00,  30, 10,
                         weighted=True, unit=Product.Unit.KG, color="#ef4444")
tomato   = make_product("4087000000001", "VEG-001", "Tomato 1kg",          cat_fruits,  7.00,  4.50,  50, 15,
                         weighted=True, unit=Product.Unit.KG, color="#dc2626")

all_products = [burger, pepsi, sprite, water, juice,
                milk, yogurt, cheese, butter,
                chips, kitkat, biscuits, sandwich,
                banana, apple, tomato]

print(f"[3] {len(all_products)} products ready")

# ── Inventory batches ──────────────────────────────────────────────────────────

for p in all_products:
    batch_no = f"BATCH-{p.sku}-001"
    if not InventoryBatch.objects.filter(batch_number=batch_no).exists():
        InventoryBatch.objects.create(
            tenant=tenant,
            product=p,
            batch_number=batch_no,
            remaining_quantity=Decimal(str(p.stock)),
            cost_price=p.cost,
            expiry_date=None,
        )
        StockMovement.objects.create(
            tenant=tenant,
            product=p,
            qty=p.stock,
            movement_type=StockMovement.MovementType.PURCHASE_IN,
            note=f"Seed purchase — {batch_no}",
        )

print("[4] Inventory batches created")

# ── Sales helper ───────────────────────────────────────────────────────────────

def make_sale(items_spec, method, cashier,
              paid_extra=0, discount_type=None,
              discount_value=Decimal("0"), offset_hours=0):
    """
    items_spec: list of (product, qty, price_each)
    offset_hours: hours in the past (positive = older)
    """
    subtotal   = sum(Decimal(str(qty)) * Decimal(str(price)) for _, qty, price in items_spec)
    tax_amount = sum(
        Decimal(str(qty)) * Decimal(str(price)) * p.tax_rate
        for p, qty, price in items_spec
    )

    if discount_type == "percent":
        discount_amount = subtotal * discount_value / Decimal("100")
    elif discount_type == "fixed":
        discount_amount = discount_value
    else:
        discount_amount = Decimal("0")

    total  = round(subtotal + tax_amount - discount_amount, 2)
    paid   = total + Decimal(str(paid_extra))
    change = paid - total

    sale = Sale(
        tenant=tenant, cashier=cashier, branch=branch, terminal=terminal,
        subtotal=round(subtotal, 2), tax_amount=round(tax_amount, 2),
        total=total, method=method, paid=paid, change=change,
        status=Sale.Status.COMPLETED,
        discount_type=discount_type, discount_value=discount_value,
        receipt_printed=True,
    )
    sale.save()

    for product, qty, price_each in items_spec:
        SaleItem.objects.create(
            sale=sale, product=product,
            product_name=product.name,
            barcode=product.barcode or "",
            qty=Decimal(str(qty)),
            price_each=Decimal(str(price_each)),
            line_total=Decimal(str(qty)) * Decimal(str(price_each)),
        )
        Product.objects.filter(pk=product.pk).update(
            stock=Product.objects.filter(pk=product.pk).values_list("stock", flat=True)[0] - int(qty)
        )
        StockMovement.objects.create(
            tenant=tenant, product=product,
            qty=-int(qty),
            movement_type=StockMovement.MovementType.SALE_OUT,
            sale=sale, note=f"Sale #{sale.pk}",
        )

    target_dt = now - timedelta(hours=offset_hours)
    Sale.objects.filter(pk=sale.pk).update(created_at=target_dt)
    print(f"    Sale #{sale.pk:03d} | {method:6s} | {cashier.username:8s} | total={float(total):7.2f} | {target_dt.strftime('%Y-%m-%d %H:%M')}")
    return sale


# ── TODAY ──────────────────────────────────────────────────────────────────────
print("[5] Creating today's sales...")

make_sale([(pepsi, 2, 7.00), (chips, 1, 7.50), (sandwich, 1, 10.00)],
          "cash", ziad, paid_extra=2, offset_hours=1)

make_sale([(burger, 2, 4.32), (sprite, 2, 7.00)],
          "card", ziad, offset_hours=2)

make_sale([(milk, 2, 8.50), (yogurt, 3, 5.00), (cheese, 1, 14.00), (butter, 1, 18.00)],
          "cash", karim, paid_extra=5, offset_hours=3)

make_sale([(banana, 2, 9.00), (apple, 1, 14.00), (tomato, 3, 7.00)],
          "wallet", ziad,
          discount_type="percent", discount_value=Decimal("10"), offset_hours=4)

make_sale([(kitkat, 3, 8.00), (biscuits, 2, 6.00), (juice, 2, 9.00), (water, 4, 3.00)],
          "cash", mohamed, paid_extra=10, offset_hours=5)

# ── YESTERDAY ─────────────────────────────────────────────────────────────────
print("[6] Creating yesterday's sales...")

make_sale([(burger, 3, 4.32), (pepsi, 3, 7.00)],
          "cash", ziad, paid_extra=3, offset_hours=28)

make_sale([(milk, 1, 8.50), (cheese, 2, 14.00), (yogurt, 2, 5.00)],
          "card", ziad, offset_hours=30)

make_sale([(sandwich, 2, 10.00), (sprite, 2, 7.00), (chips, 3, 7.50)],
          "cash", karim, offset_hours=31)

make_sale([(banana, 3, 9.00), (tomato, 2, 7.00), (apple, 2, 14.00)],
          "wallet", mohamed,
          discount_type="fixed", discount_value=Decimal("5"), offset_hours=33)

make_sale([(water, 6, 3.00), (juice, 3, 9.00), (biscuits, 4, 6.00), (kitkat, 2, 8.00)],
          "cash", ziad, paid_extra=20, offset_hours=35)

# ── LAST WEEK ─────────────────────────────────────────────────────────────────
print("[7] Creating last week's sales...")

make_sale([(burger, 4, 4.32), (pepsi, 4, 7.00), (chips, 2, 7.50)],
          "cash", ziad, paid_extra=5, offset_hours=7*24+2)

make_sale([(milk, 3, 8.50), (butter, 2, 18.00), (cheese, 1, 14.00)],
          "card", karim, offset_hours=7*24+4)

make_sale([(sandwich, 3, 10.00), (sprite, 3, 7.00), (juice, 2, 9.00)],
          "cash", ziad, paid_extra=8, offset_hours=7*24+6)

make_sale([(apple, 4, 14.00), (banana, 2, 9.00), (tomato, 5, 7.00)],
          "wallet", mohamed,
          discount_type="percent", discount_value=Decimal("15"), offset_hours=7*24+8)

make_sale([(kitkat, 5, 8.00), (biscuits, 3, 6.00), (water, 8, 3.00), (burger, 2, 4.32)],
          "card", ziad, offset_hours=7*24+10)

# ── Summary ───────────────────────────────────────────────────────────────────
total_sales    = Sale.objects.filter(tenant=tenant).count()
total_products = Product.objects.filter(tenant=tenant).count()
total_cats     = Category.objects.filter(tenant=tenant).count()

print("\n" + "="*50)
print(f"  Categories : {total_cats}")
print(f"  Products   : {total_products}  (3 weighted/scale products)")
print(f"  Total Sales: {total_sales}")
print(f"  Methods    : cash / card / wallet")
print(f"  Spread     : today(5) / yesterday(5) / last-week(5)")
print("="*50)
print("Seed complete!")
