CREATE TABLE IF NOT EXISTS analytics.posicoes_enriquecidas (

    id_posicao_enriquecida BIGINT GENERATED ALWAYS AS IDENTITY,

    -- Origem da posição
    id_embarcacao INTEGER NOT NULL,
    data_consulta TIMESTAMP NOT NULL,
    data_reportada TIMESTAMP,

    latitude NUMERIC(10,7) NOT NULL,
    longitude NUMERIC(10,7) NOT NULL,

    status_navegacao VARCHAR(100),

    -- Movimento da embarcação
    distancia_km NUMERIC(12,3),
    delta_horas_input NUMERIC(12,3),
    delta_horas_reportada NUMERIC(12,3),
    velocidade_kmh NUMERIC(12,2),
    velocidade_knots NUMERIC(12,2),
    delta_coleta_reportada INTERVAL,

    -- Proximidade de ativo offshore
    id_ativo_proximo INTEGER,
    distancia_ativo_km NUMERIC(12,3),
    evidencia_ativo NUMERIC(3,2),

    -- Campo onde está localizado o ativo
    id_campo BIGINT,

    -- Proximidade de infraestrutura logística
    id_local_proximo INTEGER,
    distancia_local_km NUMERIC(12,3),
    evidencia_local NUMERIC(3,2),

    -- Inferência final
    contexto_operacional VARCHAR(30),
    evidencia_proximidade NUMERIC(3,2),

    data_processamento TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- =====================================================
    -- CONSTRAINTS
    -- =====================================================

    CONSTRAINT posicoes_enriquecidas_pkey
        PRIMARY KEY (id_posicao_enriquecida),

    CONSTRAINT posicoes_enriquecidas_embarcacao_fkey
        FOREIGN KEY (id_embarcacao)
        REFERENCES core.embarcacoes (id_embarcacao),

    CONSTRAINT posicoes_enriquecidas_ativo_fkey
        FOREIGN KEY (id_ativo_proximo)
        REFERENCES core.ativos (id_ativo),

    CONSTRAINT posicoes_enriquecidas_local_fkey
        FOREIGN KEY (id_local_proximo)
        REFERENCES core.locais_fixos (id_local),

    CONSTRAINT posicoes_enriquecidas_campo_fkey
        FOREIGN KEY (id_campo)
        REFERENCES core.campos (id_campo),

    CONSTRAINT posicoes_enriquecidas_contexto_check
        CHECK (
            contexto_operacional IS NULL
            OR contexto_operacional IN (
                'PORTO',
                'ESTALEIRO',
                'FUNDEIO',
                'PROXIMO_ATIVO',
                'EM_TRANSITO'
            )
        ),

    CONSTRAINT posicoes_enriquecidas_evidencia_ativo_check
        CHECK (
            evidencia_ativo IS NULL
            OR evidencia_ativo BETWEEN 0 AND 1
        ),

    CONSTRAINT posicoes_enriquecidas_evidencia_local_check
        CHECK (
            evidencia_local IS NULL
            OR evidencia_local BETWEEN 0 AND 1
        ),

    CONSTRAINT posicoes_enriquecidas_evidencia_check
        CHECK (
            evidencia_proximidade IS NULL
            OR evidencia_proximidade BETWEEN 0 AND 1
        )
);