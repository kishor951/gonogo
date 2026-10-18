-- Sales in the last 30 days ('cur') and the 30 days before ('prev').
-- gross = what customers paid before returns; list_value = the same units at list price (for the discount).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT
    s.order_id, s.customer_id, s.qty, s.returned, s.unit_price_inr, p.price_inr,
    CASE
      WHEN s.order_date > DATE_SUB(anchor.d, INTERVAL 30 DAY) THEN 'cur'
      WHEN s.order_date > DATE_SUB(anchor.d, INTERVAL 60 DAY) THEN 'prev'
    END AS period
  FROM `{dataset}.sales` s
  JOIN `{dataset}.products` p ON p.sku = s.sku
  CROSS JOIN anchor
)
SELECT
  period,
  SUM(IF(returned, 0, qty * unit_price_inr)) AS revenue,
  SUM(qty * unit_price_inr) AS gross,
  SUM(qty * price_inr) AS list_value,
  COUNT(DISTINCT order_id) AS orders,
  SUM(qty) AS units,
  COUNT(DISTINCT customer_id) AS customers,
  (SELECT CAST(d AS STRING) FROM anchor) AS data_until
FROM lines
WHERE period IS NOT NULL
GROUP BY period
