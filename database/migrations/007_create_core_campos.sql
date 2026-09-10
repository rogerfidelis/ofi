-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Migration 007
-- Cadastro dos campos de petróleo
-- Geometria: SIRGAS 2000 / EPSG:4674
-- ============================================================

CREATE TABLE IF NOT EXISTS core.campos (

    id_campo BIGSERIAL PRIMARY KEY,

    id_origem INTEGER,

    codigo_campo INTEGER NOT NULL,

    sigla VARCHAR(20),

    nome VARCHAR(150) NOT NULL,

    bacia VARCHAR(100),

    operadora_id BIGINT,

    area_km2 NUMERIC(12,3),

    numero_contrato VARCHAR(30),

    numero_rodada VARCHAR(30),

    data_assinatura DATE,

    data_termino DATE,

    data_descoberta DATE,

    data_inicio DATE,

    etapa VARCHAR(50),

    lamina_agua_m NUMERIC(10,2),

    fluido_principal VARCHAR(30),

    ambiente VARCHAR(20),

    geom geometry(MultiPolygon, 4674) NOT NULL,

    ativo BOOLEAN DEFAULT TRUE,

    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);