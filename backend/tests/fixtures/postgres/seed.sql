-- Sprint 29.0 deterministic integration fixture. Idempotent.
DROP TABLE IF EXISTS variant_stock CASCADE;
DROP TABLE IF EXISTS product_variants CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT,
    created_at TIMESTAMP
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    status      TEXT,
    total       NUMERIC(10, 2),
    ordered_at  TIMESTAMP
);

CREATE TABLE order_items (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders (id),
    product_name TEXT NOT NULL,
    qty          INTEGER NOT NULL,
    unit_price   NUMERIC(10, 2)
);

CREATE TABLE product_variants (
    product_id INTEGER NOT NULL,
    sku        TEXT NOT NULL,
    label      TEXT,
    PRIMARY KEY (product_id, sku)
);

CREATE TABLE variant_stock (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    sku        TEXT NOT NULL,
    qty        INTEGER NOT NULL,
    FOREIGN KEY (product_id, sku) REFERENCES product_variants (product_id, sku)
);

INSERT INTO customers (id, name, email, created_at) VALUES
    (1, 'Ada Lovelace', 'ada@example.com', '2020-01-01 00:00:00'),
    (2, 'Alan Turing',  'alan@example.com', '2020-01-02 00:00:00');

INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES
    (1, 1, 'paid',    120.00, '2021-03-01 10:00:00'),
    (2, 1, 'pending',  45.50, '2021-03-02 11:00:00'),
    (3, 2, 'paid',     10.00, '2021-03-03 12:00:00');

INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES
    (1, 1, 'Widget', 2, 50.00),
    (2, 1, 'Gadget', 1, 20.00),
    (3, 2, 'Widget', 1, 45.50),
    (4, 3, 'Gizmo',  5,  2.00);

INSERT INTO product_variants (product_id, sku, label) VALUES
    (10, 'RED-S', 'Red Small'),
    (10, 'RED-L', 'Red Large');

INSERT INTO variant_stock (id, product_id, sku, qty) VALUES
    (1, 10, 'RED-S', 5),
    (2, 10, 'RED-L', 3);
