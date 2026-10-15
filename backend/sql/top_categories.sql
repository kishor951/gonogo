-- Best-selling categories over the last 360 days.
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
)
SELECT
  p.department,
  p.category,
  COUNT(*) AS units_12m,
  ROUND(AVG(oi.sale_price), 2) AS avg_sale_usd
FROM `bigquery-public-data.thelook_ecommerce.order_items` oi
JOIN `bigquery-public-data.thelook_ecommerce.products` p ON p.id = oi.product_id, anchor
WHERE oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
  AND oi.status != 'Cancelled'
GROUP BY p.department, p.category
ORDER BY units_12m DESC
LIMIT 10
