-- Comparable products: same department and category, price within +/- @band of the proposed price.
-- Units sold and returned in the last 360 days (counted back from the newest order in the data).
WITH anchor AS (
  SELECT MAX(created_at) AS t FROM `bigquery-public-data.thelook_ecommerce.order_items`
),
seg AS (
  SELECT id, name, brand, retail_price
  FROM `bigquery-public-data.thelook_ecommerce.products`
  WHERE category = @category
    AND department = @department
    AND retail_price BETWEEN @price_usd * (1 - @band) AND @price_usd * (1 + @band)
),
sales AS (
  SELECT
    oi.product_id,
    COUNTIF(oi.status != 'Cancelled') AS units,
    COUNTIF(oi.status = 'Returned') AS returned
  FROM `bigquery-public-data.thelook_ecommerce.order_items` oi, anchor
  WHERE oi.created_at > TIMESTAMP_SUB(anchor.t, INTERVAL 360 DAY)
  GROUP BY oi.product_id
)
SELECT
  seg.id,
  seg.name,
  seg.brand,
  seg.retail_price,
  IFNULL(sales.units, 0) AS units_12m,
  IFNULL(sales.returned, 0) AS returned_12m
FROM seg
LEFT JOIN sales ON sales.product_id = seg.id
ORDER BY units_12m DESC
