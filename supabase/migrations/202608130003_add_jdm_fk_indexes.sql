-- Cover foreign keys used by the JDM reference and history tables.
create index if not exists idx_jacc_chassis_source on public.jacc_chassis_codes (source_id);
create index if not exists idx_jacc_factory_grade_chassis on public.jacc_factory_grades (chassis_code_id);
create index if not exists idx_jacc_factory_grade_source on public.jacc_factory_grades (source_id);
create index if not exists idx_jacc_auction_model on public.jacc_auction_history (model_id);
create index if not exists idx_jacc_auction_source on public.jacc_auction_history (source_id);
create index if not exists idx_jacc_import_source on public.jacc_data_import_batches (source_id);
