-- Comparable products: same department and category, list price within +/- @band of the proposed price.
-- Units sold and returned in the last 12 months (counted back from the newest order in the data).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
seg AS (
  SELECT sku, name, brand, price_inr, status
  FROM `{dataset}.products`
  WHERE category = @category
    AND department = @department
    AND price_inr BETWEEN @price * (1 - @band) AND @price * (1 + @band)
),
recent AS (
  SELECT s.sku, s.qty, s.returned
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
)
SELECT
  seg.sku,
  seg.name,
  seg.brand,
  seg.price_inr,
  seg.status,
  IFNULL(SUM(recent.qty), 0) AS units_12m,
  IFNULL(SUM(IF(recent.returned, recent.qty, 0)), 0) AS returned_12m
FROM seg
LEFT JOIN recent ON recent.sku = seg.sku
GROUP BY seg.sku, seg.name, seg.brand, seg.price_inr, seg.status
ORDER BY units_12m DESC
