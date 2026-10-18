-- The 50 customers who spent the most in the last 12 months.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
)
SELECT
  c.customer_id, c.age_band, c.city, c.first_order_date,
  COUNT(DISTINCT s.order_id) AS orders,
  SUM(s.qty) AS units,
  SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue,
  SUM(IF(s.returned, s.qty, 0)) AS returned_units,
  MAX(s.order_date) AS last_order
FROM `{dataset}.sales` s
JOIN `{dataset}.customers` c ON c.customer_id = s.customer_id
CROSS JOIN anchor
WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
GROUP BY c.customer_id, c.age_band, c.city, c.first_order_date
ORDER BY revenue DESC
LIMIT 50
