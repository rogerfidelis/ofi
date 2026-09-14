-- ============================================================
-- OFI - CORE.OPERADORES
--
-- Cadastro mestre dos operadores dos campos de petróleo.
-- A origem dos nomes é a coluna OPERADOR_C do shapefile ANP.
-- ============================================================

CREATE TABLE IF NOT EXISTS core.operadores (

    id_operador INTEGER GENERATED ALWAYS AS IDENTITY,

    nome_operador VARCHAR(150) NOT NULL,

    CONSTRAINT operadores_pkey
        PRIMARY KEY (id_operador),

    CONSTRAINT operadores_nome_operador_key
        UNIQUE (nome_operador)
);