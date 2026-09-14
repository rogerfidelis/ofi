-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 003
-- Tabela mestre de embarcações
-- ============================================================

CREATE TABLE IF NOT EXISTS core.embarcacoes (
    id_embarcacao INTEGER GENERATED ALWAYS AS IDENTITY,

    nome_embarcacao VARCHAR NOT NULL,

    id_empresa INTEGER NOT NULL,

    CONSTRAINT embarcacoes_pkey
        PRIMARY KEY (id_embarcacao),

    CONSTRAINT embarcacoes_nome_embarcacao_key
        UNIQUE (nome_embarcacao),

    CONSTRAINT embarcacoes_id_empresa_fkey
        FOREIGN KEY (id_empresa)
        REFERENCES core.empresas (id_empresa)
);