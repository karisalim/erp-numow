# 💻 Code Examples - Implementation Guide

## 1. Adding Missing Indexes (Django Migration)

### File: `pos/migrations/0010_add_missing_indexes.py`

```python
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0009_delete_pluitem'),
    ]

    operations = [
        # Foreign Key Indexes
        migrations.AddIndex(
            model_name='saleitem',
            index=models.Index(
                fields=['product_id'],
                name='idx_saleitem_product'
            ),
        ),
        migrations.AddIndex(
            model_name='saleitem',
            index=models.Index(
                fields=['sale_id'],
                name='idx_saleitem_sale'
            ),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['category_id'],
                name='idx_product_category'
            ),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(
                fields=['cashier_id'],
                name='idx_sale_cashier'
            ),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(
                fields=['branch_id'],
                name='idx_sale_branch'
            ),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(
                fields=['terminal_id'],
                name='idx_sale_terminal'
            ),
        ),
        
        # Composite Indexes
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(
                fields=['tenant_id', '-created_at'],
                name='idx_sales_tenant_created'
            ),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(
                fields=['cashier_id', '-created_at'],
                name='idx_sales_cashier_created'
            ),
        ),
        
        # Partial Index (Low Stock)
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['stock'],
                condition=models.Q(stock__lte=models.F('reorder')) & models.Q(active=True),
                name='idx_products_low_stock'
            ),
        ),
        
        # Batch Expiry Index
        migrations.AddIndex(
            model_name='inventorybatch',
            index=models.Index(
                fields=['expiry_date'],
                condition=models.Q(expiry_date__isnull=False),
                name='idx_batch_expiry'
            ),
        ),
    ]
```

---

## 2. Fix Race Condition - Product Model

### File: `pos/models.py` (Updated)

```python
from django.db import models, transaction
from django.db.models import F

class Product(models.Model):
    # ... existing fields ...
    
    def deduct_stock(self, qty, reason=""):
        """
        Atomically deduct stock from this product.
        
        Raises:
            InsufficientStockError: If not enough stock
            
        Returns:
            Updated quantity
        """
        from django.core.exceptions import ValidationError
        
        # Validate input
        if qty <= 0:
            raise ValidationError("Quantity must be positive")
        
        with transaction.atomic():
            # Lock this row until transaction ends
            product = Product.objects.select_for_update().get(pk=self.pk)
            
            if product.stock < qty:
                raise InsufficientStockError(
                    f"Only {product.stock} {product.unit} available, "
                    f"trying to sell {qty}"
                )
            
            # Atomic update
            product.stock = F('stock') - qty
            product.save(update_fields=['stock'])
            
            # Refresh to get the actual value
            product.refresh_from_db()
            
            return product.stock
    
    def add_stock(self, qty, reason=""):
        """Atomically add stock (receiving, returns)"""
        if qty <= 0:
            raise ValidationError("Quantity must be positive")
        
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.pk)
            product.stock = F('stock') + qty
            product.save(update_fields=['stock'])
            product.refresh_from_db()
            
            return product.stock


class InsufficientStockError(Exception):
    """Raised when trying to sell more than available stock"""
    pass
```

### Usage in Views

```python
# pos/views.py

from rest_framework.response import Response
from rest_framework.decorators import api_view
from pos.models import Product, InsufficientStockError

@api_view(['POST'])
def add_item_to_cart(request):
    """
    Add product to cart with atomic stock check
    """
    product_id = request.data.get('product_id')
    qty = request.data.get('qty', 1)
    
    try:
        product = Product.objects.get(id=product_id, tenant=request.user.tenant)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found'}, status=404)
    
    try:
        remaining_stock = product.deduct_stock(qty)
        
        return Response({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'qty': qty,
                'price': str(product.price),
            },
            'remaining_stock': str(remaining_stock)
        })
        
    except InsufficientStockError as e:
        return Response({
            'error': str(e),
            'available': str(product.stock)
        }, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
```

---

## 3. Add DiscountCode Model

### File: `pos/models.py` (Add)

```python
from django.utils import timezone

class DiscountCode(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'
    
    tenant = models.ForeignKey(
        'accounts.Tenant',
        on_delete=models.CASCADE,
        related_name='discount_codes'
    )
    code = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Promo code e.g., PROMO2026"
    )
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    
    # Validity
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    
    # Usage limits
    max_uses = models.IntegerField(
        null=True,
        blank=True,
        help_text="NULL = unlimited"
    )
    uses_count = models.IntegerField(default=0)
    
    # Minimum purchase requirement
    min_purchase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    # Product restrictions
    applicable_products = models.ManyToManyField(
        'Product',
        blank=True,
        help_text="Leave empty for all products"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-valid_until']
        indexes = [
            models.Index(fields=['tenant', 'code']),
            models.Index(fields=['valid_until', 'is_active']),
        ]
        unique_together = [('tenant', 'code')]
    
    def __str__(self):
        return f"{self.code} ({self.discount_value}{self.get_discount_type_display()})"
    
    def is_valid(self):
        """Check if code is currently valid"""
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_until and
            (self.max_uses is None or self.uses_count < self.max_uses)
        )
    
    def can_apply_to_product(self, product):
        """Check if code applies to this product"""
        if not self.applicable_products.exists():
            return True  # Applies to all
        return self.applicable_products.filter(id=product.id).exists()
    
    def calculate_discount(self, cart_total, cart_items=None):
        """
        Calculate discount amount
        
        Args:
            cart_total: Total before discount
            cart_items: List of product objects (for product restrictions)
            
        Returns:
            Discount amount
            
        Raises:
            ValidationError: If code is invalid or restrictions not met
        """
        from django.core.exceptions import ValidationError
        
        if not self.is_valid():
            raise ValidationError("This code is not valid")
        
        if cart_total < self.min_purchase_amount:
            raise ValidationError(
                f"Minimum purchase of {self.min_purchase_amount} required"
            )
        
        # Check product restrictions
        if self.applicable_products.exists() and cart_items:
            applicable_count = sum(
                1 for item in cart_items
                if self.can_apply_to_product(item)
            )
            if applicable_count == 0:
                raise ValidationError(
                    "This code doesn't apply to items in your cart"
                )
        
        # Calculate discount
        if self.discount_type == self.DiscountType.PERCENT:
            discount = (cart_total * self.discount_value) / 100
        else:  # FIXED
            discount = min(self.discount_value, cart_total)
        
        return discount
    
    def apply(self):
        """Record this code as used"""
        self.uses_count += 1
        self.save(update_fields=['uses_count'])
```

### Migration

```python
# pos/migrations/0011_add_discount_code.py

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_tenant_show_tax_on_receipt'),
        ('pos', '0010_add_missing_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiscountCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, 
                                          serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=20)),
                ('discount_type', models.CharField(
                    choices=[('percent', 'Percentage'), ('fixed', 'Fixed Amount')],
                    default='percent', max_length=10)),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('valid_from', models.DateTimeField()),
                ('valid_until', models.DateTimeField()),
                ('max_uses', models.IntegerField(blank=True, null=True)),
                ('uses_count', models.IntegerField(default=0)),
                ('min_purchase_amount', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('applicable_products', models.ManyToManyField(
                    blank=True, to='pos.product')),
                ('created_by', models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to='accounts.user')),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='discount_codes', to='accounts.tenant')),
            ],
            options={
                'ordering': ['-valid_until'],
            },
        ),
        migrations.AddIndex(
            model_name='discountcode',
            index=models.Index(fields=['tenant', 'code'], name='idx_discount_tenant_code'),
        ),
    ]
```

---

## 4. Payment Model

### File: `pos/models.py` (Add)

```python
class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Credit/Debit Card'
        WALLET = 'wallet', 'Digital Wallet'
        MIXED = 'mixed', 'Mixed Payment'
    
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
    
    sale = models.OneToOneField(
        'Sale',
        on_delete=models.CASCADE,
        related_name='payment'
    )
    
    method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices
    )
    status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment gateway
    gateway = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="stripe, paypal, vodafone_cash, etc"
    )
    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )
    reference_number = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )
    
    # Cash specific
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    change = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Error handling
    error_code = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )
    error_message = models.TextField(null=True, blank=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status', 'processed_at']),
            models.Index(fields=['gateway', 'transaction_id']),
        ]
    
    def __str__(self):
        return f"Payment {self.id} ({self.status})"
    
    @classmethod
    def process_cash_payment(cls, sale, amount_paid):
        """Process cash payment"""
        payment = cls.objects.create(
            sale=sale,
            method=cls.PaymentMethod.CASH,
            status=cls.PaymentStatus.SUCCESS,
            amount=sale.total,
            amount_paid=amount_paid,
            change=amount_paid - sale.total,
            processed_at=timezone.now()
        )
        return payment
```

---

## 5. AuditLog Model

### File: `pos/models.py` (Add)

```python
import json
from django.contrib.postgres.fields import JSONField

class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'create', 'Created'
        UPDATE = 'update', 'Updated'
        DELETE = 'delete', 'Deleted'
        VOID = 'void', 'Voided'
        PRINT = 'print', 'Printed'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
    
    tenant = models.ForeignKey(
        'accounts.Tenant',
        on_delete=models.CASCADE,
        db_index=True
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        db_index=True
    )
    
    # What was changed
    model_name = models.CharField(
        max_length=50,
        db_index=True
    )
    object_id = models.BigIntegerField()
    
    # The changes
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField()
    
    # Context
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant', 'timestamp']),
            models.Index(fields=['tenant', 'model_name', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.model_name} {self.object_id} - {self.action}"
    
    @classmethod
    def log_change(cls, tenant, user, action, model_name, object_id,
                   old_values=None, new_values=None, request=None, reason=''):
        """Create audit log entry"""
        from django.http import HttpRequest
        
        ip_address = ''
        user_agent = ''
        
        if request and isinstance(request, HttpRequest):
            ip_address = get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        return cls.objects.create(
            tenant=tenant,
            user=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason
        )


def get_client_ip(request):
    """Get client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
```

### Usage Example

```python
# In a view when updating product price

from pos.models import AuditLog

old_product = Product.objects.get(id=123)
old_data = {'price': str(old_product.price)}

product.price = new_price
product.save()

AuditLog.log_change(
    tenant=request.user.tenant,
    user=request.user,
    action=AuditLog.Action.UPDATE,
    model_name='Product',
    object_id=123,
    old_values=old_data,
    new_values={'price': str(new_price)},
    request=request,
    reason='Manager: Price adjustment for promotion'
)
```

---

## 6. Query Optimization Examples

### Before (SLOW):
```python
# views.py - Bad query
sales = Sale.objects.filter(cashier=cashier).all()
# Then iterating:
for sale in sales:
    items = sale.items.all()  # N+1 query!
    for item in items:
        product = item.product  # Another N+1!
```

### After (FAST):
```python
# views.py - Good query
from django.db.models import Prefetch

sales = Sale.objects.filter(
    cashier=cashier,
    tenant=request.user.tenant
).select_related(
    'cashier',
    'branch',
    'terminal'
).prefetch_related(
    'items',
    'items__product'
)

# Only 2 queries total instead of 1 + N + N*M!
```

---

## 7. Testing Race Condition Fix

### File: `pos/tests.py`

```python
import threading
from django.test import TestCase
from django.db import transaction
from pos.models import Product, InsufficientStockError

class StockRaceConditionTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Test Product',
            barcode='123456',
            price=100,
            cost=50,
            stock=10
        )
    
    def test_concurrent_stock_updates(self):
        """Test that race condition doesn't occur"""
        results = []
        errors = []
        
        def buy_items():
            try:
                self.product.deduct_stock(3)
                results.append('success')
            except InsufficientStockError:
                errors.append('insufficient')
            except Exception as e:
                errors.append(str(e))
        
        # 5 threads trying to buy 3 items each (total 15, but only 10 in stock)
        threads = []
        for _ in range(5):
            t = threading.Thread(target=buy_items)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # 3 should succeed (9 items), 2 should fail
        self.assertEqual(len([r for r in results if r == 'success']), 3)
        self.assertEqual(len(errors), 2)
        
        # Stock should be exactly 1 (10 - 3*3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
```

---

## 8. Index Performance Test

### File: `pos/performance_test.py`

```python
import time
from django.test import TestCase
from pos.models import Sale, Product

class IndexPerformanceTest(TestCase):
    def test_index_performance(self):
        """Compare query performance with indexes"""
        
        # Generate test data (10K sales)
        sales = [
            Sale.objects.create(...) for _ in range(10000)
        ]
        
        # Test 1: Query without index (theoretical)
        # Test 2: Query with index (actual)
        
        # Measure: Get all sales for cashier ordered by date
        start = time.time()
        
        result = Sale.objects.filter(
            cashier_id=1
        ).order_by('-created_at')[0:100]
        
        list(result)  # Force evaluation
        
        end = time.time()
        
        print(f"Query time: {(end-start)*1000:.2f}ms")
        
        # Should be < 10ms with index
        self.assertLess(end - start, 0.01)
```

---

هذه الأمثلة جاهزة للاستخدام المباشر في المشروع!

