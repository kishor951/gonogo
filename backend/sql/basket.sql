-- Basket analysis: in orders that contained a comparable product (last 360 days),
-- which other categories were bought in the same order?
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
),
seg AS (
  SELECT id
  FROM `bigquery-public-data.thelook_ecommerce.products`
  WHERE category = @category
    AND department = @department
    AND retail_price BETWEEN @price_usd * (1 - @band) AND @price_usd * (1 + @band)
),
seg_orders AS (
  SELECT DISTINCT oi.order_id
  FROM `bigquery-public-data.thelook_ecommerce.order_items` oi
  JOIN seg ON seg.id = oi.product_id, anchor
  WHERE oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
    AND oi.status != 'Cancelled'
)
SELECT
  p.category,
  COUNT(DISTINCT oi.order_id) AS orders,
  (SELECT COUNT(*) FROM seg_orders) AS seg_orders
FROM `bigquery-public-data.thelook_ecommerce.order_items` oi
JOIN seg_orders so ON so.order_id = oi.order_id
JOIN `bigquery-public-data.thelook_ecommerce.products` p ON p.id = oi.product_id
WHERE oi.product_id NOT IN (SELECT id FROM seg)
GROUP BY p.category
ORDER BY orders DESC
LIMIT 5
