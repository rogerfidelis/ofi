CREATE TABLE IF NOT EXISTS core.locais_fixos (

    id_local INTEGER GENERATED ALWAYS AS IDENTITY,

    nome_local VARCHAR(100) NOT NULL,

    tipo_local VARCHAR(50) NOT NULL,

    latitude NUMERIC(10,8) NOT NULL,

    longitude NUMERIC(11,8) NOT NULL,

    CONSTRAINT locais_fixos_pkey
        PRIMARY KEY (id_local),

    CONSTRAINT locais_fixos_nome_key
        UNIQUE (nome_local),

    CONSTRAINT locais_fixos_tipo_check
        CHECK (tipo_local IN ('PORTO', 'ESTALEIRO'))
);