-- Who buys comparable products (last 12 months): units by buyer age band, sales channel and city.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
seg AS (
  SELECT sku
  FROM `{dataset}.products`
  WHERE category = @category
    AND department = @department
    AND price_inr BETWEEN @price * (1 - @band) AND @price * (1 + @band)
),
lines AS (
  SELECT s.qty, s.channel, c.age_band, c.city
  FROM `{dataset}.sales` s
  JOIN seg ON seg.sku = s.sku
  JOIN `{dataset}.customers` c ON c.customer_id = s.customer_id
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
)
SELECT 'age_band' AS dimension, age_band AS label, SUM(qty) AS units FROM lines GROUP BY age_band
UNION ALL
SELECT 'channel' AS dimension, channel AS label, SUM(qty) AS units FROM lines GROUP BY channel
UNION ALL
SELECT 'city' AS dimension, city AS label, SUM(qty) AS units FROM lines GROUP BY city
ORDER BY dimension, units DESC
