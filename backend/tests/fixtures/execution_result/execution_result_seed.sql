-- Create schema for SQLite compatible tables
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name VARCHAR,
  email VARCHAR
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER,
  order_date DATE,
  total_amount DECIMAL,
  FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE payments (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  payment_method VARCHAR,
  amount DECIMAL,
  FOREIGN KEY(order_id) REFERENCES orders(id)
);

CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  name VARCHAR,
  price DECIMAL
);

CREATE TABLE order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  product_id INTEGER,
  quantity INTEGER,
  unit_price DECIMAL,
  FOREIGN KEY(order_id) REFERENCES orders(id),
  FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username VARCHAR,
  password_hash VARCHAR,
  role VARCHAR
);

CREATE TABLE audit_logs (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  action VARCHAR,
  timestamp TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE support_tickets (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER,
  subject VARCHAR,
  status VARCHAR,
  FOREIGN KEY(customer_id) REFERENCES customers(id)
);

-- Seed data for customers
INSERT INTO customers (id, name, email) VALUES
  (1, 'Alice', 'alice@example.com'),
  (2, 'Bob', 'bob@example.com');

-- Seed data for orders
INSERT INTO orders (id, customer_id, order_date, total_amount) VALUES
  (101, 1, '2026-01-01', 120.00),
  (102, 1, '2026-01-05', 80.00),
  (103, 2, '2026-01-10', 200.00);

-- Seed data for payments
INSERT INTO payments (id, order_id, payment_method, amount) VALUES
  (1001, 101, 'card', 120.00),
  (1002, 102, 'cash', 80.00),
  (1003, 103, 'card', 200.00);

-- Seed data for products
INSERT INTO products (id, name, price) VALUES
  (1, 'Keyboard', 50.00),
  (2, 'Mouse', 20.00),
  (3, 'Monitor', 300.00);

-- Seed data for order_items (Keyboard x2, Mouse x1 = 120.00 for order 101)
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES
  (5001, 101, 1, 2, 50.00),
  (5002, 101, 2, 1, 20.00),
  (5003, 102, 2, 4, 20.00),
  (5004, 103, 3, 1, 200.00);

-- Seed data for users
INSERT INTO users (id, username, password_hash, role) VALUES
  (10, 'admin', 'hash123', 'admin'),
  (11, 'user1', 'hash456', 'user');

-- Seed data for audit_logs
INSERT INTO audit_logs (id, user_id, action, timestamp) VALUES
  (201, 10, 'logout', '2026-01-01 10:00:00'),
  (202, 10, 'login', '2026-01-01 12:00:00'),
  (203, 11, 'view_dashboard', '2026-01-01 13:00:00');

-- Seed data for support_tickets
INSERT INTO support_tickets (id, customer_id, subject, status) VALUES
  (301, 1, 'Cannot login', 'open'),
  (302, 1, 'Refund request', 'closed'),
  (303, 2, 'Payment issue', 'open');
