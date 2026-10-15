-- The organisation's business at a glance: catalogue size and the last 360 days of sales.
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
),
recent AS (
  SELECT oi.order_id, oi.user_id, oi.status, oi.sale_price
  FROM `bigquery-public-data.thelook_ecommerce.order_items` oi, anchor
  WHERE oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
)
SELECT
  (SELECT COUNT(*) FROM `bigquery-public-data.thelook_ecommerce.products`) AS products,
  (SELECT COUNT(DISTINCT CONCAT(department, '|', category)) FROM `bigquery-public-data.thelook_ecommerce.products`) AS categories,
  COUNTIF(status != 'Cancelled') AS units_12m,
  COUNT(DISTINCT IF(status != 'Cancelled', order_id, NULL)) AS orders_12m,
  COUNT(DISTINCT IF(status != 'Cancelled', user_id, NULL)) AS customers_12m,
  SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNTIF(status != 'Cancelled')) AS return_rate,
  AVG(IF(status != 'Cancelled', sale_price, NULL)) AS avg_sale_usd,
  CAST((SELECT DATE(t) FROM anchor) AS STRING) AS data_until
FROM recent
