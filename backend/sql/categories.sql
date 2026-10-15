-- Every department + category in the sample store, with how many products and the average price (USD).
SELECT
  department,
  category,
  COUNT(*) AS products,
  ROUND(AVG(retail_price), 2) AS avg_price_usd
FROM `bigquery-public-data.thelook_ecommerce.products`
GROUP BY department, category
ORDER BY department, category
