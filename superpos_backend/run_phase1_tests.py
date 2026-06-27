"""
Phase 1 — End-to-end API test runner
Run with:  python run_phase1_tests.py
"""
import json
import sys
from urllib import request as urlreq
from urllib import error as urlerr

BASE = "http://127.0.0.1:8000/api"

# ── HTTP helper ────────────────────────────────────────────────────────────────

def http(method, path, token=None, body=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urlreq.Request(url, data=data, headers=headers, method=method)
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urlerr.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"null")
        except Exception:
            payload = None
        return e.code, payload
    except Exception as e:
        return None, str(e)


# ── Login ──────────────────────────────────────────────────────────────────────

def login(username, password):
    code, body = http("POST", "/auth/login/", body={"username": username, "password": password})
    if code != 200:
        print(f"[FAIL] login {username}: {code} {body}")
        sys.exit(1)
    return body["access"], body.get("user", {})


# ── Result tracker ─────────────────────────────────────────────────────────────

results = []

def check(label, expected, actual, extra=""):
    passed = actual == expected
    icon   = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {label:55s} expected={expected} got={actual}  {extra}")
    results.append({"label": label, "expected": expected, "actual": actual, "passed": passed, "extra": extra})
    return passed


# ── Main run ───────────────────────────────────────────────────────────────────

print("\n" + "="*70)
print("  PHASE 1 — SUPERPOS API TEST SUITE")
print("="*70)

# Login all 3 users
owner_t,   owner_u   = login("karim",   "12345678")
manager_t, manager_u = login("mohamed", "12345678")
cashier_t, cashier_u = login("ziad",    "12345678")

print(f"\nLoggedin: owner=karim(role={owner_u['role']}), "
      f"manager=mohamed(role={manager_u['role']}), "
      f"cashier=ziad(role={cashier_u['role']})")

# ════════════════════════════════════════════════════════════════════════════════
# 1. RBAC TESTING
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "─"*70)
print("  1. RBAC TESTING")
print("─"*70)

print("\n[Cashier — ziad]")
code, _ = http("GET",    "/products/",                token=cashier_t);                              check("Cashier: GET /products/",        200, code)
code, _ = http("DELETE", "/products/1/",              token=cashier_t);                              check("Cashier: DELETE /products/1/",   403, code)
code, _ = http("GET",    "/dashboard/summary/",       token=cashier_t);                              check("Cashier: GET /dashboard/summary",403, code)
code, _ = http("POST",   "/products/",                token=cashier_t,
               body={"barcode":"x","sku":"x","name":"x","price":1,"cost":1});                        check("Cashier: POST /products/",       403, code)
code, _ = http("GET",    "/auth/users/",              token=cashier_t);                              check("Cashier: GET /auth/users/",      403, code)
code, _ = http("POST",   "/inventory/purchase/",      token=cashier_t,
               body={"product":1,"qty":1});                                                          check("Cashier: POST /inventory/purchase",403, code)

print("\n[Manager — mohamed]")
code, body = http("POST", "/products/", token=manager_t, body={
    "barcode": "999111222333", "sku": "TST-001", "name": "Test Product",
    "category": 1, "price": "10.00", "cost": "7.00", "tax_rate": "0.14",
    "stock": 50, "reorder": 10, "color": "#000000", "weighted": False,
    "unit": "piece", "active": True,
})
check("Manager: POST /products/", 201, code)
test_product_id = body.get("id") if isinstance(body, dict) else None

code, body = http("POST", "/inventory/purchase/", token=manager_t,
                  body={"product": test_product_id or 1, "qty": "20", "cost_price": "7.50"})
check("Manager: POST /inventory/purchase/", 201, code)

code, _ = http("GET", "/dashboard/summary/", token=manager_t);     check("Manager: GET /dashboard/summary/", 200, code)
code, _ = http("GET", "/auth/users/",        token=manager_t);     check("Manager: GET /auth/users/",        200, code)

print("\n[Owner — karim]")
code, _ = http("GET", "/products/",           token=owner_t); check("Owner: GET /products/",           200, code)
code, _ = http("GET", "/dashboard/summary/",  token=owner_t); check("Owner: GET /dashboard/summary/",  200, code)
code, _ = http("GET", "/auth/users/",         token=owner_t); check("Owner: GET /auth/users/",         200, code)
code, _ = http("GET", "/inventory/alerts/",   token=owner_t); check("Owner: GET /inventory/alerts/",   200, code)


# ════════════════════════════════════════════════════════════════════════════════
# 2. BUSINESS FLOW TESTING
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "─"*70)
print("  2. BUSINESS FLOW TESTING")
print("─"*70)

print("\n[Normal sale — qty < stock]")
code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "1", "price_each": "7.00"}],
    "method": "cash",
    "paid": "10.00",
})
sale_ok_uuid = body.get("sale_uuid") if isinstance(body, dict) else None
sale_ok_pk   = body.get("id")        if isinstance(body, dict) else None
warnings_normal = body.get("warnings", []) if isinstance(body, dict) else []
check("Normal sale create",     201, code, f"warnings={len(warnings_normal)}")
check("Normal sale: no warnings", 0,  len(warnings_normal))

print("\n[Oversell — qty > stock]")
code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 1, "qty": "99999", "price_each": "4.32"}],
    "method": "cash",
    "paid": "999999.00",
})
warnings_over = body.get("warnings", []) if isinstance(body, dict) else []
check("Oversell sale create",          201, code, f"warnings={len(warnings_over)}")
check("Oversell: warnings present",     True, len(warnings_over) > 0,
      f"sample={warnings_over[0] if warnings_over else None}")

print("\n[Discount — percent 10%]")
code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "2", "price_each": "10.00"}],
    "method": "card",
    "paid": "30.00",
    "discount_type": "percent",
    "discount_value": "10",
})
check("Discount percent sale", 201, code, f"total={body.get('total') if isinstance(body, dict) else None}")

print("\n[Discount — fixed 5]")
code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "1", "price_each": "7.00"}],
    "method": "cash",
    "paid": "20.00",
    "discount_type": "fixed",
    "discount_value": "5",
})
check("Discount fixed sale", 201, code, f"total={body.get('total') if isinstance(body, dict) else None}")

print("\n[Validation errors]")
code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "0", "price_each": "7.00"}],
    "method": "cash", "paid": "10",
})
check("Validation: qty=0", 400, code)

code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "1.5", "price_each": "7.00"}],
    "method": "cash", "paid": "20",
})
check("Validation: qty=1.5 piece product", 400, code)

code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "5", "price_each": "7.00"}],
    "method": "cash", "paid": "1.00",
})
check("Validation: paid < total", 400, code)

code, body = http("POST", "/sales/", token=cashier_t, body={
    "items": [{"product": 2, "qty": "1", "price_each": "7.00"}],
    "method": "cash", "paid": "100",
    "discount_type": "percent", "discount_value": "150",
})
check("Validation: discount 150%", 400, code)

# ════════════════════════════════════════════════════════════════════════════════
# 3. DASHBOARD TESTING
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "─"*70)
print("  3. DASHBOARD APIs")
print("─"*70)

code, body = http("GET", "/dashboard/summary/", token=manager_t)
check("Dashboard summary (no date)", 200, code,
      f"today_total={body.get('today',{}).get('total') if isinstance(body, dict) else None}")

code, body = http("GET", "/dashboard/daily-stats/", token=manager_t)
check("Dashboard daily-stats (today)", 200, code,
      f"date={body.get('date') if isinstance(body, dict) else None}")

code, body = http("GET", "/dashboard/daily-stats/?date=2026-05-14", token=manager_t)
check("Dashboard daily-stats (yesterday filter)", 200, code,
      f"total={body.get('total_sales') if isinstance(body, dict) else None}")

code, body = http("GET", "/dashboard/daily-stats/?date=2026-05-08", token=manager_t)
check("Dashboard daily-stats (last week filter)", 200, code,
      f"total={body.get('total_sales') if isinstance(body, dict) else None}")

code, body = http("GET", "/dashboard/daily-stats/?date=INVALID", token=manager_t)
check("Dashboard daily-stats (invalid date)", 400, code)

code, body = http("GET", "/dashboard/top-products/", token=manager_t)
check("Dashboard top-products", 200, code,
      f"count={len(body) if isinstance(body, list) else 'N/A'}")

code, body = http("GET", "/dashboard/low-stock/", token=manager_t)
check("Dashboard low-stock", 200, code,
      f"count={body.get('count') if isinstance(body, dict) else None}")


# ════════════════════════════════════════════════════════════════════════════════
# 4. UUID + 404 TESTING
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "─"*70)
print("  4. UUID-BASED ENDPOINTS + 404")
print("─"*70)

if sale_ok_uuid:
    code, body = http("GET", f"/sales/{sale_ok_uuid}/", token=cashier_t)
    check("GET sale by UUID", 200, code, f"id={body.get('id') if isinstance(body, dict) else None}")

if sale_ok_pk:
    code, body = http("GET", f"/sales/{sale_ok_pk}/", token=cashier_t)
    check("GET sale by PK", 200, code)

if sale_ok_uuid:
    code, body = http("POST", f"/sales/{sale_ok_uuid}/void/", token=manager_t)
    check("POST void sale by UUID", 200, code,
          f"status={body.get('status') if isinstance(body, dict) else None}")

    # Second void should fail
    code, body = http("POST", f"/sales/{sale_ok_uuid}/void/", token=manager_t)
    check("POST void already-voided sale", 400, code)

code, _ = http("GET",  "/sales/999999/",                                       token=cashier_t); check("GET sale 404 (PK)",   404, code)
code, _ = http("GET",  "/sales/00000000-0000-0000-0000-000000000000/",         token=cashier_t); check("GET sale 404 (UUID)", 404, code)
code, _ = http("GET",  "/products/999999/",                                    token=owner_t);   check("GET product 404",     404, code)


# ════════════════════════════════════════════════════════════════════════════════
# 5. AUTH / NO-TOKEN TESTING
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "─"*70)
print("  5. AUTH / NO-TOKEN")
print("─"*70)

code, _ = http("GET", "/products/");                check("No token: GET /products/",         401, code)
code, _ = http("GET", "/dashboard/summary/");       check("No token: GET /dashboard/summary/",401, code)
code, _ = http("POST", "/sales/", body={});         check("No token: POST /sales/",           401, code)

# Invalid token
code, _ = http("GET", "/products/", token="bad.token.here");
check("Bad token: GET /products/", 401, code)


# ════════════════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════════════════
total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed

print("\n" + "="*70)
print(f"  RESULTS: {passed}/{total} passed   ({failed} failed)")
print("="*70)

if failed:
    print("\nFailed tests:")
    for r in results:
        if not r["passed"]:
            print(f"  - {r['label']}: expected {r['expected']}, got {r['actual']}")

# Persist machine-readable summary
with open("phase1_test_results.json", "w", encoding="utf-8") as f:
    json.dump({"total": total, "passed": passed, "failed": failed, "results": results},
              f, indent=2, ensure_ascii=False)

print("\nSaved phase1_test_results.json")
