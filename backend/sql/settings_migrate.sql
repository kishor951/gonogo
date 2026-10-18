-- Adds the shop profile column to settings tables created before the Shop profile page existed.
ALTER TABLE `{dataset}.settings` ADD COLUMN IF NOT EXISTS profile_json STRING
