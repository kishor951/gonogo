-- Customers who ordered in the last 12 months, by age band and by city.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT s.customer_id, s.order_id, s.qty, s.returned, s.unit_price_inr, c.age_band, c.city
  FROM `{dataset}.sales` s
  JOIN `{dataset}.customers` c ON c.customer_id = s.customer_id
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
)
SELECT
  'age_band' AS dimension, age_band AS label,
  COUNT(DISTINCT customer_id) AS customers, COUNT(DISTINCT order_id) AS orders,
  SUM(IF(returned, 0, qty * unit_price_inr)) AS revenue
FROM lines
GROUP BY age_band
UNION ALL
SELECT
  'city' AS dimension, city AS label,
  COUNT(DISTINCT customer_id) AS customers, COUNT(DISTINCT order_id) AS orders,
  SUM(IF(returned, 0, qty * unit_price_inr)) AS revenue
FROM lines
GROUP BY city
