-- Revenue (after returns) and units for the last 18 complete calendar months.
WITH anchor AS (
  SELECT DATE_TRUNC(DATE_ADD(MAX(order_date), INTERVAL 1 DAY), MONTH) AS month_end FROM `{dataset}.sales`
)
SELECT
  FORMAT_DATE('%Y-%m', DATE_TRUNC(s.order_date, MONTH)) AS month,
  SUM(IF(s.returned, 0, s.qty * s.unit_price_inr)) AS revenue,
  SUM(s.qty) AS units
FROM `{dataset}.sales` s, anchor
WHERE s.order_date >= DATE_SUB(anchor.month_end, INTERVAL 18 MONTH)
  AND s.order_date < anchor.month_end
GROUP BY month
ORDER BY month
