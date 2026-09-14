from pathlib import Path
import os
import re
import unicodedata

import pandas as pd
import plotly.express as px

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE = Path(__file__).resolve().parents[1]

load_dotenv(BASE / ".env")

FUNDO = "#0B1F3A"
BRANCO = "#FFFFFF"


# ============================================================
# PERÍODO DA ANÁLISE
# ============================================================

DATA_INICIO = "2026-07-16"
DATA_FIM = "2026-09-13"

data_inicio = pd.to_datetime(DATA_INICIO)

# DATA_FIM inclusiva
data_fim = (
    pd.to_datetime(DATA_FIM)
    + pd.Timedelta(days=1)
    - pd.Timedelta(seconds=1)
)


# ============================================================
# CONEXÃO POSTGRESQL
# ============================================================

engine = create_engine(
    (
        f"postgresql+psycopg2://"
        f"{os.getenv('OFI_DB_USER')}:"
        f"{os.getenv('OFI_DB_PASSWORD')}@"
        f"{os.getenv('OFI_DB_HOST')}:"
        f"{os.getenv('OFI_DB_PORT')}/"
        f"{os.getenv('OFI_DB_NAME')}"
    ),
    pool_pre_ping=True
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_nome(nome):
    """
    Converte o nome para formato seguro para arquivo HTML.
    Exemplo:
        CBO IPANEMA -> cbo_ipanema
    """

    nome = str(nome).lower().strip()

    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(
        c for c in nome
        if not unicodedata.combining(c)
    )

    nome = re.sub(r"[^a-z0-9]+", "_", nome)

    return nome.strip("_")


# ============================================================
# CONSULTA
# ============================================================

sql = text("""
    SELECT
        p.empresa,
        p.id_embarcacao,
        e.nome_embarcacao,
        p.data_consulta,
        p.nome_ativo,
        p.id_campo,
        p.nome_campo,
        p.menor_distancia_km,
        p.evidencia_proximidade,
        p.classificacao_operacional

    FROM analytics.v_posicoes_classificadas p

    JOIN core.embarcacoes e
        ON e.id_embarcacao = p.id_embarcacao

    WHERE
        p.data_consulta >= :data_inicio
        AND p.data_consulta <= :data_fim

        AND p.classificacao_operacional = 'ATENDIMENTO_OFFSHORE'

        AND p.nome_campo IS NOT NULL

    ORDER BY
        p.empresa,
        e.nome_embarcacao,
        p.data_consulta;
""")


# ============================================================
# CARREGAMENTO
# ============================================================

print("=" * 70)
print("CAMPO DE ATENDIMENTO — OFI")
print("=" * 70)

print(
    f"\nPeríodo da análise: "
    f"{data_inicio.strftime('%Y-%m-%d')} "
    f"a "
    f"{data_fim.strftime('%Y-%m-%d')}"
)

with engine.connect() as conn:

    df = pd.read_sql(
        sql,
        conn,
        params={
            "data_inicio": data_inicio,
            "data_fim": data_fim
        }
    )


print(f"\nRegistros de atendimento encontrados: {len(df)}")


if df.empty:
    print(
        "\nNenhum atendimento offshore foi identificado "
        "no período selecionado."
    )

    engine.dispose()
    raise SystemExit


# ============================================================
# GERA GRÁFICO POR EMBARCAÇÃO
# ============================================================

for (empresa, id_embarcacao, nome_embarcacao), grupo in df.groupby(
    [
        "empresa",
        "id_embarcacao",
        "nome_embarcacao"
    ]
):

    print()
    print("-" * 70)
    print(f"Empresa: {empresa}")
    print(f"Embarcação: {nome_embarcacao}")
    print(f"Registros de atendimento: {len(grupo)}")


    # ========================================================
    # CONTAGEM POR CAMPO
    # ========================================================

    atendimento = (
        grupo["nome_campo"]
        .dropna()
        .value_counts()
        .reset_index()
    )

    atendimento.columns = [
        "campo",
        "registros"
    ]


    if atendimento.empty:

        print(
            "Nenhum campo identificado para esta embarcação."
        )

        continue


    # ========================================================
    # GRÁFICO DONUT
    # ========================================================

    fig = px.pie(
        atendimento,
        values="registros",
        names="campo",
        hole=0.60
    )


    fig.update_traces(

        textposition="inside",

        textinfo="percent",

        textfont=dict(
            color=BRANCO,
            size=14
        ),

        hovertemplate=(
            "<b>%{label}</b><br>"
            "Registros de atendimento: %{value}<br>"
            "Percentual: %{percent}"
            "<extra></extra>"
        )
    )


    fig.update_layout(

        paper_bgcolor=FUNDO,

        plot_bgcolor=FUNDO,

        font=dict(
            color=BRANCO,
            family="Arial"
        ),

        showlegend=True,

        title=dict(

            text=(
                f"Atendimento<br>"
                f"<b>{nome_embarcacao}</b><br>"
                f"<sup>"
                f"{data_inicio.strftime('%d/%m/%Y')} "
                f"a "
                f"{pd.to_datetime(DATA_FIM).strftime('%d/%m/%Y')}"
                f"</sup>"
            ),

            x=0.5,
            xanchor="center",

            y=0.95,
            yanchor="top",

            font=dict(
                color=BRANCO,
                size=18
            )
        ),

        legend=dict(

            orientation="h",

            yanchor="top",
            y=-0.10,

            xanchor="center",
            x=0.5,

            font=dict(
                color=BRANCO,
                size=12
            )
        ),

        margin=dict(
            t=100,
            b=100,
            l=20,
            r=20
        )
    )


    # ========================================================
    # SAÍDA
    # ========================================================

    empresa_pasta = normalizar_nome(empresa)

    nome_arquivo = normalizar_nome(
        nome_embarcacao
    )

    pasta_saida = (
        BASE
        / "graficos"
        / "campo_atendimento"
        / empresa_pasta
    )

    pasta_saida.mkdir(
        parents=True,
        exist_ok=True
    )


    arquivo_saida = (
        pasta_saida
        / f"{nome_arquivo}.html"
    )


    fig.write_html(
        arquivo_saida,
        include_plotlyjs="cdn",
        full_html=False
    )


    print(
        f"Gráfico salvo: {arquivo_saida}"
    )


# ============================================================
# FINALIZAÇÃO
# ============================================================

engine.dispose()

print()
print("=" * 70)
print("GRÁFICOS DE CAMPO DE ATENDIMENTO GERADOS COM SUCESSO")
print("=" * 70)