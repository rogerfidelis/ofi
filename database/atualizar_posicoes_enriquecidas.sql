BEGIN;

-- Consolida a origem, preservando os IDs originais.
CREATE TEMP TABLE ofi_origem ON COMMIT DROP AS
SELECT
    e.id_empresa,
    p.*
FROM (
    SELECT 'BRAM'::text AS empresa, b.*
    FROM raw.posicoes_bram b

    UNION ALL

    SELECT 'CBO'::text AS empresa, c.*
    FROM raw.posicoes_cbo c

    UNION ALL

    SELECT 'STARNAV'::text AS empresa, s.*
    FROM raw.posicoes_starnav s
) p
LEFT JOIN core.empresas e
    ON UPPER(TRIM(e.nome_empresa)) = p.empresa;

-- Interrompe se o cadastro de empresas não for inequívoco.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM ofi_origem
        WHERE id_empresa IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM ofi_origem
        GROUP BY empresa, id_posicao
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Confira o cadastro das empresas: mapeamento ausente ou ambiguo.';
    END IF;
END $$;

-- Mostra dados que não podem entrar na tabela enriquecida.
SELECT
    empresa,
    COUNT(*) AS total_origem,
    COUNT(*) FILTER (
        WHERE data_consulta IS NULL
           OR latitude IS NULL
           OR longitude IS NULL
           OR latitude NOT BETWEEN -90 AND 90
           OR longitude NOT BETWEEN -180 AND 180
    ) AS registros_invalidos
FROM ofi_origem
GROUP BY empresa
ORDER BY empresa;

WITH validas AS (
    SELECT *,
        COUNT(*) OVER (
            PARTITION BY id_empresa, id_embarcacao, data_consulta
        ) AS quantidade_no_horario
    FROM ofi_origem
    WHERE data_consulta IS NOT NULL
      AND latitude BETWEEN -90 AND 90
      AND longitude BETWEEN -180 AND 180
),
anteriores AS (
    SELECT *,
        LAG(data_consulta) OVER w AS consulta_anterior,
        LAG(data_reportada) OVER w AS reportada_anterior,
        LAG(latitude) OVER w AS latitude_anterior,
        LAG(longitude) OVER w AS longitude_anterior,
        LAG(quantidade_no_horario) OVER w AS quantidade_anterior
    FROM validas
    WINDOW w AS (
        PARTITION BY id_empresa, id_embarcacao
        ORDER BY data_consulta, id_posicao
    )
),
movimento AS (
    SELECT *,
        CASE
            WHEN quantidade_no_horario = 1
             AND quantidade_anterior = 1
             AND data_consulta > consulta_anterior
            THEN ST_DistanceSphere(
                ST_SetSRID(
                    ST_MakePoint(
                        longitude_anterior::double precision,
                        latitude_anterior::double precision
                    ), 4326
                ),
                ST_SetSRID(
                    ST_MakePoint(
                        longitude::double precision,
                        latitude::double precision
                    ), 4326
                )
            ) / 1000.0
        END AS deslocamento_km,

        CASE
            WHEN quantidade_no_horario = 1
             AND quantidade_anterior = 1
             AND data_consulta > consulta_anterior
            THEN EXTRACT(
                EPOCH FROM (data_consulta - consulta_anterior)
            ) / 3600.0
        END AS horas_input,

        CASE
            WHEN quantidade_no_horario = 1
             AND quantidade_anterior = 1
             AND data_reportada > reportada_anterior
            THEN EXTRACT(
                EPOCH FROM (data_reportada - reportada_anterior)
            ) / 3600.0
        END AS horas_reportadas
    FROM anteriores
),
ativos_recentes AS (
    SELECT DISTINCT ON (id_ativo)
        id_ativo, data_consulta, latitude, longitude
    FROM raw.posicoes_ativos
    WHERE latitude BETWEEN -90 AND 90
      AND longitude BETWEEN -180 AND 180
    ORDER BY
        id_ativo,
        data_consulta DESC NULLS LAST,
        latitude,
        longitude
),
proximidades AS (
    SELECT
        m.*,
        a.id_ativo,
        a.distancia AS distancia_ativo,
        campo.id_campo,
        campo_posicao.nome AS campo,
        l.id_local,
        l.tipo_local,
        l.distancia AS distancia_local
    FROM movimento m

    LEFT JOIN LATERAL (
        SELECT
            ar.*,
            ST_DistanceSphere(
                ST_SetSRID(
                    ST_MakePoint(
                        m.longitude::double precision,
                        m.latitude::double precision
                    ), 4326
                ),
                ST_SetSRID(
                    ST_MakePoint(
                        ar.longitude::double precision,
                        ar.latitude::double precision
                    ), 4326
                )
            ) / 1000.0 AS distancia
        FROM ativos_recentes ar
        JOIN core.ativos at
            ON at.id_ativo = ar.id_ativo
        ORDER BY distancia, ar.id_ativo
        LIMIT 1
    ) a ON TRUE

    LEFT JOIN LATERAL (
        SELECT c.id_campo
        FROM core.campos c
        WHERE ST_Covers(
            c.geom,
            ST_Transform(
                ST_SetSRID(
                    ST_MakePoint(
                        a.longitude::double precision,
                        a.latitude::double precision
                    ), 4326
                ),
                ST_SRID(c.geom)
            )
        )
        ORDER BY c.id_campo
        LIMIT 1
    ) campo ON TRUE

    -- Campo que contém a posição atual da embarcação.
    -- ST_Covers inclui posições exatamente sobre o limite do polígono.
    LEFT JOIN LATERAL (
        SELECT c.nome
        FROM core.campos c
        WHERE ST_Covers(
            c.geom,
            ST_Transform(
                ST_SetSRID(
                    ST_MakePoint(
                        m.longitude::double precision,
                        m.latitude::double precision
                    ), 4326
                ),
                ST_SRID(c.geom)
            )
        )
        ORDER BY c.id_campo
        LIMIT 1
    ) campo_posicao ON TRUE

    LEFT JOIN LATERAL (
        SELECT
            lf.id_local,
            UPPER(TRIM(lf.tipo_local)) AS tipo_local,
            ST_DistanceSphere(
                ST_SetSRID(
                    ST_MakePoint(
                        m.longitude::double precision,
                        m.latitude::double precision
                    ), 4326
                ),
                ST_SetSRID(
                    ST_MakePoint(
                        lf.longitude::double precision,
                        lf.latitude::double precision
                    ), 4326
                )
            ) / 1000.0 AS distancia
        FROM core.locais_fixos lf
        WHERE lf.latitude BETWEEN -90 AND 90
          AND lf.longitude BETWEEN -180 AND 180
        ORDER BY distancia, lf.id_local
        LIMIT 1
    ) l ON TRUE
),
evidencias AS (
    SELECT *,
        CASE
            WHEN distancia_ativo IS NULL THEN NULL
            WHEN distancia_ativo <= 1 THEN 1.0
            WHEN distancia_ativo <= 3 THEN 0.8
            WHEN distancia_ativo <= 5 THEN 0.5
            WHEN distancia_ativo <= 10 THEN 0.2
            ELSE 0.0
        END AS ev_ativo,

        CASE
            WHEN distancia_local IS NULL THEN NULL
            WHEN distancia_local <= 1 THEN 1.0
            WHEN distancia_local <= 3 THEN 0.8
            WHEN distancia_local <= 5 THEN 0.5
            WHEN distancia_local <= 10 THEN 0.2
            ELSE 0.0
        END AS ev_local
    FROM proximidades
)
INSERT INTO analytics.posicoes_enriquecidas (
    id_empresa,
    id_posicao_origem,
    id_embarcacao,
    data_consulta,
    data_reportada,
    latitude,
    longitude,
    status_navegacao,
    distancia_km,
    delta_horas_input,
    delta_horas_reportada,
    velocidade_kmh,
    velocidade_knots,
    delta_coleta_reportada,
    id_ativo_proximo,
    distancia_ativo_km,
    evidencia_ativo,
    id_campo,
    campo,
    id_local_proximo,
    distancia_local_km,
    evidencia_local,
    contexto_operacional,
    evidencia_proximidade,
    data_processamento
)
SELECT
    id_empresa,
    id_posicao,
    id_embarcacao,
    data_consulta,
    data_reportada,
    latitude,
    longitude,
    status,
    deslocamento_km,
    horas_input,
    horas_reportadas,
    deslocamento_km / NULLIF(horas_input, 0),
    deslocamento_km / NULLIF(horas_input, 0) / 1.852,
    data_consulta - data_reportada,
    id_ativo,
    distancia_ativo,
    ev_ativo,
    CASE
        WHEN distancia_ativo <= 10
         AND (
             distancia_local IS NULL
             OR distancia_ativo <= distancia_local
         )
        THEN id_campo
    END,
    campo,
    id_local,
    distancia_local,
    ev_local,
    CASE
        WHEN distancia_ativo <= 10
         AND (
             distancia_local IS NULL
             OR distancia_ativo <= distancia_local
         )
        THEN 'PROXIMO_ATIVO'

        WHEN distancia_local <= 5
         AND (
             distancia_ativo IS NULL
             OR distancia_local < distancia_ativo
         )
         AND tipo_local IN ('PORTO', 'ESTALEIRO', 'FUNDEIO')
        THEN tipo_local

        ELSE 'EM_TRANSITO'
    END,
    GREATEST(ev_ativo, ev_local),
    CURRENT_TIMESTAMP
FROM evidencias
ON CONFLICT (id_empresa, id_posicao_origem)
DO UPDATE SET
    id_embarcacao = EXCLUDED.id_embarcacao,
    data_consulta = EXCLUDED.data_consulta,
    data_reportada = EXCLUDED.data_reportada,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    status_navegacao = EXCLUDED.status_navegacao,
    distancia_km = EXCLUDED.distancia_km,
    delta_horas_input = EXCLUDED.delta_horas_input,
    delta_horas_reportada = EXCLUDED.delta_horas_reportada,
    velocidade_kmh = EXCLUDED.velocidade_kmh,
    velocidade_knots = EXCLUDED.velocidade_knots,
    delta_coleta_reportada = EXCLUDED.delta_coleta_reportada,
    id_ativo_proximo = EXCLUDED.id_ativo_proximo,
    distancia_ativo_km = EXCLUDED.distancia_ativo_km,
    evidencia_ativo = EXCLUDED.evidencia_ativo,
    id_campo = EXCLUDED.id_campo,
    campo = EXCLUDED.campo,
    id_local_proximo = EXCLUDED.id_local_proximo,
    distancia_local_km = EXCLUDED.distancia_local_km,
    evidencia_local = EXCLUDED.evidencia_local,
    contexto_operacional = EXCLUDED.contexto_operacional,
    evidencia_proximidade = EXCLUDED.evidencia_proximidade,
    data_processamento = EXCLUDED.data_processamento;

-- Conferência da carga.
SELECT
    e.nome_empresa,
    COUNT(*) AS total_posicoes,
    MIN(p.data_consulta) AS primeira_posicao,
    MAX(p.data_consulta) AS ultima_posicao
FROM analytics.posicoes_enriquecidas p
JOIN core.empresas e USING (id_empresa)
GROUP BY e.nome_empresa
ORDER BY e.nome_empresa;

-- Deve retornar zero para todas as empresas.
SELECT
    o.empresa,
    COUNT(*) AS posicoes_validas_ausentes
FROM ofi_origem o
WHERE o.data_consulta IS NOT NULL
  AND o.latitude BETWEEN -90 AND 90
  AND o.longitude BETWEEN -180 AND 180
  AND NOT EXISTS (
      SELECT 1
      FROM analytics.posicoes_enriquecidas p
      WHERE p.id_empresa = o.id_empresa
        AND p.id_posicao_origem = o.id_posicao
  )
GROUP BY o.empresa;

-- Confirma a gravação na tabela permanente.
COMMIT;