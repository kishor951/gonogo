-- Sales by calendar month, newest first (the current month may be incomplete).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
)
SELECT
  FORMAT_DATE('%Y-%m', DATE_TRUNC(s.order_date, MONTH)) AS month,
  COUNT(DISTINCT s.order_id) AS orders,
  SUM(s.qty) AS units,
  SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue,
  SUM(s.qty * s.unit_price_inr) AS gross,
  SUM(s.qty * p.price_inr) AS list_value,
  SUM(IF(s.returned, s.qty, 0)) AS returned_units,
  CAST(ANY_VALUE(anchor.d) AS STRING) AS data_until
FROM `{dataset}.sales` s
JOIN `{dataset}.products` p ON p.sku = s.sku
CROSS JOIN anchor
GROUP BY month
ORDER BY month DESC
