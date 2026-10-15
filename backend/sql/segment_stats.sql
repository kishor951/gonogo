-- Units sold per 30-day bucket (0 = most recent) for the whole category and for the comparable
-- price segment, plus product counts for the store, the category and the segment.
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
),
cat AS (
  SELECT
    id,
    retail_price BETWEEN @price_usd * (1 - @band) AND @price_usd * (1 + @band) AS in_seg
  FROM `bigquery-public-data.thelook_ecommerce.products`
  WHERE category = @category AND department = @department
),
recent AS (
  SELECT oi.product_id, DIV(TIMESTAMP_DIFF(anchor.t, oi.created_at, DAY), 30) AS bucket
  FROM `bigquery-public-data.thelook_ecommerce.order_items` oi, anchor
  WHERE oi.status != 'Cancelled'
    AND oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
),
by_bucket AS (
  SELECT r.bucket, COUNT(*) AS cat_units, COUNTIF(c.in_seg) AS seg_units
  FROM recent r
  JOIN cat c ON c.id = r.product_id
  GROUP BY r.bucket
),
store_by_bucket AS (
  SELECT bucket, COUNT(*) AS units FROM recent GROUP BY bucket
)
SELECT
  b AS bucket,
  IFNULL(by_bucket.cat_units, 0) AS cat_units,
  IFNULL(by_bucket.seg_units, 0) AS seg_units,
  IFNULL(store_by_bucket.units, 0) AS store_bucket_units,
  (SELECT COUNT(*) FROM recent) AS store_units,
  (SELECT COUNT(*) FROM `bigquery-public-data.thelook_ecommerce.products`) AS store_skus,
  (SELECT COUNT(*) FROM cat) AS cat_skus,
  (SELECT COUNTIF(in_seg) FROM cat) AS seg_skus
FROM UNNEST(GENERATE_ARRAY(0, 11)) AS b
LEFT JOIN by_bucket ON by_bucket.bucket = b
LEFT JOIN store_by_bucket ON store_by_bucket.bucket = b
ORDER BY bucket
