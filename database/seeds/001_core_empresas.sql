-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Seed: empresas
-- ============================================================

INSERT INTO core.empresas (nome_empresa)
VALUES
    ('CBO'),
    ('BRAM'),
    ('STARNAV')
ON CONFLICT (nome) DO NOTHING;