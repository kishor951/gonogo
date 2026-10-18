-- Sales by channel (website / myntra / amazon): last 12 months, with revenue from the 12 months before.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT
    s.channel, s.order_id, s.qty, s.returned,
    s.qty * s.unit_price_inr AS sales_inr,
    s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY) AS cur
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 730 DAY)
)
SELECT
  channel,
  SUM(IF(cur AND NOT returned, sales_inr, 0)) AS revenue,
  COUNT(DISTINCT IF(cur, order_id, NULL)) AS orders,
  SUM(IF(cur, qty, 0)) AS units,
  SUM(IF(NOT cur AND NOT returned, sales_inr, 0)) AS revenue_prev
FROM lines
GROUP BY channel
ORDER BY revenue DESC
