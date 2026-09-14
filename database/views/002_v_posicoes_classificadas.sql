-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- VIEW: analytics.v_posicoes_classificadas
--
-- OBJETIVO:
-- Interpretar operacionalmente cada posição AIS das embarcações,
-- relacionando-a ao ativo offshore ou local fixo mais próximo.
--
-- REGRAS DE PROXIMIDADE:
-- <= 1 km  -> evidencia 1.0
-- <= 3 km  -> evidencia 0.8
-- <= 5 km  -> evidencia 0.5
-- <= 10 km -> evidencia 0.2
-- > 10 km  -> evidencia 0.0
--
-- IMPORTANTE:
-- Para ativos móveis, utiliza a posição conhecida mais recente
-- do ativo cuja data_consulta seja <= data_consulta da embarcação.
-- ============================================================

CREATE OR REPLACE VIEW analytics.v_posicoes_classificadas AS

SELECT
    v.empresa,
    v.id_embarcacao,
    v.data_consulta,
    v.data_reportada,
    v.latitude,
    v.longitude,
    v.status,

    -- ========================================================
    -- REFERÊNCIA OPERACIONAL MAIS PRÓXIMA
    -- ========================================================

    CASE
        WHEN
            COALESCE(a.distancia_km, 999999) > 10
            AND COALESCE(l.distancia_km, 999999) > 10
            THEN 'SEM_REFERENCIA'

        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
            THEN 'ATIVO'

        ELSE 'LOCAL_FIXO'
    END AS tipo_referencia,

    -- ========================================================
    -- ATIVO
    -- ========================================================

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.id_ativo
    END AS id_ativo,

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.nome_ativo
    END AS nome_ativo,

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.tipo_ativo
    END AS tipo_ativo,

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.data_posicao_ativo
    END AS data_posicao_ativo,

    -- ========================================================
    -- CAMPO
    -- ========================================================

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.id_campo
    END AS id_campo,

    CASE
        WHEN COALESCE(a.distancia_km, 999999)
             <= COALESCE(l.distancia_km, 999999)
             AND a.distancia_km <= 10
        THEN a.nome_campo
    END AS nome_campo,

    -- ========================================================
    -- LOCAL FIXO
    -- ========================================================

    CASE
        WHEN COALESCE(l.distancia_km, 999999)
             < COALESCE(a.distancia_km, 999999)
             AND l.distancia_km <= 10
        THEN l.id_local
    END AS id_local,

    CASE
        WHEN COALESCE(l.distancia_km, 999999)
             < COALESCE(a.distancia_km, 999999)
             AND l.distancia_km <= 10
        THEN l.nome_local
    END AS nome_local,

    CASE
        WHEN COALESCE(l.distancia_km, 999999)
             < COALESCE(a.distancia_km, 999999)
             AND l.distancia_km <= 10
        THEN l.tipo_local
    END AS tipo_local,

    -- ========================================================
    -- MENOR DISTÂNCIA
    -- ========================================================

    CASE
        WHEN
            COALESCE(a.distancia_km, 999999) > 10
            AND COALESCE(l.distancia_km, 999999) > 10
            THEN LEAST(
                COALESCE(a.distancia_km, 999999),
                COALESCE(l.distancia_km, 999999)
            )

        ELSE LEAST(
            COALESCE(a.distancia_km, 999999),
            COALESCE(l.distancia_km, 999999)
        )
    END AS menor_distancia_km,

    -- ========================================================
    -- EVIDÊNCIA DE PROXIMIDADE
    -- ========================================================

    CASE
        WHEN LEAST(
            COALESCE(a.distancia_km, 999999),
            COALESCE(l.distancia_km, 999999)
        ) <= 1
            THEN 1.0

        WHEN LEAST(
            COALESCE(a.distancia_km, 999999),
            COALESCE(l.distancia_km, 999999)
        ) <= 3
            THEN 0.8

        WHEN LEAST(
            COALESCE(a.distancia_km, 999999),
            COALESCE(l.distancia_km, 999999)
        ) <= 5
            THEN 0.5

        WHEN LEAST(
            COALESCE(a.distancia_km, 999999),
            COALESCE(l.distancia_km, 999999)
        ) <= 10
            THEN 0.2

        ELSE 0.0
    END AS evidencia_proximidade,

    -- ========================================================
    -- CLASSIFICAÇÃO OPERACIONAL
    -- ========================================================

    CASE

        -- ATIVO OFFSHORE
        WHEN
            COALESCE(a.distancia_km, 999999)
            <= COALESCE(l.distancia_km, 999999)
            AND a.distancia_km <= 5
            THEN 'ATENDIMENTO_OFFSHORE'

        WHEN
            COALESCE(a.distancia_km, 999999)
            <= COALESCE(l.distancia_km, 999999)
            AND a.distancia_km <= 10
            THEN 'PROXIMIDADE_ATIVO'

        -- LOCAL FIXO
        WHEN
            COALESCE(l.distancia_km, 999999)
            < COALESCE(a.distancia_km, 999999)
            AND l.distancia_km <= 5
            THEN UPPER(l.tipo_local)

        WHEN
            COALESCE(l.distancia_km, 999999)
            < COALESCE(a.distancia_km, 999999)
            AND l.distancia_km <= 10
            THEN 'PROXIMIDADE_LOCAL_FIXO'

        ELSE 'TRANSITO'

    END AS classificacao_operacional


FROM analytics.v_posicoes_embarcacoes v


-- ============================================================
-- ATIVO OFFSHORE MAIS PRÓXIMO
-- -- posição mais recente disponível de cada ativo
-- raw.posicoes_ativos é tratado atualmente como snapshot operacional
-- ============================================================

LEFT JOIN LATERAL (

    SELECT
        pa.id_ativo,
        at.nome_ativo AS nome_ativo,
        at.tipo_ativo,
        pa.data_consulta AS data_posicao_ativo,

        c.id_campo,
        c.nome AS nome_campo,

        (
            ST_DistanceSphere(
                ST_SetSRID(
                    ST_MakePoint(v.longitude, v.latitude),
                    4326
                ),
                ST_SetSRID(
                    ST_MakePoint(pa.longitude, pa.latitude),
                    4326
                )
            ) / 1000.0
        ) AS distancia_km

    FROM (

       -- Última posição disponível de cada ativo
        -- usada como referência espacial atual
        SELECT DISTINCT ON (p.id_ativo)
            p.id_ativo,
            p.data_consulta,
            p.latitude,
            p.longitude

        FROM raw.posicoes_ativos p

        WHERE
            p.latitude IS NOT NULL
            AND p.longitude IS NOT NULL

        ORDER BY
            p.id_ativo,
            p.data_consulta DESC

    ) pa

    JOIN core.ativos at
        ON at.id_ativo = pa.id_ativo

    LEFT JOIN core.campos c
        ON ST_Covers(
            c.geom,
            ST_SetSRID(
                ST_MakePoint(
                    pa.longitude,
                    pa.latitude
                ),
                4674
            )
        )

    ORDER BY
        ST_DistanceSphere(
            ST_SetSRID(
                ST_MakePoint(v.longitude, v.latitude),
                4326
            ),
            ST_SetSRID(
                ST_MakePoint(pa.longitude, pa.latitude),
                4326
            )
        )

    LIMIT 1

) a ON TRUE


-- ============================================================
-- LOCAL FIXO MAIS PRÓXIMO
-- porto / estaleiro / fundeio
-- ============================================================

LEFT JOIN LATERAL (

    SELECT
        lf.id_local,
        lf.nome_local AS nome_local,
        lf.tipo_local,

        (
            ST_DistanceSphere(
                ST_SetSRID(
                    ST_MakePoint(v.longitude, v.latitude),
                    4326
                ),
                ST_SetSRID(
                    ST_MakePoint(lf.longitude, lf.latitude),
                    4326
                )
            ) / 1000.0
        ) AS distancia_km

    FROM core.locais_fixos lf

    WHERE
        lf.latitude IS NOT NULL
        AND lf.longitude IS NOT NULL

    ORDER BY
        ST_DistanceSphere(
            ST_SetSRID(
                ST_MakePoint(v.longitude, v.latitude),
                4326
            ),
            ST_SetSRID(
                ST_MakePoint(lf.longitude, lf.latitude),
                4326
            )
        )

    LIMIT 1

) l ON TRUE;