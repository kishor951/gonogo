-- Customer segments: age bands of the people who bought comparable products (last 360 days).
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
),
seg AS (
  SELECT id
  FROM `bigquery-public-data.thelook_ecommerce.products`
  WHERE category = @category
    AND department = @department
    AND retail_price BETWEEN @price_usd * (1 - @band) AND @price_usd * (1 + @band)
)
SELECT
  CASE
    WHEN u.age < 25 THEN 'Under 25'
    WHEN u.age < 35 THEN '25-34'
    WHEN u.age < 45 THEN '35-44'
    WHEN u.age < 55 THEN '45-54'
    ELSE '55+'
  END AS age_band,
  COUNT(*) AS units
FROM `bigquery-public-data.thelook_ecommerce.order_items` oi
JOIN seg ON seg.id = oi.product_id
JOIN `bigquery-public-data.thelook_ecommerce.users` u ON u.id = oi.user_id, anchor
WHERE oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
  AND oi.status != 'Cancelled'
GROUP BY age_band
ORDER BY units DESC
