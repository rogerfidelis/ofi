-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 006
-- Posições históricas das embarcações STARNAV
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.posicoes_starnav (

    id_posicao BIGSERIAL PRIMARY KEY,

    id_embarcacao INTEGER NOT NULL,

    data_consulta TIMESTAMP,

    latitude NUMERIC(10,7),

    longitude NUMERIC(10,7),

    data_reportada TIMESTAMP,

    status VARCHAR(100),

    CONSTRAINT posicoes_starnav_id_embarcacao_fkey
        FOREIGN KEY (id_embarcacao)
        REFERENCES core.embarcacoes (id_embarcacao),

    CONSTRAINT posicoes_starnav_unique
        UNIQUE (
            id_embarcacao,
            data_consulta,
            latitude,
            longitude,
            data_reportada,
            status
        )

);