-- What the shop earns now, for the experiment budget: the last 90 days of sales (after returns), their cost
-- of goods, orders and returned units, plus revenue in the same 90 days a year earlier (for growth).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT
    s.order_id, s.qty, s.returned,
    s.qty * s.unit_price_inr AS sales_inr,
    s.qty * p.cost_inr AS cost_inr,
    DATE_DIFF(anchor.d, s.order_date, DAY) AS age
  FROM `{dataset}.sales` s
  JOIN `{dataset}.products` p ON p.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 455 DAY)
)
SELECT
  SUM(IF(age < 90 AND NOT returned, sales_inr, 0)) AS revenue_90,
  SUM(IF(age < 90 AND NOT returned, cost_inr, 0)) AS cogs_90,
  COUNT(DISTINCT IF(age < 90, order_id, NULL)) AS orders_90,
  SUM(IF(age < 90 AND returned, qty, 0)) AS returned_units_90,
  SUM(IF(age BETWEEN 365 AND 454 AND NOT returned, sales_inr, 0)) AS revenue_ly_90,
  (SELECT CAST(d AS STRING) FROM anchor) AS data_until
FROM lines
