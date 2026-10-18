-- List prices of the shop's active products in one department + category, with units sold in the last 12 months.
-- Used to suggest a selling price for a new product (the percentiles are worked out in Python).
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
sold AS (
  SELECT s.sku, SUM(s.qty) AS units
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
  GROUP BY s.sku
)
SELECT p.sku, p.name, p.price_inr, IFNULL(sold.units, 0) AS units_12m
FROM `{dataset}.products` p
LEFT JOIN sold ON sold.sku = p.sku
WHERE p.status = 'active'
  AND p.department = @department
  AND p.category = @category
ORDER BY p.price_inr
