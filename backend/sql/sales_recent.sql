-- The latest 100 orders.
SELECT
  s.order_id,
  MIN(s.order_date) AS order_date,
  ANY_VALUE(s.channel) AS channel,
  ANY_VALUE(s.customer_id) AS customer_id,
  SUM(s.qty) AS units,
  SUM(s.qty * s.unit_price_inr) AS value,
  LOGICAL_OR(s.returned) AS has_return,
  STRING_AGG(p.name, ', ') AS items
FROM `{dataset}.sales` s
JOIN `{dataset}.products` p ON p.sku = s.sku
GROUP BY s.order_id
ORDER BY order_date DESC, order_id DESC
LIMIT 100
