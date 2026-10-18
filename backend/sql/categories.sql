-- Every department + category in the shop's catalogue, with how many active products and their list prices.
SELECT
  department,
  category,
  COUNT(*) AS products,
  ROUND(AVG(price_inr)) AS avg_price_inr,
  MIN(price_inr) AS min_price_inr,
  MAX(price_inr) AS max_price_inr
FROM `{dataset}.products`
WHERE status = 'active'
GROUP BY department, category
ORDER BY department, category
