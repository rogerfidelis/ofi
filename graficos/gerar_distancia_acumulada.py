import os
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# CONFIGURAÇÃO
# ============================================================

# Este script deve estar na pasta "graficos" do projeto.
BASE = Path(__file__).resolve().parents[1]

load_dotenv(BASE / ".env")

EMPRESAS = ["bram", "starnav", "cbo"]

DATA_INICIO = "2026-07-16"
DATA_FIM = "2026-09-13"  # Inclui o dia inteiro.

FUNDO = "#0B1F3A"
BRANCO = "#FFFFFF"

RAIO_TERRA_KM = 6371.0088

PASTA_SAIDA = BASE / "graficos" / "distancia_acumulada"

# Mapeamento explícito das tabelas disponíveis.
TABELAS = {
    "bram": "raw.posicoes_bram",
    "starnav": "raw.posicoes_starnav",
    "cbo": "raw.posicoes_cbo",
}


# ============================================================
# CONEXÃO COM O BANCO
# ============================================================

def criar_engine():
    """
    Utiliza DATABASE_URL, se disponível.

    Caso contrário, utiliza:
        OFI_DB_HOST
        OFI_DB_PORT
        OFI_DB_NAME
        OFI_DB_USER
        OFI_DB_PASSWORD

    OFI_DB_SSLMODE é opcional.
    Para o Aiven, configure como require.
    """
    database_url = os.getenv("DATABASE_URL")

    sslmode = os.getenv("OFI_DB_SSLMODE")
    connect_args = {"connect_timeout": 20}

    if sslmode:
        connect_args["sslmode"] = sslmode

    if database_url:
        # Compatibilidade com URLs que começam com postgres://.
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql://",
                1,
            )

        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

    obrigatorias = [
        "OFI_DB_HOST",
        "OFI_DB_NAME",
        "OFI_DB_USER",
        "OFI_DB_PASSWORD",
    ]

    ausentes = [
        nome for nome in obrigatorias
        if not os.getenv(nome)
    ]

    if ausentes:
        raise ValueError(
            "Configure DATABASE_URL ou as variáveis ausentes no .env: "
            + ", ".join(ausentes)
        )

    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.getenv("OFI_DB_USER"),
        password=os.getenv("OFI_DB_PASSWORD"),
        host=os.getenv("OFI_DB_HOST"),
        port=int(os.getenv("OFI_DB_PORT", "5432")),
        database=os.getenv("OFI_DB_NAME"),
    )

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


# ============================================================
# CONSULTA DAS POSIÇÕES
# ============================================================

def carregar_posicoes(engine, empresa, inicio, fim_exclusivo):
    tabela = TABELAS[empresa]

    sql = text(
        f"""
        SELECT
            p.id_posicao,
            p.id_embarcacao,
            e.nome_embarcacao,
            p.data_consulta,
            p.data_reportada,
            p.latitude,
            p.longitude
        FROM {tabela} AS p
        JOIN core.embarcacoes AS e
            ON e.id_embarcacao = p.id_embarcacao
        WHERE p.data_reportada >= :inicio
          AND p.data_reportada < :fim_exclusivo
        ORDER BY
            p.id_embarcacao,
            p.data_reportada,
            p.data_consulta,
            p.id_posicao
        """
    )

    with engine.connect() as conexao:
        return pd.read_sql_query(
            sql,
            conexao,
            params={
                "inicio": inicio.to_pydatetime(),
                "fim_exclusivo": fim_exclusivo.to_pydatetime(),
            },
        )


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

def preparar_posicoes(df):
    df = df.copy()

    for coluna in ["data_consulta", "data_reportada"]:
        df[coluna] = pd.to_datetime(
            df[coluna],
            errors="coerce",
        )

    for coluna in ["latitude", "longitude"]:
        df[coluna] = pd.to_numeric(
            df[coluna],
            errors="coerce",
        )

    validos = (
        df["data_reportada"].notna()
        & df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    )

    invalidos = int((~validos).sum())
    df = df.loc[validos].copy()

    # Para um mesmo horário reportado, utiliza o registro
    # válido da consulta mais recente.
    # id_posicao funciona como desempate.
    df = df.sort_values(
        ["data_reportada", "data_consulta", "id_posicao"],
        na_position="first",
    )

    antes = len(df)

    df = df.drop_duplicates(
        subset=["id_embarcacao", "data_reportada"],
        keep="last",
    )

    repetidos = antes - len(df)

    df = df.sort_values(
        "data_reportada"
    ).reset_index(drop=True)

    return df, invalidos, repetidos


# ============================================================
# CÁLCULO DA DISTÂNCIA
# ============================================================

def calcular_distancias(df):
    df = df.copy()

    latitudes = np.radians(
        df["latitude"].to_numpy(dtype=float)
    )

    longitudes = np.radians(
        df["longitude"].to_numpy(dtype=float)
    )

    distancias = np.zeros(len(df), dtype=float)

    if len(df) > 1:
        delta_lat = np.diff(latitudes)
        delta_lon = np.diff(longitudes)

        a = (
            np.sin(delta_lat / 2) ** 2
            + np.cos(latitudes[:-1])
            * np.cos(latitudes[1:])
            * np.sin(delta_lon / 2) ** 2
        )

        # Proteção contra pequenas imprecisões numéricas.
        a = np.clip(a, 0.0, 1.0)

        distancias[1:] = (
            2
            * RAIO_TERRA_KM
            * np.arcsin(np.sqrt(a))
        )

    df["distancia_km"] = distancias

    df["distancia_acumulada_km"] = (
        df["distancia_km"].cumsum()
    )

    return df


# ============================================================
# NOME DOS ARQUIVOS
# ============================================================

def nome_arquivo(nome):
    nome = unicodedata.normalize("NFKD", str(nome))

    nome = (
        nome.encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )

    nome = re.sub(r"[^a-z0-9]+", "_", nome).strip("_")

    return nome or "embarcacao"


# ============================================================
# GRÁFICO
# ============================================================

def gerar_grafico(df, nome_embarcacao, destino):
    total = float(df["distancia_acumulada_km"].iloc[-1])

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["data_reportada"],
            y=df["distancia_acumulada_km"],
            customdata=df[["distancia_km"]].to_numpy(),
            mode="lines+markers",
            name="Distância acumulada",
            line=dict(
                color=BRANCO,
                width=2,
            ),
            marker=dict(
                color=BRANCO,
                size=5,
            ),
            hovertemplate=(
                "<b>Data reportada:</b> %{x|%d/%m/%Y %H:%M}"
                "<br>"
                "<b>Distância do trecho:</b> "
                "%{customdata[0]:,.2f} km"
                "<br>"
                "<b>Distância acumulada:</b> %{y:,.2f} km"
                "<extra></extra>"
            ),
        )
    )

    fig.update_xaxes(
        title=dict(
            text="Data reportada",
            font=dict(color=BRANCO),
        ),
        tickformat="%d/%m/%Y",
        tickangle=90,
        tickfont=dict(color=BRANCO),
        linecolor=BRANCO,
        gridcolor="rgba(255,255,255,0.15)",
        zerolinecolor="rgba(255,255,255,0.2)",
        automargin=True,
    )

    fig.update_yaxes(
        title=dict(
            text="Distância acumulada (km)",
            font=dict(color=BRANCO),
        ),
        tickfont=dict(color=BRANCO),
        linecolor=BRANCO,
        gridcolor="rgba(255,255,255,0.15)",
        zerolinecolor="rgba(255,255,255,0.2)",
        rangemode="tozero",
        automargin=True,
    )

    fig.update_layout(
        paper_bgcolor=FUNDO,
        plot_bgcolor=FUNDO,
        font=dict(
            color=BRANCO,
            family="Arial",
        ),
        title=dict(
            text=(
                f"Distância acumulada — {nome_embarcacao}"
                "<br>"
                f"<sup>Total estimado: {total:,.2f} km</sup>"
            ),
            font=dict(
                color=BRANCO,
                size=20,
            ),
            x=0.5,
            xanchor="center",
        ),
        showlegend=False,
        autosize=True,
        margin=dict(
            l=70,
            r=25,
            t=90,
            b=80,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=FUNDO,
            font=dict(color=BRANCO),
            bordercolor=BRANCO,
        ),
    )

    config = {
        "responsive": True,
        "displayModeBar": True,
        "displaylogo": False,
    }

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.write_html(
        destino,
        # Inclui o Plotly no HTML para funcionar sem internet.
        include_plotlyjs=True,
        full_html=True,
        config=config,
        default_width="100%",
        default_height="100vh",
    )


# ============================================================
# EXECUÇÃO
# ============================================================

def main():
    inicio = pd.Timestamp(DATA_INICIO).normalize()
    fim = pd.Timestamp(DATA_FIM).normalize()

    if fim < inicio:
        raise ValueError(
            "DATA_FIM deve ser igual ou posterior a DATA_INICIO."
        )

    fim_exclusivo = fim + pd.Timedelta(days=1)

    engine = criar_engine()

    total_graficos = 0
    falhas = []

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))

        print("=" * 70)
        print("CONEXÃO COM POSTGRESQL REALIZADA COM SUCESSO")
        print("=" * 70)

        print(
            f"\nPeríodo: {inicio:%d/%m/%Y} "
            f"a {fim:%d/%m/%Y}"
        )
        print("Referência temporal: data_reportada")

        for empresa in EMPRESAS:
            print("\n" + "=" * 70)
            print(f"EMPRESA: {empresa.upper()}")
            print("=" * 70)

            try:
                dados = carregar_posicoes(
                    engine,
                    empresa,
                    inicio,
                    fim_exclusivo,
                )

                if dados.empty:
                    print("Nenhuma posição encontrada no período.")
                    continue

                grupos = dados.groupby(
                    "id_embarcacao",
                    sort=True,
                )

                # Evita sobrescrever arquivos se nomes diferentes
                # resultarem no mesmo nome normalizado.
                nomes_usados = set()

                for id_embarcacao, bruto in grupos:
                    nome = str(
                        bruto["nome_embarcacao"].iloc[0]
                    )

                    df, invalidos, repetidos = preparar_posicoes(
                        bruto
                    )

                    print(f"\nEmbarcação: {nome}")
                    print(f"Registros consultados: {len(bruto)}")
                    print(f"Registros inválidos: {invalidos}")
                    print(f"Horários repetidos removidos: {repetidos}")
                    print(f"Posições utilizadas: {len(df)}")

                    if df.empty:
                        print("Ignorada: nenhuma posição válida.")
                        continue

                    df = calcular_distancias(df)

                    if len(df) == 1:
                        print(
                            "Apenas uma posição: distância zero; "
                            "não há trecho para calcular."
                        )

                    slug = nome_arquivo(nome)

                    if slug in nomes_usados:
                        slug = f"{slug}_{id_embarcacao}"

                    nomes_usados.add(slug)

                    destino = (
                        PASTA_SAIDA
                        / empresa
                        / f"{slug}.html"
                    )

                    gerar_grafico(df, nome, destino)

                    total = df["distancia_acumulada_km"].iloc[-1]

                    print(f"Distância estimada: {total:,.2f} km")
                    print(f"Gráfico salvo: {destino}")

                    total_graficos += 1

            except Exception as erro:
                falhas.append(empresa)
                print(
                    f"ERRO AO PROCESSAR {empresa.upper()}: "
                    f"{erro}"
                )

    finally:
        engine.dispose()

    print("\n" + "=" * 70)
    print(f"GRÁFICOS GERADOS: {total_graficos}")

    if falhas:
        print("Empresas com falha: " + ", ".join(falhas))

    print("=" * 70)

    if falhas:
        raise SystemExit(1)


if __name__ == "__main__":
    main()