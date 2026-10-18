-- Basket analysis: in orders that contained a comparable product (last 12 months),
-- which other categories were bought in the same order?
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
seg_orders AS (
  SELECT DISTINCT s.order_id
  FROM `{dataset}.sales` s
  JOIN seg ON seg.sku = s.sku
  CROSS JOIN anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
)
SELECT
  p.department,
  p.category,
  COUNT(DISTINCT s.order_id) AS orders,
  (SELECT COUNT(*) FROM seg_orders) AS seg_orders
FROM `{dataset}.sales` s
JOIN seg_orders so ON so.order_id = s.order_id
JOIN `{dataset}.products` p ON p.sku = s.sku
WHERE NOT (p.category = @category AND p.department = @department)
GROUP BY p.department, p.category
ORDER BY orders DESC
LIMIT 5
