-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 005
-- Posições históricas das embarcações CBO
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.posicoes_cbo (

    id_posicao BIGSERIAL PRIMARY KEY,

    id_embarcacao INTEGER NOT NULL,

    data_consulta TIMESTAMP,

    latitude NUMERIC(10,7),

    longitude NUMERIC(10,7),

    data_reportada TIMESTAMP,

    status VARCHAR(100),

    CONSTRAINT posicoes_cbo_id_embarcacao_fkey
        FOREIGN KEY (id_embarcacao)
        REFERENCES core.embarcacoes (id_embarcacao),

    CONSTRAINT posicoes_cbo_unique
        UNIQUE (
            id_embarcacao,
            data_consulta,
            latitude,
            longitude,
            data_reportada,
            status
        )

);