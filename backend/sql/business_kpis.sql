-- The shop's key numbers for the last 12 months ('cur') and the 12 months before ('prev').
-- Revenue and cost exclude returned lines; units and the return rate count every line sold.
WITH anchor AS (
  SELECT MAX(order_date) AS d, MIN(order_date) AS first_day FROM `{dataset}.sales`
),
lines AS (
  SELECT
    s.order_id, s.customer_id, s.qty, s.returned,
    s.qty * s.unit_price_inr AS sales_inr,
    s.qty * p.cost_inr AS cost_inr,
    IF(s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY), 'cur', 'prev') AS period
  FROM `{dataset}.sales` s
  JOIN `{dataset}.products` p ON p.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 730 DAY)
)
SELECT
  period,
  SUM(IF(returned, 0, sales_inr)) AS revenue,
  SUM(IF(returned, 0, cost_inr)) AS cost,
  SUM(qty) AS units,
  SUM(IF(returned, qty, 0)) AS returned_units,
  COUNT(DISTINCT order_id) AS orders,
  COUNT(DISTINCT customer_id) AS customers,
  (SELECT CAST(d AS STRING) FROM anchor) AS data_until,
  (SELECT CAST(first_day AS STRING) FROM anchor) AS data_from,
  (SELECT COUNTIF(status = 'active') FROM `{dataset}.products`) AS active_skus
FROM lines
GROUP BY period
