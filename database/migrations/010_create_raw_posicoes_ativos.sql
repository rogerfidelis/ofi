CREATE TABLE IF NOT EXISTS raw.posicoes_ativos (

    id_posicao BIGINT GENERATED ALWAYS AS IDENTITY,

    id_ativo INTEGER NOT NULL,

    data_consulta TIMESTAMP NOT NULL,

    latitude NUMERIC(10,8) NOT NULL,

    longitude NUMERIC(11,8) NOT NULL,

    CONSTRAINT posicoes_ativos_pkey
        PRIMARY KEY (id_posicao),

    CONSTRAINT posicoes_ativos_id_ativo_fkey
        FOREIGN KEY (id_ativo)
        REFERENCES core.ativos (id_ativo),

    CONSTRAINT posicoes_ativos_unique
        UNIQUE (
            id_ativo,
            data_consulta,
            latitude,
            longitude
        )
);