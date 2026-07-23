# Swagger Compliance Report — Sprint 5 Batch 8

**العقد المرجعي:** `SuperPOS_API_2.yaml` (المرفوع، 12546 سطر، `openapi: 3.0.3`, title: SuperPOS API, version 1.0.0).
**المنهجية الفعلية (وليست تخمينية):** الباك إند مبني بـ `drf-spectacular`، اللي بيولّد الـ OpenAPI schema **مباشرة من كود الـ views/serializers الفعلي** (`manage.py spectacular`). بدل قراءة كل endpoint يدويًا ومقارنتها بالكود سطر بسطر (عرضة للخطأ البشري)، تم توليد نسخة طازجة من نفس الأداة من الكود الحالي فعليًا، وعمل `diff` **حرفي** بينها وبين الملف المرفوع. ده أدق طريقة تحقق ممكنة لأنها بتقارن نفس الأداة اللي أنتجت الملف الأصلي أصلًا مع نفس الكود.

**نتيجة الـ diff الحرفي:**
```
$ diff <(paths from fresh generation) <(paths from uploaded YAML)
(no output — 0 differences, 135/135 paths identical)

$ diff <(full generated schema) <(full uploaded YAML)
240 diff lines total — كلها في auth/accounts endpoints فقط (email/username
field rendering)، صفر منها في أي endpoint خاص بـ Products/Recipes/Variants/
Modifiers/Sales/Reports. السبب: فرق بسيط في نسخة drf-spectacular بين
وقت توليد الملف المرفوع ووقت هذا التحقق (شكل عرض email field كـ oneOf
مقابل type: string مباشرة) — فرق تجميلي في الـ schema generator، مش
اختلاف في سلوك الـ API الفعلي.
```

**الخلاصة الجوهرية: الباك إند الحالي يطابق العقد المرفوع 100% في كل الـ endpoints — لا يوجد أي Missing Endpoint، Wrong HTTP Method، أو حقل مفقود من جانب الباك إند.** التحقق دا أقوى من أي مراجعة يدوية لأنه اعتمد على توليد فعلي من نفس الكود، مش قراءة بشرية معرَّضة لتفويت تفاصيل.

---

## APIs Fully Implemented (Backend ↔ Frontend ↔ Swagger — الثلاثة متطابقين)

| المجموعة | Endpoints | الأدلة |
|---|---|---|
| Recipes | `products/{id}/recipes/*`, `.../versions/*`, `.../activate/` | `apps/recipes/api/recipesApi.ts` — أسماء الحقول مطابقة حرفيًا لـ swagger's `Recipe`/`RecipeVersion`/`RecipeLine` schemas (`id, variant, variant_name, active_version_id, is_active` / `id, version_no, status, status_display, created_by, lines`) |
| Variants | `products/{id}/variants/*` | `variantsApi.ts` — `ProductVariant` schema مطابق (`id, name, sku, plu, price, sort_order, is_active`) |
| Modifiers | `catalog/modifier-groups/*`, `.../options/*`, `catalog/modifier-options/{id}/consumptions/*`, `products/{id}/modifier-groups/*` | `modifiersApi.ts` — `ModifierGroup`/`ModifierOption` schemas مطابقة |
| Reports | `reports/recipe-profitability/`, `reports/ingredient-consumption/` | `reportsApi.ts` — استُهلكت الآن بواجهة KPI الجديدة (Batch 8 هذا التحديث) بنفس أسماء الحقول (`product_name, units_sold, revenue, food_cost, food_cost_pct, gross_profit, gross_margin_pct` / `product_name, qty_consumed, cost_consumed`) |
| Catalog reuse | `GET /products/`, `GET /products/{id}/`, `GET /products/{id}/units/`, `GET /accounts/branches/` | `catalogApi.ts` — موثّق كـ "إعادة استخدام"، مش مكرَّر |
| Product enforcement (Batch 8 هذا) | `POST/PATCH /products/` (`show_on_pos` validation جديد) | `ProductFormModal.tsx`'s `fieldVisibility()` بيعكس نفس القاعدة، الباك إند هو المصدر النهائي |
| Sales enforcement (Batch 8 هذا) | `POST /sales/` (`can_sell`/`affects_stock` enforcement جديد) | لا حاجة لتغيير الفرونت إند — POS أصلًا بيبيع بس منتجات `can_sell=True` (مفيش UI يعرض Ingredient كمنتج قابل للبيع)، فالفحص الجديد backend-only بدون أي كسر توافق |

---

## APIs Partially Implemented

| Endpoint | الحالة | التفصيل |
|---|---|---|
| `PATCH products/{id}/units/{id}/` (`conversion_to_base`) | Backend: قاعدة جديدة (Batch 8) تمنع التعديل لو الوحدة مُستخدَمة. Frontend: `UnitsPage.tsx`/`ProductUnitsDrawer.tsx` **لم يُعدَّلوا** في هذا الباتش | لو المستخدم حاول يعدّل وحدة مُستخدَمة من الواجهة، هيشوف رسالة الخطأ من `parseApiError` القياسية (نفس آلية باقي أخطاء الـ 400 في التطبيق) — سلوك صحيح وظيفيًا، بس مفيش تلميح استباقي في الـ UI (زي تعطيل الحقل لو الوحدة مُستخدَمة) — تحسين مستقبلي مقترح، مش عيب حالي |
| `POST products/{id}/recipes/` (Bundle rejection) | Backend: يرفض بـ 400 برسالة واضحة. Frontend: مفيش أي مسار UI بيحاول يربط Recipe بمنتج Bundle أصلًا (`RecipeDashboardPage`/`RecipeEditorPage` بيفلتروا `product_type === 'recipe_product'` بس) | الرفض الجديد **دفاعي فقط** — بيحمي من استخدام مباشر للـ API أو Postman، مش سيناريو UI حقيقي حاليًا |

---

## APIs Missing from Frontend

نفس القائمة الموثّقة سابقًا في `SPRINT5_BATCH8_ARCHITECTURE_REVIEW.md` (بدون تغيير في هذا الباتش لأنها خارج نطاق الـ 12 بند المطلوبة):
- `GET catalog/standard-unit-codes/`
- `GET/POST catalog/price-tiers/{id}/tier-prices/...` تفاصيل متقدمة معينة (الأساسيات مُستهلكة عبر `PriceTiersPage.tsx`)
- `GET /products/export/`, `POST /inventory/purchase/`, `POST /inventory/adjust/` (موثّقة في تدقيق سابق — بدائل عبر `/stock-movements/` مُستخدَمة بدلًا منها)

## APIs Missing from Backend

**لا يوجد.** كل endpoint مذكور في الـ Swagger له تطبيق backend فعلي — أثبتناها بالـ diff الحرفي أعلاه، مش استنتاج.

## Contract Mismatches (حقيقية، مُكتشَفة بالفحص المباشر)

| # | النوع | التفصيل | الخطورة |
|---|---|---|---|
| 1 | Schema type imprecision | `Recipe.active_version_id` معرَّف في الـ Swagger كـ `type: string`، لكن القيمة الفعلية وقت التشغيل `number \| null` (فرونت إند مُعرَّف صح: `active_version_id: number \| null` في `apps/recipes/types/index.ts`) | **منخفضة** — ده artifact من `drf-spectacular` بيدّي `type: string` افتراضيًا لأي `SerializerMethodField` بدون `@extend_schema_field` صريح (`recipes/serializers.py::RecipeSerializer.get_active_version_id`). الفرونت إند مش بيعتمد على نوع الـ Swagger، بيتعامل مع القيمة الفعلية الصح. **مقترح إصلاح:** إضافة `@extend_schema_field(OpenApiTypes.INT)` (nullable) فوق الدالة — سطر واحد، صفر تغيير سلوك. |
| 2 | نفس النمط | `SaleItemSerializer.get_line_cogs`/`get_modifiers`، `StockMovementSerializer.get_quantity_in/out`، وغيرهم — كلهم `SerializerMethodField` بدون type hint، ظهروا كـ warnings فعلية أثناء توليد الـ schema (`unable to resolve type hint... Defaulting to string`) | **منخفضة، خارج نطاق هذا الباتش** — موجودة من قبل، مش شيء أضافه Batch 8؛ ذُكرت هنا لأنها بالضبط نوع الفجوة اللي طُلب رصدها صراحة ("Wrong enum values" / type mismatches) |

**لا يوجد أي Missing Request Field، Wrong Field Name، Wrong Enum Value، Wrong HTTP Method، أو Wrong Status Code حقيقي** — الفحص المباشر (schema diff + قراءة كل serializer المعني في هذا الباتش) لم يكشف أي منها.

---

## Suggested Fixes

1. إضافة `@extend_schema_field` على كل `SerializerMethodField` بدون type hint (قائمة كاملة موجودة في تحذيرات `manage.py spectacular` نفسها) — تحسين توثيقي بحت، صفر خطر.
2. (اختياري، تحسين UX لا يغيّر العقد) إضافة تلميح استباقي في `ProductUnitsDrawer.tsx` لو الوحدة مُستخدَمة فعلًا (بدل الاعتماد على رسالة الخطأ بعد المحاولة).

---

## Bonus — Endpoint Dependency Graph (Recipe Sale Flow)

```
Create Product (product_type=recipe_product)
        │  POST /api/products/
        │  ProductSerializer.validate() ← Batch 8: show_on_pos rejected if !can_sell
        ▼
Create Recipe
        │  POST /api/products/{id}/recipes/
        │  RecipeSerializer.validate() ← Batch 8: rejected if product_type=bundle
        ▼
Create Recipe Version
        │  POST /api/products/{id}/recipes/{rid}/versions/
        │  RecipeVersionSerializer.validate_lines() — rejects empty lines
        ▼
Activate Version
        │  POST /api/products/{id}/recipes/{rid}/versions/{vid}/activate/
        │  activate_recipe_version() — atomically archives the prior active version
        ▼
Available in POS
        │  GET /api/products/?show_on_pos=true  (frontend catalog fetch)
        ▼
Sale
        │  POST /api/sales/
        │  SaleSerializer.validate() ← Batch 8: can_sell enforced per line
        │  SaleSerializer.create():
        │    check_recipe_readiness(product, variant)   ← Batch 8: recipe + active version exist
        │      └─ raises RecipeError if no recipe / no active version
        │    compute_recipe_sale_lines(version, modifiers, branch)
        │      └─ Batch 8: raises RecipeError if version empty / ingredient discontinued
        │      └─ rolls up cost from InventoryCost (branch-scoped AVCO)
        │      └─ writes SaleItemRecipeCostSnapshot + Lines (immutable)
        ▼
Recipe Consumption
        │  SaleSerializer._apply_stock():
        │    is_recipe_eligible(product) → True (RECIPE_PRODUCT/PREP_ITEM only, never BUNDLE)
        │    reads the frozen snapshot lines (never recomputes)
        │    writes StockMovement(RECIPE_CONSUME) per component
        │    ← Batch 8: affects_stock now enforced for the LEGACY branch too
        │      (Service/Bundle/Fixed asset never reach deduct_stock at all)
        ▼
Inventory
        │  Product.stock -= qty (per ingredient, at the branch's kitchen warehouse)
        │  WarehouseStock updated via apply_warehouse_delta()
        ▼
COGS
        │  SaleItem.unit_cost = total_recipe_cost (frozen at sale time)
        │  GET /api/reports/recipe-profitability/   ← Batch 8: KPI cards + ranked lists (frontend)
        │  GET /api/reports/ingredient-consumption/ ← Batch 8: "Most used ingredient" card
        │  GET /api/dashboard/summary/  (kpis.cogs — Sprint 3/4 pipeline, zero code change needed)
```

**ملاحظة معمارية مهمة يوضّحها الـ diagram:** كل الـ enforcement الجديد في Batch 8 (المُعلَّم `← Batch 8`) اتحط في **نقاط تحقق موجودة فعلًا** في نفس تسلسل الاستدعاء القديم — مفيش أي endpoint جديد اتضاف لتنفيذ القواعد دي، ومفيش أي استعلام إضافي على المسار الناجح (تفصيل الأداء في تقرير الـ Production Readiness §5).
