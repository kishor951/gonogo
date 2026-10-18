-- Category performance: last 12 months, with revenue from the 12 months before for growth.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT
    p.department, p.category, s.qty, s.returned,
    s.qty * s.unit_price_inr AS sales_inr,
    s.qty * p.cost_inr AS cost_inr,
    s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY) AS cur
  FROM `{dataset}.sales` s
  JOIN `{dataset}.products` p ON p.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 730 DAY)
)
SELECT
  department,
  category,
  SUM(IF(cur AND NOT returned, sales_inr, 0)) AS revenue,
  SUM(IF(cur AND NOT returned, cost_inr, 0)) AS cost,
  SUM(IF(cur, qty, 0)) AS units,
  SUM(IF(cur AND returned, qty, 0)) AS returned_units,
  SUM(IF(NOT cur AND NOT returned, sales_inr, 0)) AS revenue_prev
FROM lines
GROUP BY department, category
ORDER BY revenue DESC
