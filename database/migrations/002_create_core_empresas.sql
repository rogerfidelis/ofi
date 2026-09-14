-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 002
-- Tabela mestre de empresas
-- ============================================================

CREATE TABLE IF NOT EXISTS core.empresas (
    id_empresa INTEGER GENERATED ALWAYS AS IDENTITY,
    nome_empresa VARCHAR NOT NULL,

    CONSTRAINT empresas_pkey
        PRIMARY KEY (id_empresa),

    CONSTRAINT empresas_nome_empresa_key
        UNIQUE (nome_empresa)
);