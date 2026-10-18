-- Every active product's stock position, with cover, sell-through and a status to act on.
-- Sales speed = last 8 weeks. Status, in this order: dead stock (stock on hand, no sale in 90 days),
-- reorder (on hand + on order below the reorder point), overstock (more than 120 days of cover), healthy.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
sold AS (
  SELECT
    s.sku,
    SUM(IF(s.order_date > DATE_SUB(anchor.d, INTERVAL 56 DAY), s.qty, 0)) AS units_8w,
    SUM(IF(s.order_date > DATE_SUB(anchor.d, INTERVAL 90 DAY), s.qty, 0)) AS units_90d,
    MAX(s.order_date) AS last_sale
  FROM `{dataset}.sales` s, anchor
  GROUP BY s.sku
),
base AS (
  SELECT
    p.sku, p.name, p.department, p.category, p.cost_inr, p.price_inr,
    sup.name AS supplier, sup.lead_time_days,
    i.on_hand, i.on_order, i.reorder_point, i.last_received_date,
    IFNULL(sold.units_8w, 0) / 8 AS weekly_sales,
    IFNULL(sold.units_90d, 0) AS units_90d,
    sold.last_sale
  FROM `{dataset}.products` p
  JOIN `{dataset}.inventory` i ON i.sku = p.sku
  LEFT JOIN sold ON sold.sku = p.sku
  LEFT JOIN `{dataset}.suppliers` sup ON sup.supplier_id = p.supplier_id
  WHERE p.status = 'active'
),
rated AS (
  SELECT
    *,
    IF(weekly_sales > 0, on_hand / (weekly_sales / 7), NULL) AS cover_days,
    SAFE_DIVIDE(units_90d, units_90d + on_hand) AS sell_through_90d,
    on_hand * cost_inr AS stock_value,
    on_order * cost_inr AS on_order_value,
    CASE
      WHEN on_hand > 0 AND units_90d = 0 THEN 'dead'
      WHEN on_hand + on_order < reorder_point THEN 'reorder'
      WHEN on_hand > 0 AND (weekly_sales = 0 OR on_hand / (weekly_sales / 7) > 120) THEN 'overstock'
      ELSE 'healthy'
    END AS status
  FROM base
)
SELECT *
FROM rated
ORDER BY CASE status WHEN 'dead' THEN 0 WHEN 'reorder' THEN 1 WHEN 'overstock' THEN 2 ELSE 3 END, stock_value DESC
