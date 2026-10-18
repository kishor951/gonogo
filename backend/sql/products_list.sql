-- The catalogue: every product with its list margin and the last 12 months of sales and returns.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
s12 AS (
  SELECT
    s.sku,
    SUM(s.qty) AS units,
    SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue,
    SUM(IF(s.returned, s.qty, 0)) AS returned_units
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
  GROUP BY s.sku
),
last_sale AS (
  SELECT sku, MAX(order_date) AS last_sale FROM `{dataset}.sales` GROUP BY sku
)
SELECT
  p.sku, p.name, p.department, p.category, p.brand, p.price_inr, p.cost_inr,
  SAFE_DIVIDE(p.price_inr - p.cost_inr, p.price_inr) AS list_margin,
  p.status, p.launch_date, sup.name AS supplier,
  IFNULL(s12.units, 0) AS units_12m,
  IFNULL(s12.revenue, 0) AS revenue_12m,
  SAFE_DIVIDE(s12.returned_units, s12.units) AS return_rate,
  last_sale.last_sale
FROM `{dataset}.products` p
LEFT JOIN s12 ON s12.sku = p.sku
LEFT JOIN last_sale ON last_sale.sku = p.sku
LEFT JOIN `{dataset}.suppliers` sup ON sup.supplier_id = p.supplier_id
ORDER BY revenue_12m DESC
