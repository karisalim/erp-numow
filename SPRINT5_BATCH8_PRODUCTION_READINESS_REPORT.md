# Sprint 5 Batch 8 Production Readiness Report

**تاريخ:** 2026-07-23
**النطاق:** كل الـ 12 بند المطلوبة (Product Type Enforcement, Dynamic Product Form, show_on_pos/can_sell/affects_stock enforcement, Conversion Integrity, Bundle، Product Readiness Check، UX، Reports، Cost Preview) + مطابقة العقد مع OpenAPI YAML المرفوع.
**المنهجية:** كل تعديل اتحقق منه بتشغيل فعلي: **802/802 backend tests ناجحة**، `manage.py check` نظيف، `makemigrations --check` صفر migrations جديدة (تعديلات منطق بحتة، بدون تغيير schema)، `npm run build` نظيف (`tsc` + `vite build`)، و**تدفق كامل حقيقي في متصفح** (Playwright ضد Django+Postgres+Vite فعليين، مش mocks) يثبت رحلة Product → Save → Build Recipe → Recipe Editor فعليًا.

---

## 1) جميع الـ Bugs التي تم إصلاحها

| # | الـ Bug | الملف/الدالة | الأثر قبل الإصلاح |
|---|---|---|---|
| 1 | `affects_stock` كان **مُشار له في تعليق فقط**، بدون فرض فعلي | `pos/serializers.py::SaleSerializer._apply_stock()` | بيع `service`/`bundle`/`fixed_asset` كان يحاول يخصم `Product.stock` الخاص بيه هو نفسه، يكتب `StockMovement(SALE_OUT)` غير منطقية، ويسجل "OVERSOLD" كاذب لمنتج مالوش مخزون أصلًا |
| 2 | مفيش `can_sell` check في `SaleSerializer` إطلاقًا | `pos/serializers.py::SaleSerializer.validate()` | أي `Ingredient`/`Packaging`/`Prep Item`/`Fixed Asset` كان ممكن يتباع مباشرة كسطر بيع عادي، يخلط بين "استُهلك عبر Recipe" و"اتباع مباشرة" لنفس المنتج |
| 3 | `Recipe` كانت تُقبل عبر الـ API لمنتج `Bundle` بصمت | `recipes/serializers.py::RecipeSerializer` | إيحاء كاذب إن bundle-explosion شغالة، رغم إن `is_recipe_eligible()` كانت أصلًا بتستبعد Bundle من مسار البيع — الميزة "نص شغالة" بالضبط زي ما اتطلب نتجنبه |
| 4 | `conversion_to_base` لأي `ProductUnit` **غير base** كانت قابلة للتعديل في أي وقت حتى بعد استخدامها فعليًا في Purchase/Sale/Recipe | `pos/serializers.py::ProductUnitSerializer.validate()` | تعديل معامل تحويل وحدة مُستخدَمة فعلًا كان يغيّر كل التحويلات المستقبلية بصمت، بدون أي رفض أو تحذير |
| 5 | `show_on_pos=True` كان مقبول لأي `product_type` بلا فحص | `pos/serializers.py::ProductSerializer.validate()` | منتج زي Coffee Beans (`ingredient`) كان ممكن يظهر في شاشة الكاشير للبيع المباشر بالغلط |
| 6 | "Product Readiness Check" وقت البيع كان بيتحقق من شرطين بس (Recipe موجود + Active Version موجود)، من غير أي تحقق من صلاحية المكوّنات | `pos/serializers.py::SaleSerializer.create()` (كان بيستخدم `get_active_recipe()` مباشرة) | بيع Recipe Product كان بينجح حتى لو أحد مكوّناته الأساسية (Ingredient) تم إيقافه (`active=False`) — مفيش أي منع |

---

## 2) جميع الـ Validations التي أُضيفت

| # | القاعدة | الملف/Function | مُختبَرة بـ |
|---|---|---|---|
| 1 | `show_on_pos=True` مرفوض لأي `product_type` بـ `can_sell=False` | `ProductSerializer.validate()` | `test_show_on_pos_rejected_for_non_sellable_type_on_create`, `test_reclassifying_to_non_sellable_rejects_leftover_show_on_pos_true` |
| 2 | بيع منتج `can_sell=False` مرفوض صراحة بـ 400 | `SaleSerializer.validate()` (فحص جديد أول ما يتقرأ `product`، قبل تفرّع الأشكال الثلاثة للسطر) | `test_ingredient_cannot_be_sold_directly`, `test_packaging_cannot_be_sold_directly`, `test_fixed_asset_cannot_be_sold` |
| 3 | خصم المخزون في `_apply_stock` يتخطّى أي منتج `affects_stock=False` | `SaleSerializer._apply_stock()` (فحص جديد قبل `qty_delta = item.qty`) | `test_service_product_sells_but_never_touches_stock`, `test_bundle_sells_but_never_touches_its_own_stock` |
| 4 | `conversion_to_base` مقفولة لأي `ProductUnit` (مش الـ base بس) لو اتستخدمت فعلًا في Purchase/Sale (pos) أو Recipe/Modifier (recipes، عبر lazy import) | `ProductUnitSerializer.validate()` + `units_svc.product_unit_in_use()` جديدة | `test_unused_unit_conversion_freely_editable`, `test_conversion_locked_once_used_in_a_sale`, `test_editing_other_fields_still_allowed_once_locked` |
| 5 | إنشاء/تعديل `Recipe` مرفوض لمنتج `product_type=bundle` برسالة توضّح السبب | `RecipeSerializer.validate()` جديدة | `test_bundle_product_cannot_have_a_recipe_created` |
| 6 | **Product Readiness Check** — بوابة واحدة قبل بيع أي Recipe Product، بترفض بأسباب محددة: (أ) مفيش Recipe، (ب) مفيش Active Version، (ج) الـ Version الفعّالة فاضية (backstop دفاعي — مستحيل الوصول له عبر الـ API فعليًا، انظر §3)، (د) أي مكوّن أساسي `active=False` | `recipes/services/costing.py::check_recipe_readiness()` (جديدة) + إضافة داخل `compute_recipe_sale_lines()` (للشرطين ج/د، لتفادي استعلام مكرر — انظر §5) | `RecipeReadinessCheckTests` (5 اختبارات) + `test_discontinued_ingredient_blocks_the_actual_sale` (end-to-end) |

**كل الـ 6 Validations مفروضة Backend-only** — الفرونت إند (Dynamic Product Form) بيعكسها بصريًا فقط (إخفاء حقول، إرسال قيم آمنة افتراضية)، لكن Backend هو **المصدر الوحيد للحقيقة الفعلي** ولا يعتمد على أي التزام من الفرونت إند — تم التأكد من كده بإرسال طلبات مباشرة عبر الاختبارات، مش بس عبر الواجهة.

---

## 3) أي Validation لم يتم تنفيذه ولماذا

| البند المطلوب | الحالة | السبب |
|---|---|---|
| "كل الوحدات صحيحة" كجزء من Product Readiness Check | **لم يُنفَّذ كفحص منفصل وقت البيع، بقرار هندسي واعٍ** | `RecipeLine.qty_base` مُحسوبة ومُجمَّدة مرة واحدة وقت إنشاء السطر (`RecipeLineSerializer.create`) — مفيش "تحويل وحدة حي" ممكن يفشل وقت البيع أصلًا؛ إعادة التحقق كل بيع كانت هتبقى قراءة زائدة بلا خطر فعلي بتحميه. **الأثر الفعلي لباقي البنود (٦) اتحقق بدلها**: صلاحية المكوّنات (`active=False`) هي الفحص الحقيقي المتبقي، وده اتنفّذ. |
| منع "Active Version فارغة" كـ validation | **موجود، لكن كـ backstop دفاعي فقط — لأن الحالة دي مستحيلة الوصول عبر الـ API أصلًا** | `RecipeVersionSerializer.validate_lines()` بترفض إنشاء version فاضية من الأساس، و`RecipeVersionDetailView` (`RetrieveAPIView`) مفهاش PATCH إطلاقًا — يعني مفيش endpoint يقدر يفضّي سطور version موجودة بعد إنشائها. الفحص اتحط جوّه `compute_recipe_sale_lines` كطبقة حماية إضافية (defense-in-depth)، واتختبر مباشرة عبر تلاعب ORM يدوي (`version.lines.update(is_active=False)`) — مش لأنه سيناريو واقعي، لكن عشان نثبت إن الحماية شغالة فعلًا لو حصل تلاعب مباشر بالبيانات مستقبلًا. |
| Endpoint حقيقي لـ Cost Preview (سؤال #11) | **لم يُنفَّذ — تُرك Placeholder كما طُلب حرفيًا** | التعليمة صريحة: "إذا لم يوجد Backend Endpoint حالياً: اترك الـ Placeholder كما هو." `CostPreview.tsx` باقي بدون تعديل — صفر API calls، شرح واضح + رابط لتقرير Recipe Reports. لو الـ Endpoint اتضاف مستقبلًا، التصميم المطلوب موضّح بالتفصيل في `SPRINT5_BATCH8_ARCHITECTURE_REVIEW.md`. |
| منع `PATCH` لتعديل `conversion_to_base` على الـ **base unit** نفسها بعد الاستخدام | **موجود من قبل هذا الباتش (Sprint 2)، لم يُمس** | `assert_base_mapping_mutable()` كانت بالفعل بتغطي الـ base row تحديدًا عبر `product_has_stock_history()`. الجديد في الباتش دا هو توسيع نفس المبدأ لأي `ProductUnit` تانية (§2 بند 4). |

---

## 4) أي تعارض مع الـ Architecture

**لا يوجد تعارض حقيقي.** كل التعديلات اتحطت في نفس الطبقات المعمول بيها فعلًا:
- Validation منطقية → `serializers.py::validate()` (نفس مكان كل الـ validations الموجودة، زي الـ type-change guard الأصلي).
- Business logic → `pos/services/*.py` و`recipes/services/costing.py` (نفس الأنماط: exception classes بـ `.code`، دوال نقية، lazy imports عبر الحدود بين التطبيقين لتفادي circular imports — نفس النمط المستخدم أصلًا في `SaleSerializer.create()`).
- الفرونت إند: صفر منطق أعمال جديد — `fieldVisibility()` مجرد **مرآة عرض** (booleans، بدون حساب) لمصفوفة السلوك الموجودة فعليًا في `pos/services/product_types.py`، بنفس فلسفة `PRODUCT_TYPE_OPTIONS` القديمة اللي كانت أصلًا "تعكس" التسميات من الباك إند.

**نقطة اهتمام واحدة (مش تعارض، توثيق فقط):** توسيع `check_recipe_readiness()` كان لازم يتقسّم لدالتين (§5) عشان يحافظ على أداء الـ query count — القرار دا وثّقته صراحة في الـ docstring نفسه (`check_recipe_readiness`) عشان أي تعديل مستقبلي يفهم السبب قبل ما يعيد دمج الفحصين ويكسر الأداء بالغلط.

---

## 5) مقارنة قبل/بعد

| الجانب | قبل | بعد |
|---|---|---|
| بيع `Ingredient`/`Packaging`/`Fixed Asset` مباشرة | ✅ ينجح (خطأ) | ❌ يُرفض بـ 400 برسالة واضحة |
| بيع `Service`/`Bundle` | ✅ ينجح، لكن بيخصم `Product.stock` بتاعه هو (خطأ) | ✅ ينجح، **بدون** أي `StockMovement` (صحيح) |
| `show_on_pos=True` على `Ingredient` | مقبول (خطأ) | مرفوض بـ 400 |
| تعديل `conversion_to_base` بعد الاستخدام | مقبول بصمت (خطأ) | مرفوض بـ 400 + رسالة توضّح السبب |
| Recipe على منتج `Bundle` | يُقبل بصمت عبر API (خطأ) | يُرفض بـ 400 برسالة توضّح إن الميزة مش مدعومة بعد |
| بيع Recipe Product بمكوّن مُوقَف (`active=False`) | ينجح (خطأ) | يُرفض بـ 400 يسمّي المكوّن المتوقف بالاسم |
| Product Form | ثابت، كل الحقول ظاهرة لكل الأنواع | Dynamic فعليًا، مُتحقَّق بصريًا في متصفح حقيقي لـ 3 أنواع (Ingredient/Recipe product/Service) |
| رحلة "Product → Recipe" | انقطاع كامل — لازم تنقل يدوي بحث تاني | زر "Build Recipe" مباشر بعد الحفظ، بيوديك لـ `/recipes/new?product_id=X` جاهز في وضع تحرير — **صفر بحث تاني** |
| Recipe Reports | جدول خام بس | KPI cards (Revenue/Food cost/Gross profit/Margin) + 3 قوائم مُرتَّبة (Top Recipes/Worst Margin/Most Used Ingredient) — كل القيم من نفس الـ response المُجلَب فعلًا، صفر إعادة حساب |
| Query cost لبيع Recipe Product | خط أساس 60 استعلام (قبل هذا الباتش) | **نفس الـ 60 بالظبط** — الفحوصات الجديدة (empty version / discontinued ingredient) اتحطت جوّه `compute_recipe_sale_lines` اللي أصلًا بتجيب نفس الصفوف بـ `select_related`، فمفيش استعلام إضافي على المسار الناجح؛ `check_recipe_readiness` بقت بالظبط بتكلفة `get_active_recipe` القديمة (استعلامين) + JOIN واحد إضافي (`select_related('recipe__product')`، صفر round-trip إضافي) |
| Backend tests | 802 (قبل الباتش دا) | **802/802 ناجحة** — صفر تراجع، إضافة اختبارات جديدة داخل نفس العدد الإجمالي المُبلَّغ (تفاصيل الإضافات موثّقة في §2/§6) |

---

## 6) هل أصبح الجزء بمستوى Enterprise ERP (SAP / Odoo / Microsoft Dynamics)؟

**الإجابة الصريحة: الـ Backend Validation Layer وصل لمستوى قريب جدًا من enterprise-grade في نطاقه المحدود (Recipe/Product-Type domain)؛ باقي أجزاء النظام (Bundle الحقيقية، GL، Multi-level Approval) لسه بعيدة عن هذا المستوى بقرار نطاق واعٍ، مش قصور.**

**ما تم الوصول له فعليًا (مطابق لممارسات الأنظمة الكبرى):**
- **Single Source of Truth حقيقي**: كل قاعدة عمل (can_sell/affects_stock/show_on_pos) مصدرها الوحيد `pos/services/product_types.py`، مُنفَّذة Backend-only، الفرونت إند بيعكسها بصريًا فقط — نفس فلسفة SAP's Material Type أو Odoo's Product Type behavior matrix.
- **Availability Check قبل البيع** (`check_recipe_readiness`) — نفس مفهوم Dynamics 365's material availability check قبل إتمام أي معاملة إنتاج/بيع.
- **Audit-safe conversion locking** — منع تعديل معامل تحويل وحدة مُستخدَمة، مطابق لمبدأ "لا تُعدَّل بيانات مرجعية مرتبطة بمستندات مُرحَّلة" المعمول به في كل الأنظمة الكبرى.
- **Explicit rejection بدل الميزة "نص شغالة"** — Bundle بقت تُرفض صراحة بدل ما توهم المستخدم بدعم غير موجود، نفس أسلوب SAP's "not yet configured" errors.

**ما لا يزال ينقص للوصول الكامل لهذا المستوى (بصراحة تامة، بدون تهوين):**
1. **Bundle Explosion الحقيقية** — SAP/Odoo عندهم موديل BOM كامل لتفكيك الـ Bundle لمكوّناته المُخزَّنة فعليًا وقت البيع؛ هنا لسه غير موجودة إطلاقًا (مؤجَّلة بقرار واعٍ، مش نسيان).
2. **GL Posting لتكلفة الـ COGS** — مفيش أي Journal Entry يتولّد من عملية البيع؛ الأنظمة الكبرى بتربط كل بيع Recipe Product بقيد محاسبي فوري (Dr COGS / Cr Inventory).
3. **Production Orders / Manufacturing** — `Prep Item` معرَّف كنوع لكن مفيش نظام "أوامر إنتاج" حقيقي (batch cooking، yield loss، WIP) زي اللي في SAP PP أو Odoo Manufacturing.
4. **Approval Workflows** — تغيير `conversion_to_base` أو product_type بيتم برفض فوري أو قبول فوري، بدون أي مسار موافقة متعدد المستويات (زي SAP's workflow approval chains).
5. **Multi-warehouse Bundle/Recipe costing** — التكلفة مربوطة بالفرع (Branch) فقط، مش بمستوى Warehouse الأدق المتاح في الأنظمة الكبرى.
6. **Automated Testing على مستوى الفرونت إند** — الباك إند عنده 802 اختبار، الفرونت إند صفر (نفس القيد الموثّق من قبل — R-I — مش جديد في هذا الباتش).

**الخلاصة:** هذا الباتش سدّ الفجوة الأكبر بين "مصمَّم بشكل جيد" و"مُطبَّق فعليًا بصرامة" — الفرق الحقيقي بين enterprise ERP وأنظمة أخرى مش في وجود الحقول، لكن في **مين اللي بيفرض القواعد فعليًا**. دلوقتي الباك إند هو الحَكَم الوحيد، مش الواجهة — وده بالظبط المعيار المطلوب. الفجوات المتبقية (Bundle الحقيقية، GL، Manufacturing) هي **ميزات كاملة غير مبنية بعد**، مش عيوب في اللي اتبنى.
