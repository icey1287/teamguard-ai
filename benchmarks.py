"""Synthetic e-commerce context and frozen development benchmark (no customer data)."""

from contracts import Rule, Rulebook

SCHEMA = """CREATE TABLE customers (
    customer_id INT PRIMARY KEY, country VARCHAR(2),
    is_test BOOLEAN, signup_at DATETIME
);
CREATE TABLE orders (
    order_id INT PRIMARY KEY, customer_id INT,
    status VARCHAR(20), total_amount DECIMAL(12,2), created_at DATETIME
);
CREATE TABLE payments (
    payment_id INT PRIMARY KEY, order_id INT,
    status VARCHAR(20), amount DECIMAL(12,2), paid_at DATETIME
);
CREATE TABLE returns (
    return_id INT PRIMARY KEY, order_id INT,
    status VARCHAR(20), refunded_amount DECIMAL(12,2)
);"""

RULES = (
    "Recognized revenue is SUM(orders.total_amount) for orders with status = 'paid', excluding any order with a completed return (returns.status = 'completed'). Pending returns do not exclude an order. Use NOT EXISTS or equivalent logic.",
    "The paid-order count counts distinct orders.order_id with orders.status = 'paid'. Unpaid and cancelled orders must not contribute; returned orders still count as paid orders.",
    "Customer-base metrics (counts of registered customers by country or signup date) exclude test accounts: customers.is_test = 0.",
    "Payment receipts sum payments.amount only where payments.status = 'captured'; pending or failed payments must not contribute. Receipts are separate from recognized revenue.",
    "Refund totals sum returns.refunded_amount only where returns.status = 'completed'. Pending or rejected returns must not contribute.",
    "An order may have multiple payments and multiple returns. Recognized revenue must count each eligible order amount exactly once; joining raw payment or return rows can multiply revenue. SUM(DISTINCT total_amount) is not a valid deduplication because different orders may have equal amounts.",
    "The October 2026 paid-order report uses orders.created_at >= '2026-10-01' AND orders.created_at < '2026-11-01'. DATETIME values on October 31 must be included and November 1 must be excluded.",
    "The paying-customer metric counts distinct orders.customer_id from orders with status = 'paid', not the number of order rows. Multiple paid orders by the same customer count once.",
)

BENCHMARK_BOOK = Rulebook(project_id="demo-commerce", project_name="Commerce Analytics · Demo", version=1,
                     schema_sql=SCHEMA, rules=tuple(Rule(id=f"R{i:03d}", text=t) for i, t in enumerate(RULES, 1)))

REVENUE_FILTER = "o.status = 'paid' AND NOT EXISTS (SELECT 1 FROM returns r WHERE r.order_id = o.order_id AND r.status = 'completed')"
GOOD_REVENUE = f"SELECT SUM(o.total_amount) AS recognized_revenue\nFROM orders o\nWHERE {REVENUE_FILTER};"
BAD_REVENUE = "SELECT SUM(total_amount) AS recognized_revenue\nFROM orders;"
# Labels are developer-authored hypotheses, not external/manual validation results.
# One expected issue per case keeps category/rule matching reproducible.
def benchmark_cases():
    cases = []

    def add(group, title, sql, expected=(), severe=False):
        cases.append({"id": f"{group}-{sum(c['group'] == group for c in cases) + 1:02d}",
                      "group": group, "title": title, "sql": sql,
                      "expected": list(expected), "severe": severe})

    clean = [
        ("Recognized revenue", GOOD_REVENUE),
        ("Paid-order count", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders WHERE status = 'paid';"),
        ("Customer base", "SELECT country, COUNT(*) AS customers FROM customers WHERE is_test = 0 GROUP BY country;"),
        ("Captured receipts", "SELECT SUM(amount) AS payment_receipts FROM payments WHERE status = 'captured';"),
        ("Completed refunds", "SELECT SUM(refunded_amount) AS refunds FROM returns WHERE status = 'completed';"),
        ("October paid orders", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders WHERE status = 'paid' AND created_at >= '2026-10-01' AND created_at < '2026-11-01';"),
        ("Paying customers", "SELECT COUNT(DISTINCT customer_id) AS paying_customers FROM orders WHERE status = 'paid';"),
        ("Read-only detail", "SELECT order_id, status, total_amount FROM orders ORDER BY order_id LIMIT 20;"),
        ("CTE paid count", "WITH paid AS (SELECT order_id FROM orders WHERE status = 'paid') SELECT COUNT(DISTINCT order_id) AS paid_orders FROM paid;"),
        ("Correlated revenue by country", f"SELECT c.country, SUM(o.total_amount) AS recognized_revenue FROM orders o JOIN customers c ON c.customer_id = o.customer_id WHERE {REVENUE_FILTER} GROUP BY c.country;"),
        ("Comment after terminator", "SELECT order_id FROM orders LIMIT 5; -- analyst preview"),
        ("Union detail", "SELECT order_id FROM orders WHERE status = 'paid' UNION ALL SELECT order_id FROM orders WHERE status = 'pending';"),
    ]
    for title, sql in clean:
        add("clean", title, sql)
    for title, sql in [
        ("Invented table", "SELECT * FROM invoices;"),
        ("Invented column", "SELECT net_revenue FROM orders;"),
        ("Ambiguous column", "SELECT order_id FROM orders o JOIN payments p ON o.order_id = p.order_id;"),
        ("Cross-database table", "SELECT * FROM production.orders;"),
        ("Unknown alias", "SELECT x.order_id FROM orders o;"),
        ("Missing CTE column", "WITH q AS (SELECT order_id FROM orders) SELECT amount FROM q;"),
        ("Unknown nested table", "SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM staff);"),
        ("Unknown join column", "SELECT o.order_id FROM orders o JOIN payments p ON o.invoice_id = p.order_id;"),
    ]:
        add("schema", title, sql, ("schema",), True)
    for title, sql in [
        ("Delete", "DELETE FROM orders;"),
        ("Update", "UPDATE orders SET total_amount = 0;"),
        ("Drop", "DROP TABLE orders;"),
        ("Multiple statements", "SELECT * FROM orders; DELETE FROM orders;"),
        ("File access", "SELECT LOAD_FILE('/etc/passwd');"),
        ("Sleep", "SELECT SLEEP(10);"),
        ("Row lock", "SELECT * FROM orders FOR UPDATE;"),
        ("Variable assignment", "SELECT @amount := 100;"),
    ]:
        add("safety", title, sql, ("safety",), True)
    for title, sql in [
        ("Missing projection", "SELECT FROM orders;"),
        ("Incomplete predicate", "SELECT order_id FROM orders WHERE"),
        ("Unclosed function", "SELECT SUM(total_amount FROM orders;"),
        ("Trailing comma", "SELECT order_id, FROM orders;"),
    ]:
        add("syntax", title, sql, ("syntax",), True)
    metrics = [
        ("Revenue misses paid filter", "SELECT SUM(o.total_amount) AS recognized_revenue FROM orders o WHERE NOT EXISTS (SELECT 1 FROM returns r WHERE r.order_id = o.order_id AND r.status = 'completed');", "R001"),
        ("Revenue includes returns", "SELECT SUM(total_amount) AS recognized_revenue FROM orders WHERE status = 'paid';", "R001"),
        ("Order count includes pending", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders;", "R002"),
        ("Order count includes cancelled", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders WHERE status IN ('paid', 'cancelled');", "R002"),
        ("Customer count includes tests", "SELECT COUNT(*) AS registered_customers FROM customers;", "R003"),
        ("Country customer count includes tests", "SELECT country, COUNT(*) AS registered_customers FROM customers GROUP BY country;", "R003"),
        ("Receipts include pending", "SELECT SUM(amount) AS payment_receipts FROM payments;", "R004"),
        ("Receipts include failed", "SELECT SUM(amount) AS payment_receipts FROM payments WHERE status IN ('captured', 'failed');", "R004"),
        ("Refunds include pending", "SELECT SUM(refunded_amount) AS refunds FROM returns;", "R005"),
        ("Refunds include rejected", "SELECT SUM(refunded_amount) AS refunds FROM returns WHERE status != 'pending';", "R005"),
        ("Payment fan-out", f"SELECT SUM(o.total_amount) AS recognized_revenue FROM orders o JOIN payments p ON p.order_id = o.order_id WHERE {REVENUE_FILTER};", "R006"),
        ("Distinct amount loses orders", f"SELECT SUM(DISTINCT o.total_amount) AS recognized_revenue FROM orders o WHERE {REVENUE_FILTER};", "R006"),
        ("October loses last day", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders WHERE status = 'paid' AND created_at BETWEEN '2026-10-01' AND '2026-10-31';", "R007"),
        ("October includes November", "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM orders WHERE status = 'paid' AND created_at >= '2026-10-01' AND created_at <= '2026-11-01';", "R007"),
        ("Paying customers count rows", "SELECT COUNT(customer_id) AS paying_customers FROM orders WHERE status = 'paid';", "R008"),
        ("Paying customers include unpaid", "SELECT COUNT(DISTINCT customer_id) AS paying_customers FROM orders;", "R008"),
    ]
    for title, sql, rule in metrics:
        add("metric", title, sql, (f"metric:{rule}",), True)
    return cases
