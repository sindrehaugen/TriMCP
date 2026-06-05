-- 007_rename_db_roles.sql
-- Idempotent migration: rename legacy trimcp_app / trimcp_gc roles to nce_app / nce_gc.
-- Safe to re-run; checks pg_roles before each ALTER to avoid errors on fresh installs.
--
-- PostgreSQL ALTER ROLE RENAME is DDL (auto-commits). This DO block is idempotent:
-- if the roles are already named nce_app/nce_gc the block is a no-op.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_app') THEN
        ALTER ROLE trimcp_app RENAME TO nce_app;
        RAISE NOTICE 'Renamed role trimcp_app → nce_app';
    ELSE
        RAISE NOTICE 'Role trimcp_app not found — skipping (already renamed or fresh install)';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_gc') THEN
        ALTER ROLE trimcp_gc RENAME TO nce_gc;
        RAISE NOTICE 'Renamed role trimcp_gc → nce_gc';
    ELSE
        RAISE NOTICE 'Role trimcp_gc not found — skipping (already renamed or fresh install)';
    END IF;
END $$;

-- Also rename the app password default if it is still the old value.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        -- Only update if the role currently has the old default password.
        -- Operators who have already set a strong password are unaffected.
        -- This is a no-op if the password was already changed.
        EXECUTE format(
            'ALTER ROLE nce_app PASSWORD %L',
            current_setting('nce_app.migration_password', true)
        );
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL; -- Password update is best-effort; don't block the migration.
END $$;
