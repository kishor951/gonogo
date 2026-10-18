-- Customer numbers: everyone, and who ordered in the last 12 months.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
per AS (
  SELECT
    s.customer_id,
    COUNT(DISTINCT s.order_id) AS orders,
    SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
  GROUP BY s.customer_id
)
SELECT
  (SELECT COUNT(*) FROM `{dataset}.customers`) AS customers,
  (SELECT COUNTIF(c.first_order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY))
     FROM `{dataset}.customers` c, anchor) AS new_12m,
  COUNT(*) AS active_12m,
  COUNTIF(orders >= 2) AS repeat_12m,
  SUM(orders) AS orders_12m,
  SUM(revenue) AS revenue_12m
FROM per
