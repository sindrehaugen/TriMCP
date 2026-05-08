-- ============================================================================
-- TriMCP Migration: Quota Lower-Bound Safety — DB-Level CHECK Constraint
-- Target: Defense in depth — prevent manual operator errors from setting
--         negative ``used_amount`` values on ``resource_quotas``.
--
-- The application layer already uses ``GREATEST(0, used - delta)`` in
-- ``QuotaReservation.rollback()``, but relying purely on application logic
-- leaves the database vulnerable to ad-hoc SQL or operator mistakes.
-- This CHECK constraint provides a database-level guarantee.
-- ============================================================================

-- 1. Add CHECK (used_amount >= 0) to resource_quotas if it doesn't already exist.
-- The schema.sql CREATE TABLE already includes this constraint, but existing
-- deployments may have been created before the constraint was in place.
DO $$
DECLARE
    constraint_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'resource_quotas'::regclass
          AND conname = 'chk_resource_quotas_used_amount_nonnegative'
    ) INTO constraint_exists;

    IF NOT constraint_exists THEN
        ALTER TABLE resource_quotas
        ADD CONSTRAINT chk_resource_quotas_used_amount_nonnegative
        CHECK (used_amount >= 0);
        RAISE NOTICE '003_quota_check: Added CHECK (used_amount >= 0) to resource_quotas';
    ELSE
        RAISE NOTICE '003_quota_check: CHECK constraint already present — skipping';
    END IF;
END $$;

-- 2. Quality gate: verify no existing rows violate the constraint.
-- This catches pre-existing negative used_amount values before the
-- constraint was applied (if any exist due to operator error).
DO $$
DECLARE
    negative_count bigint;
BEGIN
    SELECT count(*) INTO negative_count
    FROM resource_quotas
    WHERE used_amount < 0;

    IF negative_count > 0 THEN
        RAISE WARNING '003_quota_check: Found % row(s) with negative used_amount — '
                      'these violate the new CHECK constraint. Consider running: '
                      'UPDATE resource_quotas SET used_amount = 0 WHERE used_amount < 0;',
                      negative_count;
    ELSE
        RAISE NOTICE '003_quota_check quality gate: 0 rows with negative used_amount — OK';
    END IF;
END $$;
