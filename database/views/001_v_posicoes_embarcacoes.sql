-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- VIEW: analytics.v_posicoes_embarcacoes
--
-- OBJETIVO:
-- Consolidar as posições AIS das embarcações das empresas
-- BRAM, CBO e STARNAV em uma única camada de consulta.
--
-- IMPORTANTE:
-- Esta view NÃO realiza inferência operacional.
-- Não calcula proximidade, ativo, campo ou local fixo.
-- ============================================================


-- ============================================================
-- SCHEMA ANALYTICS
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analytics;


-- ============================================================
-- VIEW CONSOLIDADA DE POSIÇÕES
-- ============================================================

CREATE OR REPLACE VIEW analytics.v_posicoes_embarcacoes AS


-- ------------------------------------------------------------
-- BRAM
-- ------------------------------------------------------------

SELECT
    'BRAM'::text AS empresa,
    id_embarcacao,
    data_consulta,
    latitude,
    longitude,
    data_reportada,
    status

FROM raw.posicoes_bram


UNION ALL


-- ------------------------------------------------------------
-- CBO
-- ------------------------------------------------------------

SELECT
    'CBO'::text AS empresa,
    id_embarcacao,
    data_consulta,
    latitude,
    longitude,
    data_reportada,
    status

FROM raw.posicoes_cbo


UNION ALL


-- ------------------------------------------------------------
-- STARNAV
-- ------------------------------------------------------------

SELECT
    'STARNAV'::text AS empresa,
    id_embarcacao,
    data_consulta,
    latitude,
    longitude,
    data_reportada,
    status

FROM raw.posicoes_starnav;