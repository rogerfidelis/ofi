SET client_min_messages = NOTICE;

DO $$
DECLARE
    r RECORD;
    quantidade BIGINT;
BEGIN
    RAISE NOTICE 'SCHEMA | TABELA | REGISTROS';

    FOR r IN
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('core', 'raw', 'analytics')
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
    LOOP
        EXECUTE format(
            'SELECT COUNT(*) FROM %I.%I',
            r.table_schema,
            r.table_name
        )
        INTO quantidade;

        RAISE NOTICE '% | % | %',
            r.table_schema,
            r.table_name,
            quantidade;
    END LOOP;
END $$;