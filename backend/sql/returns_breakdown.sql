-- Returns in the last 12 months by category and by channel.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
lines AS (
  SELECT p.department, p.category, s.channel, s.qty, s.returned, s.unit_price_inr
  FROM `{dataset}.sales` s
  JOIN `{dataset}.products` p ON p.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
)
SELECT
  'category' AS dimension, department, category AS label,
  SUM(qty) AS units, SUM(IF(returned, qty, 0)) AS returned_units,
  SUM(IF(returned, qty * unit_price_inr, 0)) AS returned_value
FROM lines
GROUP BY department, category
UNION ALL
SELECT
  'channel' AS dimension, CAST(NULL AS STRING) AS department, channel AS label,
  SUM(qty) AS units, SUM(IF(returned, qty, 0)) AS returned_units,
  SUM(IF(returned, qty * unit_price_inr, 0)) AS returned_value
FROM lines
GROUP BY channel
