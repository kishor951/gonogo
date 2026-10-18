-- Units sold by comparable products per 30-day bucket (0 = most recent), last 12 buckets.
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
recent AS (
  SELECT s.qty, DIV(DATE_DIFF(anchor.d, s.order_date, DAY), 30) AS bucket
  FROM `{dataset}.sales` s
  JOIN seg ON seg.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 360 DAY)
)
SELECT b AS bucket, IFNULL(SUM(recent.qty), 0) AS seg_units
FROM UNNEST(GENERATE_ARRAY(0, 11)) AS b
LEFT JOIN recent ON recent.bucket = b
GROUP BY b
ORDER BY b
