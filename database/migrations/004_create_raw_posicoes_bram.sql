-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 004
-- Posições históricas das embarcações BRAM
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.posicoes_bram (

    id_posicao BIGSERIAL PRIMARY KEY,

    id_embarcacao INTEGER NOT NULL,

    data_consulta TIMESTAMP,

    latitude NUMERIC(10,7),

    longitude NUMERIC(10,7),

    data_reportada TIMESTAMP,

    status VARCHAR(100),

    CONSTRAINT posicoes_bram_id_embarcacao_fkey
        FOREIGN KEY (id_embarcacao)
        REFERENCES core.embarcacoes (id_embarcacao),

    CONSTRAINT posicoes_bram_unique
        UNIQUE (
            id_embarcacao,
            data_consulta,
            latitude,
            longitude,
            data_reportada,
            status
        )
);