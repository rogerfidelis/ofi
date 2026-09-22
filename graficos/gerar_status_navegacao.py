from pathlib import Path
import os
import unicodedata

import pandas as pd
import plotly.express as px

from sqlalchemy import create_engine, text
from dotenv import load_dotenv


# ============================================================
# CAMINHOS DO PROJETO
# ============================================================

BASE = Path(__file__).resolve().parents[1]

load_dotenv(BASE / ".env")


# ============================================================
# CONFIGURAÇÃO DO BANCO
# ============================================================

DB_HOST = os.getenv("OFI_DB_HOST", "localhost")
DB_PORT = os.getenv("OFI_DB_PORT", "5432")
DB_NAME = os.getenv("OFI_DB_NAME", "ofi")
DB_USER = os.getenv("OFI_DB_USER", "postgres")
DB_PASSWORD = os.getenv("OFI_DB_PASSWORD")


if not DB_PASSWORD:
    raise ValueError(
        "OFI_DB_PASSWORD não foi encontrada no arquivo .env."
    )


DATABASE_URL = (
    f"postgresql+psycopg://"
    f"{DB_USER}:{DB_PASSWORD}@"
    f"{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ============================================================
# PERÍODO DA ANÁLISE
# ============================================================

DATA_INICIO = "2026-08-01"
DATA_FIM = "2026-09-22"


DATA_INICIO = pd.to_datetime(DATA_INICIO)

# Soma 1 dia para incluir todo o DATA_FIM
DATA_FIM_EXCLUSIVA = (
    pd.to_datetime(DATA_FIM)
    + pd.Timedelta(days=1)
)


# ============================================================
# EMPRESAS
# ============================================================

EMPRESAS = [
    "BRAM",
    "CBO",
    "STARNAV"
]


# ============================================================
# CONFIGURAÇÕES VISUAIS
# ============================================================

FUNDO = "#0B1F3A"
TEXTO = "#FFFFFF"


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_nome_arquivo(nome):
    """
    Normaliza o nome da embarcação para ser utilizado
    como nome de arquivo HTML.
    """

    nome = unicodedata.normalize(
        "NFKD",
        str(nome)
    )

    nome = "".join(
        caractere
        for caractere in nome
        if not unicodedata.combining(caractere)
    )

    nome = (
        nome.lower()
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    return nome


# ============================================================
# TESTE DE CONEXÃO
# ============================================================

def testar_conexao():

    try:

        with engine.connect() as conexao:

            conexao.execute(
                text("SELECT 1")
            )

        print("=" * 70)
        print("CONEXÃO COM POSTGRESQL REALIZADA COM SUCESSO")
        print("=" * 70)

    except Exception as erro:

        print("\nERRO DE CONEXÃO COM O POSTGRESQL")
        print(erro)

        raise


# ============================================================
# BUSCA ID DA EMPRESA
# ============================================================

def buscar_id_empresa(nome_empresa):

    query = text(
        """
        SELECT
            id_empresa
        FROM core.empresas
        WHERE UPPER(TRIM(nome_empresa)) = :empresa;
        """
    )

    df = pd.read_sql(
        query,
        engine,
        params={
            "empresa": nome_empresa.upper()
        }
    )

    if df.empty:

        raise ValueError(
            f"Empresa '{nome_empresa}' "
            f"não encontrada em core.empresas."
        )

    return int(
        df.iloc[0]["id_empresa"]
    )


# ============================================================
# BUSCA POSIÇÕES ENRIQUECIDAS DA EMPRESA
# ============================================================

def buscar_dados_empresa(
    id_empresa
):
    """
    Busca todas as posições enriquecidas das embarcações
    de uma empresa dentro do período selecionado.
    """

    query = text(
        """
        SELECT
            pe.id_embarcacao,
            e.nome_embarcacao,
            pe.id_empresa,
            pe.data_consulta,
            pe.data_reportada,
            pe.status_navegacao,
            pe.contexto_operacional,
            pe.id_ativo_proximo,
            pe.id_campo,
            pe.id_local_proximo,
            pe.evidencia_proximidade
        FROM analytics.posicoes_enriquecidas pe

        INNER JOIN core.embarcacoes e
            ON e.id_embarcacao = pe.id_embarcacao

        WHERE pe.id_empresa = :id_empresa
          AND pe.data_consulta >= :data_inicio
          AND pe.data_consulta < :data_fim

        ORDER BY
            e.nome_embarcacao,
            pe.data_consulta;
        """
    )


    return pd.read_sql(
        query,
        engine,
        params={
            "id_empresa": id_empresa,
            "data_inicio": DATA_INICIO,
            "data_fim": DATA_FIM_EXCLUSIVA
        }
    )


# ============================================================
# TRATAMENTO DO STATUS
# ============================================================

def preparar_status(df):
    """
    Remove registros sem status válido e padroniza
    espaços em branco.
    """

    df = df.copy()


    df["status_navegacao"] = (
        df["status_navegacao"]
        .astype("string")
        .str.strip()
    )


    df = df[
        df["status_navegacao"].notna()
        &
        (df["status_navegacao"] != "")
    ].copy()


    return df


# ============================================================
# GERAÇÃO DO GRÁFICO
# ============================================================

def gerar_grafico(
    df,
    nome_embarcacao,
    arquivo_saida
):
    """
    Gera o gráfico de rosca com a distribuição
    dos status de navegação da embarcação.
    """

    df = preparar_status(
        df
    )


    if df.empty:

        print(
            "  Não existem registros "
            "de status válidos."
        )

        return False


    # --------------------------------------------------------
    # CONTAGEM DOS STATUS
    # --------------------------------------------------------

    contagem_status = (
        df["status_navegacao"]
        .value_counts()
        .rename_axis("status")
        .reset_index(name="quantidade")
    )


    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total_registros = (
        contagem_status["quantidade"]
        .sum()
    )


    contagem_status["percentual"] = (
        contagem_status["quantidade"]
        / total_registros
        * 100
    )


    # ========================================================
    # GRÁFICO DE ROSCA
    # ========================================================

    fig = px.pie(
        contagem_status,
        values="quantidade",
        names="status",
        hole=0.60,
        title=(
            "Status de Navegação"
            f"<br><b>{nome_embarcacao}</b>"
        )
    )


    # ========================================================
    # CONFIGURAÇÃO DA ROSCA
    # ========================================================

    fig.update_traces(

        # Apenas percentual dentro da rosca
        textposition="inside",

        textinfo="percent",

        textfont=dict(
            color=TEXTO,
            size=14
        ),

        # Hover
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Registros: %{value}<br>"
            "Percentual: %{percent:.1%}"
            "<extra></extra>"
        ),

        domain=dict(
            x=[0, 1],
            y=[0.30, 0.90]
        )
    )


    # ========================================================
    # LAYOUT
    # ========================================================

    fig.update_layout(

        paper_bgcolor=FUNDO,

        plot_bgcolor=FUNDO,

        font=dict(
            color=TEXTO,
            family="Arial"
        ),

        title=dict(
            x=0.5,
            xanchor="center",
            y=0.97,
            yanchor="top",

            font=dict(
                color=TEXTO,
                size=18
            )
        ),

        legend=dict(
            orientation="h",

            yanchor="top",
            y=0.22,

            xanchor="center",
            x=0.5,

            font=dict(
                color=TEXTO,
                size=12
            )
        ),

        margin=dict(
            l=20,
            r=20,
            t=70,
            b=20
        ),

        showlegend=True
    )


    # ========================================================
    # EXPORTAÇÃO
    # ========================================================

    fig.write_html(
        arquivo_saida,
        include_plotlyjs="cdn",
        full_html=False
    )


    return True


# ============================================================
# PROCESSAMENTO POR EMPRESA
# ============================================================

def processar_empresa(
    empresa
):

    print("\n" + "=" * 70)
    print(f"EMPRESA: {empresa}")
    print("=" * 70)


    # --------------------------------------------------------
    # IDENTIFICA ID DA EMPRESA
    # --------------------------------------------------------

    id_empresa = buscar_id_empresa(
        empresa
    )


    print(
        f"id_empresa: {id_empresa}"
    )


    # --------------------------------------------------------
    # BUSCA DADOS ANALÍTICOS
    # --------------------------------------------------------

    df_empresa = buscar_dados_empresa(
        id_empresa
    )


    if df_empresa.empty:

        print(
            "Nenhum registro encontrado "
            "no período selecionado."
        )

        return


    print(
        f"Registros encontrados: "
        f"{len(df_empresa)}"
    )


    # --------------------------------------------------------
    # EMBARCAÇÕES ENCONTRADAS
    # --------------------------------------------------------

    quantidade_embarcacoes = (
        df_empresa["id_embarcacao"]
        .nunique()
    )


    print(
        f"Embarcações encontradas: "
        f"{quantidade_embarcacoes}"
    )


    # --------------------------------------------------------
    # PASTA DE SAÍDA
    # --------------------------------------------------------

    pasta_saida = (
        BASE
        / "graficos"
        / "status_navegacao"
        / empresa.lower()
    )


    pasta_saida.mkdir(
        parents=True,
        exist_ok=True
    )


    graficos_gerados = 0


    # ========================================================
    # PROCESSAMENTO POR EMBARCAÇÃO
    # ========================================================

    grupos = df_empresa.groupby(
        [
            "id_embarcacao",
            "nome_embarcacao"
        ],
        sort=True
    )


    for (
        id_embarcacao,
        nome_embarcacao
    ), df_embarcacao in grupos:


        print(
            f"\nProcessando: "
            f"{nome_embarcacao} "
            f"(id={id_embarcacao})"
        )


        # ----------------------------------------------------
        # NOME DO ARQUIVO
        # ----------------------------------------------------

        nome_arquivo = (
            normalizar_nome_arquivo(
                nome_embarcacao
            )
        )


        arquivo_saida = (
            pasta_saida
            / f"{nome_arquivo}.html"
        )


        # ----------------------------------------------------
        # GERA GRÁFICO
        # ----------------------------------------------------

        sucesso = gerar_grafico(
            df=df_embarcacao,
            nome_embarcacao=nome_embarcacao,
            arquivo_saida=arquivo_saida
        )


        if sucesso:

            graficos_gerados += 1

            print(
                f"  Registros utilizados: "
                f"{len(df_embarcacao)}"
            )

            print(
                f"  Gráfico salvo: "
                f"{arquivo_saida}"
            )


    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    print(
        f"\n{graficos_gerados} gráficos "
        f"gerados para {empresa}."
    )


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():

    testar_conexao()


    print(
        f"\nPeríodo da análise: "
        f"{DATA_INICIO.date()} "
        f"a "
        f"{(DATA_FIM_EXCLUSIVA - pd.Timedelta(days=1)).date()}"
    )


    for empresa in EMPRESAS:

        try:

            processar_empresa(
                empresa
            )

        except Exception as erro:

            print(
                f"\nERRO AO PROCESSAR "
                f"{empresa}:"
            )

            print(erro)

            raise


    print("\n" + "=" * 70)
    print("GRÁFICOS DE STATUS DE NAVEGAÇÃO CONCLUÍDOS")
    print("=" * 70)


if __name__ == "__main__":

    main()