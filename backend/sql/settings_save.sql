-- Save the shop's name, rules and profile (insert the row the first time, update it after that).
MERGE `{dataset}.settings` t
USING (SELECT 'default' AS org_id, @shop_name AS shop_name, @rules_json AS rules_json, @profile_json AS profile_json) s
ON t.org_id = s.org_id
WHEN MATCHED THEN
  UPDATE SET shop_name = s.shop_name, rules_json = s.rules_json, profile_json = s.profile_json,
             updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (org_id, shop_name, rules_json, profile_json, updated_at)
  VALUES (s.org_id, s.shop_name, s.rules_json, s.profile_json, CURRENT_TIMESTAMP())
