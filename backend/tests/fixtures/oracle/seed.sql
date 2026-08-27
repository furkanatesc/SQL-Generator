-- Sprint 29.4 deterministic Oracle integration fixture.
-- Applied once against a fresh gvenzl/oracle-free FREEPDB1 as APP_USER=sqlgen.
-- Mirrors the Postgres 29.0 seed shape. No PL/SQL, plain DDL + INSERT only.
CREATE TABLE customers (
    id         NUMBER PRIMARY KEY,
    name       VARCHAR2(200) NOT NULL,
    email      VARCHAR2(200),
    created_at TIMESTAMP
);
CREATE TABLE orders (
    id          NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL REFERENCES customers (id),
    status      VARCHAR2(50),
    total       NUMBER(10, 2),
    ordered_at  TIMESTAMP
);
CREATE TABLE order_items (
    id           NUMBER PRIMARY KEY,
    order_id     NUMBER NOT NULL REFERENCES orders (id),
    product_name VARCHAR2(200) NOT NULL,
    qty          NUMBER NOT NULL,
    unit_price   NUMBER(10, 2)
);
CREATE TABLE product_variants (
    product_id NUMBER NOT NULL,
    sku        VARCHAR2(50) NOT NULL,
    label      VARCHAR2(200),
    PRIMARY KEY (product_id, sku)
);
CREATE TABLE variant_stock (
    id         NUMBER PRIMARY KEY,
    product_id NUMBER NOT NULL,
    sku        VARCHAR2(50) NOT NULL,
    qty        NUMBER NOT NULL,
    FOREIGN KEY (product_id, sku) REFERENCES product_variants (product_id, sku)
);
INSERT INTO customers (id, name, email, created_at) VALUES (1, 'Ada Lovelace', 'ada@example.com', TO_TIMESTAMP('2020-01-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS'));
INSERT INTO customers (id, name, email, created_at) VALUES (2, 'Alan Turing', 'alan@example.com', TO_TIMESTAMP('2020-01-02 00:00:00', 'YYYY-MM-DD HH24:MI:SS'));
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (1, 1, 'paid', 120.00, TO_TIMESTAMP('2021-03-01 10:00:00', 'YYYY-MM-DD HH24:MI:SS'));
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (2, 1, 'pending', 45.50, TO_TIMESTAMP('2021-03-02 11:00:00', 'YYYY-MM-DD HH24:MI:SS'));
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (3, 2, 'paid', 10.00, TO_TIMESTAMP('2021-03-03 12:00:00', 'YYYY-MM-DD HH24:MI:SS'));
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (1, 1, 'Widget', 2, 50.00);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (2, 1, 'Gadget', 1, 20.00);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (3, 2, 'Widget', 1, 45.50);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (4, 3, 'Gizmo', 5, 2.00);
INSERT INTO product_variants (product_id, sku, label) VALUES (10, 'RED-S', 'Red Small');
INSERT INTO product_variants (product_id, sku, label) VALUES (10, 'RED-L', 'Red Large');
INSERT INTO variant_stock (id, product_id, sku, qty) VALUES (1, 10, 'RED-S', 5);
INSERT INTO variant_stock (id, product_id, sku, qty) VALUES (2, 10, 'RED-L', 3);
