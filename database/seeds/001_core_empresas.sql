-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Seed: empresas
-- ============================================================

INSERT INTO core.empresas (nome)
VALUES
    ('CBO'),
    ('BRAM'),
    ('STARNAV')
ON CONFLICT (nome) DO NOTHING;