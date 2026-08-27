-- Sprint 29.5 deterministic MySQL integration fixture.
-- Applied once against a fresh mysql:8.4 sqlgen_test DB as MYSQL_USER=sqlgen.
-- Mirrors the Postgres 29.0 / Oracle 29.4 seed shape. No stored procedures.
CREATE TABLE customers (
    id         INT PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    email      VARCHAR(200),
    created_at DATETIME
) ENGINE=InnoDB;
CREATE TABLE orders (
    id          INT PRIMARY KEY,
    customer_id INT NOT NULL,
    status      VARCHAR(50),
    total       DECIMAL(10, 2),
    ordered_at  DATETIME,
    FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;
CREATE TABLE order_items (
    id           INT PRIMARY KEY,
    order_id     INT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    qty          INT NOT NULL,
    unit_price   DECIMAL(10, 2),
    FOREIGN KEY (order_id) REFERENCES orders (id)
) ENGINE=InnoDB;
CREATE TABLE product_variants (
    product_id INT NOT NULL,
    sku        VARCHAR(50) NOT NULL,
    label      VARCHAR(200),
    PRIMARY KEY (product_id, sku)
) ENGINE=InnoDB;
CREATE TABLE variant_stock (
    id         INT PRIMARY KEY,
    product_id INT NOT NULL,
    sku        VARCHAR(50) NOT NULL,
    qty        INT NOT NULL,
    FOREIGN KEY (product_id, sku) REFERENCES product_variants (product_id, sku)
) ENGINE=InnoDB;
INSERT INTO customers (id, name, email, created_at) VALUES (1, 'Ada Lovelace', 'ada@example.com', '2020-01-01 00:00:00');
INSERT INTO customers (id, name, email, created_at) VALUES (2, 'Alan Turing', 'alan@example.com', '2020-01-02 00:00:00');
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (1, 1, 'paid', 120.00, '2021-03-01 10:00:00');
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (2, 1, 'pending', 45.50, '2021-03-02 11:00:00');
INSERT INTO orders (id, customer_id, status, total, ordered_at) VALUES (3, 2, 'paid', 10.00, '2021-03-03 12:00:00');
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (1, 1, 'Widget', 2, 50.00);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (2, 1, 'Gadget', 1, 20.00);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (3, 2, 'Widget', 1, 45.50);
INSERT INTO order_items (id, order_id, product_name, qty, unit_price) VALUES (4, 3, 'Gizmo', 5, 2.00);
INSERT INTO product_variants (product_id, sku, label) VALUES (10, 'RED-S', 'Red Small');
INSERT INTO product_variants (product_id, sku, label) VALUES (10, 'RED-L', 'Red Large');
INSERT INTO variant_stock (id, product_id, sku, qty) VALUES (1, 10, 'RED-S', 5);
INSERT INTO variant_stock (id, product_id, sku, qty) VALUES (2, 10, 'RED-L', 3);
