"""Robustness katmanları birim testi"""
import sys, json
sys.path.insert(0, r'c:\Users\furkan\Desktop\SQLGen\backend')
from app.sql_pipeline import enrich_aqr_from_natural_query, validate_columns_against_schema, enforce_oracle_case
from app.schema_manager import SchemaManager

# Şema yükle
sm = SchemaManager()
schema = sm.load_schema()

# === TEST 1: AQR Zenginleştirme ===
print("=== TEST 1: AQR Zenginlestirme ===")
aqr = {
    "natural_query": "ulkelere gore siparis sayisinin sorgusunu istiyorum",
    "entities": [], "fields": [], "filters": [],
    "aggregations": [], "sorts": [], "business_rules": []
}
enriched = enrich_aqr_from_natural_query(aqr, schema)
print("Entities:", enriched["entities"])
print("Fields:", enriched["fields"])
print("Aggregations:", enriched["aggregations"])
assert "ORDERS" in enriched["entities"], "FAIL: ORDERS should be in entities"
assert "CUSTOMERS" in enriched["entities"], "FAIL: CUSTOMERS should be in entities"
print("TEST 1 PASSED\n")

# === TEST 2: Semantik Doğrulama (hatalı SQL) ===
print("=== TEST 2: Semantik Dogrulama (hatali SQL) ===")
bad_sql = "SELECT country, COUNT(order_id) AS order_count FROM orders GROUP BY country ORDER BY order_count DESC"
pruned = {"tables": {"ORDERS": schema["tables"]["ORDERS"]}}
valid, err = validate_columns_against_schema(bad_sql, pruned, dialect="oracle")
print("Valid:", valid)
print("Error:", err[:300])
assert not valid, "FAIL: bad SQL should be invalid"
assert "COUNTRY" in err, "FAIL: error should mention COUNTRY column"
print("TEST 2 PASSED\n")

# === TEST 3: Semantik Doğrulama (doğru SQL) ===
print("=== TEST 3: Semantik Dogrulama (dogru SQL) ===")
good_sql = "SELECT C.COUNTRY, COUNT(O.ORDER_ID) AS SIPARIS_SAYISI FROM CUSTOMERS C JOIN ORDERS O ON C.CUSTOMER_ID = O.CUSTOMER_ID GROUP BY C.COUNTRY ORDER BY SIPARIS_SAYISI DESC"
pruned2 = {"tables": {"ORDERS": schema["tables"]["ORDERS"], "CUSTOMERS": schema["tables"]["CUSTOMERS"]}}
valid2, err2 = validate_columns_against_schema(good_sql, pruned2, dialect="oracle")
print("Valid:", valid2)
print("Error:", err2)
assert valid2, "FAIL: good SQL should be valid"
print("TEST 3 PASSED\n")

# === TEST 4: Oracle Case Enforcement ===
print("=== TEST 4: Oracle Case Enforcement ===")
lower_sql = "SELECT c.country, COUNT(o.order_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.country"
upper_sql = enforce_oracle_case(lower_sql, dialect="oracle")
print("Result:", upper_sql)
assert "COUNTRY" in upper_sql, "FAIL: identifiers should be uppercase"
assert "CUSTOMERS" in upper_sql, "FAIL: table names should be uppercase"
print("TEST 4 PASSED\n")

# === TEST 5: AQR Zenginleştirme (Türkçe karakterli) ===
print("=== TEST 5: AQR Zenginlestirme (Turkce karakterli) ===")
aqr2 = {
    "natural_query": "hangi ülkeden kaç sipariş geldiğinin sorgusunu istiyorum",
    "entities": [], "fields": [], "filters": [],
    "aggregations": [], "sorts": [], "business_rules": []
}
enriched2 = enrich_aqr_from_natural_query(aqr2, schema)
print("Entities:", enriched2["entities"])
print("Fields:", enriched2["fields"])
print("Aggregations:", enriched2["aggregations"])
assert "ORDERS" in enriched2["entities"], "FAIL: ORDERS should be in entities"
print("TEST 5 PASSED\n")

print("=" * 50)
print("ALL TESTS PASSED!")
