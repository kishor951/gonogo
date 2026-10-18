-- Sales speed, returns and trend for the comparable segment, its whole category and the whole shop.
-- Speed = units per product per month over the last 12 months, counting only active products on sale
-- for at least 30 days, and only the days each was on sale (a product launched 3 months ago counts 3 months).
-- Trend windows: the last 91 days, the 91 days before, and the same 91 days a year earlier.
WITH anchor AS (
  SELECT MAX(order_date) AS d FROM `{dataset}.sales`
),
p AS (
  SELECT
    sku,
    category = @category AND department = @department AS in_cat,
    category = @category AND department = @department
      AND price_inr BETWEEN @price * (1 - @band) AND @price * (1 + @band) AS in_seg,
    DATE_DIFF(anchor.d, GREATEST(launch_date, DATE_SUB(anchor.d, INTERVAL 364 DAY)), DAY) + 1 AS live_days,
    status = 'active' AND DATE_DIFF(anchor.d, launch_date, DAY) >= 30 AS rated
  FROM `{dataset}.products`, anchor
),
s AS (
  SELECT sales.sku, sales.qty, sales.returned, DATE_DIFF(anchor.d, sales.order_date, DAY) AS age
  FROM `{dataset}.sales` sales, anchor
  WHERE sales.order_date > DATE_SUB(anchor.d, INTERVAL 456 DAY)
),
per_sku AS (
  SELECT
    p.sku, p.in_cat, p.in_seg, p.live_days, p.rated,
    IFNULL(SUM(IF(s.age < 365, s.qty, 0)), 0) AS units_12m,
    IFNULL(SUM(IF(s.age < 365 AND s.returned, s.qty, 0)), 0) AS returned_12m,
    IFNULL(SUM(IF(s.age < 91, s.qty, 0)), 0) AS last_3m,
    IFNULL(SUM(IF(s.age BETWEEN 91 AND 181, s.qty, 0)), 0) AS prev_3m,
    IFNULL(SUM(IF(s.age BETWEEN 365 AND 455, s.qty, 0)), 0) AS ly_3m
  FROM p
  LEFT JOIN s ON s.sku = p.sku
  GROUP BY p.sku, p.in_cat, p.in_seg, p.live_days, p.rated
)
SELECT
  SUM(IF(rated, units_12m, 0)) AS shop_units,
  SUM(IF(rated, live_days, 0)) / 30.4 AS shop_sku_months,
  COUNTIF(rated) AS shop_skus,
  SUM(IF(rated AND in_cat, units_12m, 0)) AS cat_units,
  SUM(IF(rated AND in_cat, live_days, 0)) / 30.4 AS cat_sku_months,
  COUNTIF(rated AND in_cat) AS cat_skus,
  SUM(IF(rated AND in_seg, units_12m, 0)) AS seg_units,
  SUM(IF(rated AND in_seg, live_days, 0)) / 30.4 AS seg_sku_months,
  COUNTIF(rated AND in_seg) AS seg_skus,
  -- returns and trend use every product in the segment, discontinued ones too
  SUM(IF(in_seg, units_12m, 0)) AS seg_units_all,
  SUM(IF(in_seg, returned_12m, 0)) AS seg_returned,
  SUM(IF(in_seg, last_3m, 0)) AS seg_last_3m,
  SUM(IF(in_seg, prev_3m, 0)) AS seg_prev_3m,
  SUM(IF(in_seg, ly_3m, 0)) AS seg_ly_3m,
  SUM(last_3m) AS shop_last_3m,
  SUM(prev_3m) AS shop_prev_3m,
  SUM(ly_3m) AS shop_ly_3m
FROM per_sku
