# DB Schema Snapshot

- db_path: `C:\Users\画桦\Desktop\DeepAudit_pro\database.db`
- tables: `29`
- indexes: `49`
- triggers: `0`

## table `ai_prompt_ledger`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `trace_id` | `TEXT` | 1 | `None` | 0 |
| 2 | `invoice_id` | `INTEGER` | 0 | `None` | 0 |
| 3 | `risk_level` | `TEXT` | 0 | `None` | 0 |
| 4 | `risk_score` | `INTEGER` | 0 | `None` | 0 |
| 5 | `prompt_version` | `TEXT` | 0 | `None` | 0 |
| 6 | `provider` | `TEXT` | 0 | `None` | 0 |
| 7 | `input_json` | `TEXT` | 0 | `None` | 0 |
| 8 | `output_json` | `TEXT` | 0 | `None` | 0 |
| 9 | `hash_prev` | `TEXT` | 0 | `None` | 0 |
| 10 | `hash_curr` | `TEXT` | 0 | `None` | 0 |
| 11 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_ai_prompt_ledger_created_at` unique=0 cols=['created_at']
- `idx_ai_prompt_ledger_invoice_id` unique=0 cols=['invoice_id']
- `idx_ai_prompt_ledger_trace_id` unique=1 cols=['trace_id']

row_count: `3`

## table `audit_evidence`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `trace_id` | `TEXT` | 1 | `None` | 0 |
| 2 | `object_type` | `TEXT` | 1 | `'invoice'` | 0 |
| 3 | `object_id` | `TEXT` | 1 | `''` | 0 |
| 4 | `file_path` | `TEXT` | 1 | `None` | 0 |
| 5 | `evidence_type` | `TEXT` | 1 | `'file'` | 0 |
| 6 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_audit_evidence_trace_id` unique=0 cols=['trace_id']

row_count: `2`

## table `audit_log`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 2 | `actor_user_id` | `TEXT` | 0 | `''` | 0 |
| 3 | `actor_name` | `TEXT` | 0 | `''` | 0 |
| 4 | `action` | `TEXT` | 1 | `''` | 0 |
| 5 | `target_type` | `TEXT` | 1 | `''` | 0 |
| 6 | `target_id` | `TEXT` | 1 | `''` | 0 |
| 7 | `client_ip` | `TEXT` | 1 | `''` | 0 |
| 8 | `change_reason_code` | `TEXT` | 1 | `'SYSTEM_AUTO'` | 0 |
| 9 | `snapshot_before` | `TEXT` | 1 | `'{}'` | 0 |
| 10 | `snapshot_after` | `TEXT` | 1 | `'{}'` | 0 |
| 11 | `trace_id` | `TEXT` | 0 | `''` | 0 |

indexes:
- `idx_audit_log_target` unique=0 cols=['target_type', 'target_id']
- `idx_audit_log_action` unique=0 cols=['action']
- `idx_audit_log_created_at` unique=0 cols=['created_at']

row_count: `6`

## table `audit_logs`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `action_type` | `TEXT` | 1 | `None` | 0 |
| 2 | `operator` | `TEXT` | 1 | `None` | 0 |
| 3 | `actor_user_id` | `INTEGER` | 0 | `None` | 0 |
| 4 | `target_type` | `TEXT` | 0 | `None` | 0 |
| 5 | `target_id` | `INTEGER` | 0 | `None` | 0 |
| 6 | `detail` | `TEXT` | 0 | `None` | 0 |
| 7 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_audit_logs_action_type` unique=0 cols=['action_type']
- `idx_audit_logs_created_at` unique=0 cols=['created_at']

row_count: `6`

## table `audit_trace_events`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `trace_id` | `TEXT` | 1 | `None` | 0 |
| 2 | `event_type` | `TEXT` | 1 | `None` | 0 |
| 3 | `event_time` | `TEXT` | 1 | `None` | 0 |
| 4 | `payload_json` | `TEXT` | 0 | `'{}'` | 0 |
| 5 | `actor_user_id` | `TEXT` | 0 | `''` | 0 |
| 6 | `actor_name` | `TEXT` | 0 | `''` | 0 |
| 7 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_audit_trace_events_event_time` unique=0 cols=['event_time']
- `idx_audit_trace_events_trace_id` unique=0 cols=['trace_id']

row_count: `93`

## table `audit_traces`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `object_type` | `TEXT` | 1 | `None` | 0 |
| 2 | `object_id` | `TEXT` | 1 | `None` | 0 |
| 3 | `trace_id` | `TEXT` | 1 | `None` | 0 |
| 4 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_audit_traces_object` unique=0 cols=['object_type', 'object_id']
- `idx_audit_traces_trace_id` unique=1 cols=['trace_id']
- `sqlite_autoindex_audit_traces_1` unique=1 cols=['trace_id']

row_count: `55`

## table `bank_transactions`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `txn_id` | `TEXT` | 1 | `None` | 0 |
| 2 | `ts` | `TEXT` | 0 | `None` | 0 |
| 3 | `amount` | `REAL` | 0 | `None` | 0 |
| 4 | `counterparty` | `TEXT` | 0 | `None` | 0 |
| 5 | `memo` | `TEXT` | 0 | `None` | 0 |
| 6 | `imported_at` | `TEXT` | 1 | `None` | 0 |
| 7 | `matched_invoice_id` | `INTEGER` | 0 | `None` | 0 |
| 8 | `match_score` | `REAL` | 0 | `None` | 0 |
| 9 | `match_reason` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_bank_transactions_txn_id` unique=1 cols=['txn_id']
- `sqlite_autoindex_bank_transactions_1` unique=1 cols=['txn_id']

row_count: `0`

## table `case_actions`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `case_id` | `INTEGER` | 1 | `None` | 0 |
| 2 | `action_type` | `TEXT` | 0 | `None` | 0 |
| 3 | `operator` | `TEXT` | 0 | `None` | 0 |
| 4 | `action_note` | `TEXT` | 0 | `None` | 0 |
| 5 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_case_actions_case_id` unique=0 cols=['case_id']

row_count: `0`

## table `db_departments`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `enterprise_id` | `INTEGER` | 0 | `None` | 0 |
| 2 | `dept_code` | `TEXT` | 1 | `None` | 0 |
| 3 | `dept_name` | `TEXT` | 1 | `None` | 0 |
| 4 | `parent_id` | `INTEGER` | 0 | `None` | 0 |
| 5 | `level` | `INTEGER` | 0 | `1` | 0 |
| 6 | `path` | `TEXT` | 0 | `None` | 0 |
| 7 | `manager_id` | `INTEGER` | 0 | `None` | 0 |

indexes:
- `idx_db_departments_parent` unique=0 cols=['parent_id']
- `idx_db_departments_enterprise` unique=0 cols=['enterprise_id']

row_count: `0`

## table `db_enterprises`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `enterprise_code` | `TEXT` | 1 | `None` | 0 |
| 2 | `enterprise_name` | `TEXT` | 1 | `None` | 0 |
| 3 | `status` | `TEXT` | 0 | `'active'` | 0 |
| 4 | `settings_json` | `TEXT` | 0 | `None` | 0 |
| 5 | `created_at` | `TEXT` | 0 | `CURRENT_TIMESTAMP` | 0 |

indexes:
- `idx_db_enterprises_code` unique=1 cols=['enterprise_code']
- `sqlite_autoindex_db_enterprises_1` unique=1 cols=['enterprise_code']

row_count: `0`

## table `db_integrations`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `enterprise_id` | `INTEGER` | 0 | `None` | 0 |
| 2 | `integration_type` | `TEXT` | 1 | `None` | 0 |
| 3 | `config_json` | `TEXT` | 0 | `None` | 0 |
| 4 | `status` | `TEXT` | 0 | `'active'` | 0 |
| 5 | `last_sync_at` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_db_integrations_type` unique=0 cols=['integration_type']
- `idx_db_integrations_enterprise` unique=0 cols=['enterprise_id']

row_count: `0`

## table `db_metrics`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `metric_type` | `TEXT` | 1 | `None` | 0 |
| 2 | `metric_name` | `TEXT` | 1 | `None` | 0 |
| 3 | `metric_value` | `REAL` | 0 | `None` | 0 |
| 4 | `metric_unit` | `TEXT` | 0 | `None` | 0 |
| 5 | `recorded_at` | `TEXT` | 0 | `CURRENT_TIMESTAMP` | 0 |

indexes:
- `idx_db_metrics_recorded_at` unique=0 cols=['recorded_at']
- `idx_db_metrics_type_name` unique=0 cols=['metric_type', 'metric_name']

row_count: `780`

## table `db_risk_cases`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `case_code` | `TEXT` | 1 | `None` | 0 |
| 2 | `risk_type` | `TEXT` | 0 | `None` | 0 |
| 3 | `severity` | `TEXT` | 0 | `None` | 0 |
| 4 | `description` | `TEXT` | 0 | `None` | 0 |
| 5 | `solution` | `TEXT` | 0 | `None` | 0 |
| 6 | `tags` | `TEXT` | 0 | `None` | 0 |
| 7 | `created_at` | `TEXT` | 0 | `CURRENT_TIMESTAMP` | 0 |

indexes:
- `idx_db_risk_cases_code` unique=1 cols=['case_code']
- `sqlite_autoindex_db_risk_cases_1` unique=1 cols=['case_code']

row_count: `0`

## table `db_sync_logs`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `integration_id` | `INTEGER` | 0 | `None` | 0 |
| 2 | `sync_type` | `TEXT` | 0 | `None` | 0 |
| 3 | `status` | `TEXT` | 0 | `None` | 0 |
| 4 | `records_count` | `INTEGER` | 0 | `None` | 0 |
| 5 | `error_message` | `TEXT` | 0 | `None` | 0 |
| 6 | `sync_at` | `TEXT` | 0 | `CURRENT_TIMESTAMP` | 0 |

indexes:
- `idx_db_sync_logs_sync_at` unique=0 cols=['sync_at']
- `idx_db_sync_logs_integration` unique=0 cols=['integration_id']

row_count: `0`

## table `departments`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `name` | `TEXT` | 1 | `None` | 0 |
| 2 | `parent_id` | `INTEGER` | 0 | `None` | 0 |
| 3 | `status` | `TEXT` | 1 | `'ACTIVE'` | 0 |
| 4 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 5 | `updated_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_departments_parent_id` unique=0 cols=['parent_id']
- `idx_departments_name` unique=1 cols=['name']
- `sqlite_autoindex_departments_1` unique=1 cols=['name']

row_count: `4`

## table `governance_rules`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `rule_key` | `TEXT` | 1 | `None` | 0 |
| 2 | `rule_name` | `TEXT` | 1 | `None` | 0 |
| 3 | `threshold` | `REAL` | 1 | `0` | 0 |
| 4 | `threshold_json` | `TEXT` | 1 | `'{}'` | 0 |
| 5 | `enabled` | `INTEGER` | 1 | `1` | 0 |
| 6 | `severity` | `TEXT` | 1 | `'MEDIUM'` | 0 |
| 7 | `version` | `INTEGER` | 1 | `1` | 0 |
| 8 | `updated_by` | `TEXT` | 0 | `None` | 0 |
| 9 | `updated_at` | `TEXT` | 1 | `None` | 0 |
| 10 | `rule_type` | `TEXT` | 1 | `'system'` | 0 |
| 11 | `status` | `TEXT` | 1 | `'published'` | 0 |
| 12 | `publish_reason` | `TEXT` | 0 | `None` | 0 |
| 13 | `published_at` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_governance_rules_key` unique=1 cols=['rule_key']
- `sqlite_autoindex_governance_rules_1` unique=1 cols=['rule_key']

row_count: `6`

## table `invoices`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `reference_no` | `TEXT` | 0 | `None` | 0 |
| 2 | `filename` | `TEXT` | 1 | `None` | 0 |
| 3 | `amount` | `TEXT` | 0 | `None` | 0 |
| 4 | `invoice_date` | `TEXT` | 0 | `None` | 0 |
| 5 | `applicant` | `TEXT` | 0 | `None` | 0 |
| 6 | `department` | `TEXT` | 0 | `None` | 0 |
| 7 | `is_canton_fair` | `INTEGER` | 1 | `0` | 0 |
| 8 | `hotel_limit` | `INTEGER` | 1 | `500` | 0 |
| 9 | `mode` | `TEXT` | 0 | `None` | 0 |
| 10 | `raw_json` | `TEXT` | 0 | `None` | 0 |
| 11 | `risk_level` | `TEXT` | 0 | `None` | 0 |
| 12 | `risk_reason` | `TEXT` | 0 | `None` | 0 |
| 13 | `currency` | `TEXT` | 0 | `None` | 0 |
| 14 | `fx_flag` | `INTEGER` | 0 | `0` | 0 |
| 15 | `fx_reason` | `TEXT` | 0 | `None` | 0 |
| 16 | `manual_rate` | `TEXT` | 0 | `None` | 0 |
| 17 | `manual_cny_amount` | `TEXT` | 0 | `None` | 0 |
| 18 | `ai_risk_level` | `TEXT` | 0 | `None` | 0 |
| 19 | `ai_analysis_reason` | `TEXT` | 0 | `None` | 0 |
| 20 | `status` | `TEXT` | 1 | `'PENDING'` | 0 |
| 21 | `record_state` | `TEXT` | 1 | `'DRAFT'` | 0 |
| 22 | `source` | `TEXT` | 1 | `'normal'` | 0 |
| 23 | `verify_status` | `TEXT` | 1 | `'PENDING'` | 0 |
| 24 | `verify_message` | `TEXT` | 0 | `''` | 0 |
| 25 | `verify_checked_at` | `TEXT` | 0 | `NULL` | 0 |
| 26 | `verify_count` | `INTEGER` | 1 | `0` | 0 |
| 27 | `verify_provider` | `TEXT` | 0 | `''` | 0 |
| 28 | `verify_request_id` | `TEXT` | 0 | `''` | 0 |
| 29 | `verify_latency_ms` | `INTEGER` | 0 | `0` | 0 |
| 30 | `verify_status_code` | `INTEGER` | 0 | `0` | 0 |
| 31 | `verify_raw_payload` | `TEXT` | 0 | `''` | 0 |
| 32 | `approval_stage` | `TEXT` | 1 | `'L1'` | 0 |
| 33 | `approval_status` | `TEXT` | 1 | `'PENDING'` | 0 |
| 34 | `first_approver_id` | `TEXT` | 0 | `''` | 0 |
| 35 | `second_approver_id` | `TEXT` | 0 | `''` | 0 |
| 36 | `first_approved_at` | `TEXT` | 0 | `NULL` | 0 |
| 37 | `second_approved_at` | `TEXT` | 0 | `NULL` | 0 |
| 38 | `sla_due_at` | `TEXT` | 0 | `NULL` | 0 |
| 39 | `queue_owner_id` | `TEXT` | 0 | `''` | 0 |
| 40 | `rule_hit_id` | `TEXT` | 0 | `''` | 0 |
| 41 | `rule_explain` | `TEXT` | 0 | `''` | 0 |
| 42 | `ai_trace_id` | `TEXT` | 0 | `''` | 0 |
| 43 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 44 | `submitted_by_user_id` | `INTEGER` | 0 | `None` | 0 |
| 45 | `submitter_department` | `TEXT` | 0 | `None` | 0 |
| 46 | `submitter_name` | `TEXT` | 0 | `None` | 0 |
| 47 | `submitter_no` | `TEXT` | 0 | `None` | 0 |
| 48 | `proxy_id` | `INTEGER` | 0 | `None` | 0 |
| 49 | `proxy_name` | `TEXT` | 0 | `None` | 0 |
| 50 | `is_proxy_submit` | `INTEGER` | 0 | `0` | 0 |
| 51 | `invoice_code` | `TEXT` | 0 | `None` | 0 |
| 52 | `invoice_number` | `TEXT` | 0 | `None` | 0 |
| 53 | `seller_name` | `TEXT` | 0 | `None` | 0 |
| 54 | `buyer_name` | `TEXT` | 0 | `None` | 0 |
| 55 | `tax_amount` | `TEXT` | 0 | `None` | 0 |
| 56 | `rule_explain_biz` | `TEXT` | 0 | `None` | 0 |
| 57 | `risk_reason_biz` | `TEXT` | 0 | `None` | 0 |
| 58 | `risk_score` | `INTEGER` | 0 | `NULL` | 0 |

indexes:
- `idx_invoices_record_state` unique=0 cols=['record_state']
- `idx_invoices_approval_status` unique=0 cols=['approval_status']
- `idx_invoices_queue_owner` unique=0 cols=['queue_owner_id']
- `sqlite_autoindex_invoices_1` unique=1 cols=['reference_no']

row_count: `39`

## table `login_security_locks`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `username` | `TEXT` | 1 | `None` | 0 |
| 2 | `ip_address` | `TEXT` | 1 | `None` | 0 |
| 3 | `failed_count` | `INTEGER` | 1 | `0` | 0 |
| 4 | `window_start` | `TEXT` | 0 | `None` | 0 |
| 5 | `lock_until` | `TEXT` | 0 | `None` | 0 |
| 6 | `updated_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_login_security_locks_lock_until` unique=0 cols=['lock_until']
- `idx_login_security_locks_identity` unique=1 cols=['username', 'ip_address']

row_count: `1`

## table `permissions`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `permission_key` | `TEXT` | 1 | `None` | 0 |
| 2 | `description` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_permissions_key` unique=1 cols=['permission_key']
- `sqlite_autoindex_permissions_1` unique=1 cols=['permission_key']

row_count: `17`

## table `positions`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `name` | `TEXT` | 1 | `None` | 0 |
| 2 | `status` | `TEXT` | 1 | `'ACTIVE'` | 0 |
| 3 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 4 | `updated_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_positions_status` unique=0 cols=['status']
- `idx_positions_name` unique=1 cols=['name']
- `sqlite_autoindex_positions_1` unique=1 cols=['name']

row_count: `1`

## table `risk_cases`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `event_id` | `INTEGER` | 1 | `None` | 0 |
| 2 | `assigned_to` | `TEXT` | 0 | `None` | 0 |
| 3 | `status` | `TEXT` | 1 | `'OPEN'` | 0 |
| 4 | `resolution_note` | `TEXT` | 0 | `None` | 0 |
| 5 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 6 | `closed_at` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_risk_cases_status` unique=0 cols=['status']
- `idx_risk_cases_event_id` unique=1 cols=['event_id']

row_count: `0`

## table `risk_events`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `invoice_id` | `INTEGER` | 0 | `None` | 0 |
| 2 | `risk_level` | `TEXT` | 0 | `None` | 0 |
| 3 | `risk_score` | `INTEGER` | 0 | `None` | 0 |
| 4 | `rule_summary` | `TEXT` | 0 | `None` | 0 |
| 5 | `trace_id` | `TEXT` | 0 | `None` | 0 |
| 6 | `created_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_risk_events_created_at` unique=0 cols=['created_at']
- `idx_risk_events_invoice_id` unique=0 cols=['invoice_id']

row_count: `0`

## table `role_data_scopes`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `role_id` | `INTEGER` | 1 | `None` | 0 |
| 2 | `scope_type` | `TEXT` | 1 | `'DEPT'` | 0 |
| 3 | `dept_ids` | `TEXT` | 1 | `'[]'` | 0 |
| 4 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 5 | `updated_at` | `TEXT` | 1 | `None` | 0 |
| 6 | `user_ids` | `TEXT` | 1 | `'[]'` | 0 |
| 7 | `updated_by` | `TEXT` | 0 | `None` | 0 |

indexes:
- `idx_role_data_scopes_scope_type` unique=0 cols=['scope_type']
- `idx_role_data_scopes_role_id` unique=1 cols=['role_id']
- `sqlite_autoindex_role_data_scopes_1` unique=1 cols=['role_id']

row_count: `8`

## table `role_permissions`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `role_id` | `INTEGER` | 1 | `None` | 0 |
| 2 | `permission_id` | `INTEGER` | 1 | `None` | 0 |

indexes:
- `idx_role_permissions_role_id` unique=0 cols=['role_id']
- `idx_role_permissions_unique` unique=1 cols=['role_id', 'permission_id']

row_count: `55`

## table `roles`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `role_name` | `TEXT` | 1 | `None` | 0 |
| 2 | `data_scope` | `TEXT` | 1 | `'DEPT'` | 0 |
| 3 | `created_at` | `TEXT` | 1 | `None` | 0 |
| 4 | `status` | `TEXT` | 1 | `'ACTIVE'` | 0 |
| 5 | `is_deleted` | `INTEGER` | 1 | `0` | 0 |

indexes:
- `idx_roles_name` unique=1 cols=['role_name']
- `sqlite_autoindex_roles_1` unique=1 cols=['role_name']

row_count: `8`

## table `system_settings`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `key` | `TEXT` | 0 | `None` | 1 |
| 1 | `value` | `TEXT` | 1 | `None` | 0 |
| 2 | `updated_at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `sqlite_autoindex_system_settings_1` unique=1 cols=['key']

row_count: `1`

## table `user_roles`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `user_id` | `INTEGER` | 1 | `None` | 0 |
| 2 | `role_id` | `INTEGER` | 1 | `None` | 0 |

indexes:
- `idx_user_roles_user_id` unique=0 cols=['user_id']
- `idx_user_roles_unique` unique=1 cols=['user_id', 'role_id']

row_count: `3`

## table `users`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `username` | `TEXT` | 1 | `None` | 0 |
| 2 | `password_hash` | `TEXT` | 0 | `None` | 0 |
| 3 | `department` | `TEXT` | 1 | `None` | 0 |
| 4 | `employee_name` | `TEXT` | 1 | `None` | 0 |
| 5 | `employee_no` | `TEXT` | 1 | `None` | 0 |
| 6 | `role` | `TEXT` | 0 | `''` | 0 |
| 7 | `status` | `TEXT` | 1 | `'ACTIVE'` | 0 |
| 8 | `must_change_password` | `INTEGER` | 1 | `0` | 0 |
| 9 | `failed_login_attempts` | `INTEGER` | 1 | `0` | 0 |
| 10 | `lock_until` | `TEXT` | 0 | `None` | 0 |
| 11 | `password_updated_at` | `TEXT` | 0 | `None` | 0 |
| 12 | `position_id` | `INTEGER` | 0 | `None` | 0 |
| 13 | `email` | `TEXT` | 0 | `''` | 0 |
| 14 | `phone` | `TEXT` | 0 | `''` | 0 |

indexes:
- `sqlite_autoindex_users_1` unique=1 cols=['username']

row_count: `3`

## table `workflow_config`
| cid | name | type | notnull | default | pk |
|---:|---|---|---:|---|---:|
| 0 | `id` | `INTEGER` | 0 | `None` | 1 |
| 1 | `version` | `INTEGER` | 1 | `None` | 0 |
| 2 | `status` | `TEXT` | 1 | `None` | 0 |
| 3 | `config_json` | `TEXT` | 1 | `None` | 0 |
| 4 | `scope` | `TEXT` | 1 | `'ALL'` | 0 |
| 5 | `reason` | `TEXT` | 0 | `''` | 0 |
| 6 | `by` | `TEXT` | 0 | `''` | 0 |
| 7 | `at` | `TEXT` | 1 | `None` | 0 |

indexes:
- `idx_workflow_config_status_at` unique=0 cols=['status', 'at']
- `idx_workflow_config_version` unique=1 cols=['version']

row_count: `5`
