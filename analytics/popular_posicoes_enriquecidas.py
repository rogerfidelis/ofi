from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE = Path(__file__).resolve().parents[1]

load_dotenv(BASE / ".env")

DB_HOST = os.getenv("OFI_DB_HOST")
DB_PORT = os.getenv("OFI_DB_PORT")
DB_NAME = os.getenv("OFI_DB_NAME")
DB_USER = os.getenv("OFI_DB_USER")
DB_PASSWORD = os.getenv("OFI_DB_PASSWORD")
DB_SSLMODE = os.getenv("OFI_DB_SSLMODE", "require")


EMPRESAS = {
    "BRAM": "raw.posicoes_bram",
    "CBO": "raw.posicoes_cbo",
    "STARNAV": "raw.posicoes_starnav",
}


# ============================================================
# CONEXÃO
# ============================================================

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?sslmode={DB_SSLMODE}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def obter_id_empresa(conn, nome_empresa):
    sql = text("""
        SELECT id_empresa
        FROM core.empresas
        WHERE UPPER(nome_empresa) = UPPER(:nome_empresa)
    """)

    resultado = conn.execute(
        sql,
        {"nome_empresa": nome_empresa}
    ).scalar()

    if resultado is None:
        raise RuntimeError(
            f"Empresa {nome_empresa} não encontrada em core.empresas."
        )

    return resultado


def contar_raw(conn, tabela_raw):
    sql = text(f"""
        SELECT COUNT(*)
        FROM {tabela_raw}
    """)

    return conn.execute(sql).scalar()


def contar_analytics_empresa(conn, id_empresa):
    sql = text("""
        SELECT COUNT(*)
        FROM analytics.posicoes_enriquecidas
        WHERE id_empresa = :id_empresa
    """)

    return conn.execute(
        sql,
        {"id_empresa": id_empresa}
    ).scalar()


def contar_pendentes(conn, tabela_raw, id_empresa):
    sql = text(f"""
        SELECT COUNT(*)
        FROM {tabela_raw} r
        WHERE NOT EXISTS (
            SELECT 1
            FROM analytics.posicoes_enriquecidas a
            WHERE a.id_empresa = :id_empresa
              AND a.id_posicao_origem = r.id_posicao
        )
    """)

    return conn.execute(
        sql,
        {"id_empresa": id_empresa}
    ).scalar()


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_empresa(conn, nome_empresa, tabela_raw):

    id_empresa = obter_id_empresa(
        conn,
        nome_empresa
    )

    total_raw = contar_raw(
        conn,
        tabela_raw
    )

    total_antes = contar_analytics_empresa(
        conn,
        id_empresa
    )

    pendentes = contar_pendentes(
        conn,
        tabela_raw,
        id_empresa
    )

    print()
    print("-" * 70)
    print(f"EMPRESA: {nome_empresa}")
    print("-" * 70)

    print(f"Registros RAW:                  {total_raw}")
    print(f"Já existentes em analytics:    {total_antes}")
    print(f"Pendentes de processamento:    {pendentes}")

    if pendentes == 0:
        print("Nenhuma nova posição para processar.")
        return 0

    sql = text(f"""

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

            id_local_proximo,
            distancia_local_km,
            evidencia_local,

            contexto_operacional,
            evidencia_proximidade,

            data_processamento
        )

        WITH historico AS (

            SELECT

                r.id_posicao,
                r.id_embarcacao,
                r.data_consulta,
                r.data_reportada,
                r.latitude,
                r.longitude,
                r.status,

                LAG(r.latitude) OVER (
                    PARTITION BY r.id_embarcacao
                    ORDER BY
                        r.data_consulta,
                        r.id_posicao
                ) AS latitude_anterior,

                LAG(r.longitude) OVER (
                    PARTITION BY r.id_embarcacao
                    ORDER BY
                        r.data_consulta,
                        r.id_posicao
                ) AS longitude_anterior,

                LAG(r.data_consulta) OVER (
                    PARTITION BY r.id_embarcacao
                    ORDER BY
                        r.data_consulta,
                        r.id_posicao
                ) AS data_consulta_anterior,

                LAG(r.data_reportada) OVER (
                    PARTITION BY r.id_embarcacao
                    ORDER BY
                        r.data_consulta,
                        r.id_posicao
                ) AS data_reportada_anterior

            FROM {tabela_raw} r

            WHERE
                r.latitude IS NOT NULL
                AND r.longitude IS NOT NULL
                AND r.data_consulta IS NOT NULL
        ),

        pendentes AS (

            SELECT h.*

            FROM historico h

            WHERE NOT EXISTS (

                SELECT 1

                FROM analytics.posicoes_enriquecidas pe

                WHERE
                    pe.id_empresa = :id_empresa
                    AND pe.id_posicao_origem = h.id_posicao
            )
        ),

        movimento AS (

            SELECT

                p.*,

                CASE

                    WHEN
                        p.latitude_anterior IS NOT NULL
                        AND p.longitude_anterior IS NOT NULL

                    THEN

                        ST_Distance(

                            ST_SetSRID(
                                ST_MakePoint(
                                    p.longitude,
                                    p.latitude
                                ),
                                4674
                            )::geography,

                            ST_SetSRID(
                                ST_MakePoint(
                                    p.longitude_anterior,
                                    p.latitude_anterior
                                ),
                                4674
                            )::geography

                        ) / 1000.0

                END AS distancia_km_calc,


                CASE

                    WHEN p.data_consulta_anterior IS NOT NULL

                    THEN

                        EXTRACT(
                            EPOCH FROM (
                                p.data_consulta
                                -
                                p.data_consulta_anterior
                            )
                        ) / 3600.0

                END AS delta_horas_input_calc,


                CASE

                    WHEN
                        p.data_reportada IS NOT NULL
                        AND p.data_reportada_anterior IS NOT NULL

                    THEN

                        EXTRACT(
                            EPOCH FROM (
                                p.data_reportada
                                -
                                p.data_reportada_anterior
                            )
                        ) / 3600.0

                END AS delta_horas_reportada_calc

            FROM pendentes p
        ),

        enriquecido AS (

            SELECT

                m.*,

                ativo.id_ativo,
                ativo.latitude_ativo,
                ativo.longitude_ativo,
                ativo.distancia_ativo_km,

                campo.id_campo,

                local.id_local,
                local.tipo_local,
                local.distancia_local_km

            FROM movimento m


            -- ====================================================
            -- ATIVO OFFSHORE MAIS PRÓXIMO
            -- ====================================================

            LEFT JOIN LATERAL (

                SELECT

                    candidatos.id_ativo,
                    candidatos.latitude AS latitude_ativo,
                    candidatos.longitude AS longitude_ativo,

                    ST_Distance(

                        ST_SetSRID(
                            ST_MakePoint(
                                m.longitude,
                                m.latitude
                            ),
                            4674
                        )::geography,

                        ST_SetSRID(
                            ST_MakePoint(
                                candidatos.longitude,
                                candidatos.latitude
                            ),
                            4674
                        )::geography

                    ) / 1000.0 AS distancia_ativo_km


                FROM (

                    SELECT

                        a.id_ativo,
                        pa.latitude,
                        pa.longitude

                    FROM core.ativos a

                    JOIN LATERAL (

                        SELECT
                            pxa.latitude,
                            pxa.longitude

                        FROM raw.posicoes_ativos pxa

                        WHERE
                            pxa.id_ativo = a.id_ativo
                            AND pxa.latitude IS NOT NULL
                            AND pxa.longitude IS NOT NULL

                        ORDER BY
                            ABS(
                                EXTRACT(
                                    EPOCH FROM (
                                        pxa.data_consulta
                                        -
                                        m.data_consulta
                                    )
                                )
                            )

                        LIMIT 1

                    ) pa
                    ON TRUE

                ) candidatos

                ORDER BY

                    ST_Distance(

                        ST_SetSRID(
                            ST_MakePoint(
                                m.longitude,
                                m.latitude
                            ),
                            4674
                        )::geography,

                        ST_SetSRID(
                            ST_MakePoint(
                                candidatos.longitude,
                                candidatos.latitude
                            ),
                            4674
                        )::geography
                    )

                LIMIT 1

            ) ativo
            ON TRUE


            -- ====================================================
            -- CAMPO DO ATIVO
            -- ====================================================

            LEFT JOIN LATERAL (

                SELECT
                    c.id_campo

                FROM core.campos c

                WHERE

                    ativo.id_ativo IS NOT NULL

                    AND ST_Intersects(

                        c.geom,

                        ST_SetSRID(
                            ST_MakePoint(
                                ativo.longitude_ativo,
                                ativo.latitude_ativo
                            ),
                            4674
                        )
                    )

                LIMIT 1

            ) campo
            ON TRUE


            -- ====================================================
            -- LOCAL FIXO MAIS PRÓXIMO
            -- ====================================================

            LEFT JOIN LATERAL (

                SELECT

                    lf.id_local,
                    lf.tipo_local,

                    ST_Distance(

                        ST_SetSRID(
                            ST_MakePoint(
                                m.longitude,
                                m.latitude
                            ),
                            4674
                        )::geography,

                        ST_SetSRID(
                            ST_MakePoint(
                                lf.longitude,
                                lf.latitude
                            ),
                            4674
                        )::geography

                    ) / 1000.0 AS distancia_local_km

                FROM core.locais_fixos lf

                WHERE
                    lf.latitude IS NOT NULL
                    AND lf.longitude IS NOT NULL

                ORDER BY

                    ST_Distance(

                        ST_SetSRID(
                            ST_MakePoint(
                                m.longitude,
                                m.latitude
                            ),
                            4674
                        )::geography,

                        ST_SetSRID(
                            ST_MakePoint(
                                lf.longitude,
                                lf.latitude
                            ),
                            4674
                        )::geography
                    )

                LIMIT 1

            ) local
            ON TRUE
        ),

        evidencias AS (

            SELECT

                e.*,


                CASE

                    WHEN e.distancia_ativo_km IS NULL
                        THEN NULL

                    WHEN e.distancia_ativo_km <= 1
                        THEN 1.00

                    WHEN e.distancia_ativo_km <= 3
                        THEN 0.80

                    WHEN e.distancia_ativo_km <= 5
                        THEN 0.50

                    WHEN e.distancia_ativo_km <= 10
                        THEN 0.20

                    ELSE 0.00

                END AS evidencia_ativo_calc,


                CASE

                    WHEN e.distancia_local_km IS NULL
                        THEN NULL

                    WHEN e.distancia_local_km <= 1
                        THEN 1.00

                    WHEN e.distancia_local_km <= 3
                        THEN 0.80

                    WHEN e.distancia_local_km <= 5
                        THEN 0.50

                    WHEN e.distancia_local_km <= 10
                        THEN 0.20

                    ELSE 0.00

                END AS evidencia_local_calc

            FROM enriquecido e
        )

        SELECT

            :id_empresa,
            ev.id_posicao,

            ev.id_embarcacao,
            ev.data_consulta,
            ev.data_reportada,

            ev.latitude,
            ev.longitude,

            ev.status,

            ROUND(
                ev.distancia_km_calc::numeric,
                3
            ),

            ROUND(
                ev.delta_horas_input_calc::numeric,
                3
            ),

            ROUND(
                ev.delta_horas_reportada_calc::numeric,
                3
            ),


            CASE

                WHEN
                    ev.distancia_km_calc IS NOT NULL
                    AND ev.delta_horas_input_calc > 0

                THEN ROUND(

                    (
                        ev.distancia_km_calc
                        /
                        ev.delta_horas_input_calc
                    )::numeric,

                    2
                )

            END AS velocidade_kmh,


            CASE

                WHEN
                    ev.distancia_km_calc IS NOT NULL
                    AND ev.delta_horas_input_calc > 0

                THEN ROUND(

                    (
                        (
                            ev.distancia_km_calc
                            /
                            ev.delta_horas_input_calc
                        )
                        /
                        1.852
                    )::numeric,

                    2
                )

            END AS velocidade_knots,


            CASE

                WHEN ev.data_reportada IS NOT NULL

                THEN
                    ev.data_consulta
                    -
                    ev.data_reportada

            END AS delta_coleta_reportada,


            ev.id_ativo,

            ROUND(
                ev.distancia_ativo_km::numeric,
                3
            ),

            ev.evidencia_ativo_calc,


            ev.id_campo,


            ev.id_local,

            ROUND(
                ev.distancia_local_km::numeric,
                3
            ),

            ev.evidencia_local_calc,


            CASE

                -- Ativo possui evidência e é mais próximo
                -- que o local fixo.

                WHEN
                    COALESCE(
                        ev.evidencia_ativo_calc,
                        0
                    ) > 0

                    AND (

                        COALESCE(
                            ev.evidencia_local_calc,
                            0
                        ) = 0

                        OR

                        ev.distancia_ativo_km
                        <=
                        ev.distancia_local_km
                    )

                THEN 'PROXIMO_ATIVO'


                -- Local fixo possui evidência.

                WHEN
                    COALESCE(
                        ev.evidencia_local_calc,
                        0
                    ) > 0

                THEN

                    CASE

                        WHEN UPPER(ev.tipo_local) = 'PORTO'
                            THEN 'PORTO'

                        WHEN UPPER(ev.tipo_local) = 'ESTALEIRO'
                            THEN 'ESTALEIRO'

                        WHEN UPPER(ev.tipo_local) = 'FUNDEIO'
                            THEN 'FUNDEIO'

                        ELSE 'LOCAL_FIXO'

                    END


                ELSE 'EM_TRANSITO'

            END AS contexto_operacional,


            GREATEST(

                COALESCE(
                    ev.evidencia_ativo_calc,
                    0
                ),

                COALESCE(
                    ev.evidencia_local_calc,
                    0
                )

            ) AS evidencia_proximidade,


            CURRENT_TIMESTAMP

        FROM evidencias ev


        ON CONFLICT (
            id_empresa,
            id_posicao_origem
        )
        DO NOTHING

    """)

    resultado = conn.execute(
        sql,
        {"id_empresa": id_empresa}
    )

    inseridos = resultado.rowcount

    total_depois = contar_analytics_empresa(
        conn,
        id_empresa
    )

    print(f"Novos registros inseridos:     {inseridos}")
    print(f"Total analytics da empresa:    {total_depois}")

    return inseridos


# ============================================================
# EXECUÇÃO
# ============================================================

def main():

    print("=" * 70)
    print("POSIÇÕES ENRIQUECIDAS — CARGA INCREMENTAL")
    print("=" * 70)

    total_inseridos = 0

    try:

        with engine.begin() as conn:

            print()
            print("Conexão com PostgreSQL estabelecida.")

            for empresa, tabela_raw in EMPRESAS.items():

                inseridos = processar_empresa(
                    conn,
                    empresa,
                    tabela_raw
                )

                total_inseridos += inseridos


        print()
        print("=" * 70)
        print("RESULTADO")
        print("=" * 70)

        print(
            f"Total de novos registros inseridos: "
            f"{total_inseridos}"
        )

        print()
        print("Carga concluída com sucesso.")

    except Exception:

        print()
        print("A carga falhou.")
        print(
            "Nenhuma alteração desta execução "
            "foi confirmada no banco."
        )

        raise


if __name__ == "__main__":
    main()