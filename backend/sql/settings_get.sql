-- The shop's saved name, rules and profile (one row per organisation).
SELECT shop_name, rules_json, profile_json, FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', updated_at) AS updated_at
FROM `{dataset}.settings`
WHERE org_id = 'default'
LIMIT 1
