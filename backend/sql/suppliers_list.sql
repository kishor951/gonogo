-- Every supplier: lead time, minimum order, the products they make, and those products' sales and stock.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
s12 AS (
  SELECT s.sku, SUM(s.qty) AS units, SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue
  FROM `{dataset}.sales` s, anchor
  WHERE s.order_date > DATE_SUB(anchor.d, INTERVAL 365 DAY)
  GROUP BY s.sku
)
SELECT
  sup.supplier_id, sup.name, sup.city, sup.lead_time_days, sup.moq,
  COUNTIF(p.status = 'active') AS active_products,
  STRING_AGG(DISTINCT p.category, ', ') AS categories,
  IFNULL(SUM(s12.units), 0) AS units_12m,
  IFNULL(SUM(s12.revenue), 0) AS revenue_12m,
  IFNULL(SUM(IF(p.status = 'active', i.on_hand * p.cost_inr, 0)), 0) AS stock_value,
  IFNULL(SUM(IF(p.status = 'active', i.on_order * p.cost_inr, 0)), 0) AS on_order_value
FROM `{dataset}.suppliers` sup
LEFT JOIN `{dataset}.products` p ON p.supplier_id = sup.supplier_id
LEFT JOIN `{dataset}.inventory` i ON i.sku = p.sku
LEFT JOIN s12 ON s12.sku = p.sku
GROUP BY sup.supplier_id, sup.name, sup.city, sup.lead_time_days, sup.moq
ORDER BY revenue_12m DESC
