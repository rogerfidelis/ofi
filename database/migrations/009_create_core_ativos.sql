CREATE TABLE IF NOT EXISTS core.ativos (

    id_ativo INTEGER GENERATED ALWAYS AS IDENTITY,

    nome_ativo VARCHAR(100) NOT NULL,

    tipo_ativo VARCHAR(50) NOT NULL,

    CONSTRAINT ativos_pkey
        PRIMARY KEY (id_ativo),

    CONSTRAINT ativos_nome_ativo_key
        UNIQUE (nome_ativo),

    CONSTRAINT ativos_tipo_ativo_check
        CHECK (
            tipo_ativo IN (
                'navio sonda',
                'FPSO',
                'Semi-Sub/Prod/Perfuração',
                'Semi-Sub/Perfuração',
                'Fixa (Habitada)',
                'Semi-Sub/Produção',
                'Fixa (Rebombeio)'
            )
        )
);