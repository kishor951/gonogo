-- Products sent back most often (last 12 months, at least 30 units sold).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
)
SELECT
  p.sku, p.name, p.department, p.category,
  SUM(s.qty) AS units,
  SUM(IF(s.returned, s.qty, 0)) AS returned_units,
  SAFE_DIVIDE(SUM(IF(s.returned, s.qty, 0)), SUM(s.qty)) AS return_rate,
  SUM(IF(s.returned, s.qty * s.unit_price_inr, 0)) AS returned_value
FROM `{dataset}.sales` s
JOIN `{dataset}.products` p ON p.sku = s.sku
CROSS JOIN anchor
WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
GROUP BY p.sku, p.name, p.department, p.category
HAVING SUM(s.qty) >= 30
ORDER BY return_rate DESC
LIMIT 25
