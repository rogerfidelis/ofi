from pathlib import Path
from urllib.parse import quote
import os
import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# ============================================================
# CAMINHOS
# ============================================================

# Considerando:
# projeto_ofi/
# ├── .env
# ├── graficos/
# │   └── gerar_gantt_atendimento.py

BASE = Path(__file__).resolve().parents[1]

load_dotenv(BASE / ".env")


# ============================================================
# CONFIGURAÇÕES
# ============================================================

EMPRESAS = ["BRAM", "CBO", "STARNAV"]

DATA_INICIO = "2026-07-16"
DATA_FIM = "2026-09-13"

PASTA_SAIDA = BASE / "graficos" / "gantt_atendimento"

COR_FUNDO = "#0B1F3A"
COR_TEXTO = "#FFFFFF"

CORES_TIPO = {
    "Parado": "#D4AF37",
    "Trânsito": "#1CA3EC",
}

CLASSIFICACOES_PARADO = {
    "ATENDIMENTO_OFFSHORE",
    "PORTO",
    "ESTALEIRO",
    "FUNDEIO",
    "PROXIMIDADE_LOCAL_FIXO",
}

DURACAO_MINIMA_MINUTOS = 30


# ============================================================
# CONEXÃO COM O POSTGRESQL
# ============================================================

def criar_engine():
    """
    Primeiro tenta utilizar DATABASE_URL.

    Caso DATABASE_URL não exista, monta a conexão usando:
        OFI_DB_HOST
        OFI_DB_PORT
        OFI_DB_NAME ou OFI_DB_DATABASE
        OFI_DB_USER
        OFI_DB_PASSWORD
        OFI_DB_SSLMODE
    """

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return create_engine(
            database_url,
            pool_pre_ping=True,
        )

    host = os.getenv("OFI_DB_HOST")
    port = os.getenv("OFI_DB_PORT", "5432")
    banco = (
        os.getenv("OFI_DB_NAME")
        or os.getenv("OFI_DB_DATABASE")
    )
    usuario = os.getenv("OFI_DB_USER")
    senha = os.getenv("OFI_DB_PASSWORD")
    sslmode = os.getenv("OFI_DB_SSLMODE", "prefer")

    variaveis_obrigatorias = {
        "OFI_DB_HOST": host,
        "OFI_DB_NAME ou OFI_DB_DATABASE": banco,
        "OFI_DB_USER": usuario,
        "OFI_DB_PASSWORD": senha,
    }

    ausentes = [
        nome
        for nome, valor in variaveis_obrigatorias.items()
        if not valor
    ]

    if ausentes:
        raise RuntimeError(
            "Variáveis de conexão ausentes no .env: "
            + ", ".join(ausentes)
        )

    usuario_url = quote(usuario, safe="")
    senha_url = quote(senha, safe="")

    url = (
        f"postgresql+psycopg2://"
        f"{usuario_url}:{senha_url}"
        f"@{host}:{port}/{banco}"
        f"?sslmode={sslmode}"
    )

    return create_engine(
        url,
        pool_pre_ping=True,
    )


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_nome_arquivo(nome):
    """
    Transforma o nome da embarcação em um nome seguro para HTML.
    """

    nome = unicodedata.normalize(
        "NFKD",
        str(nome),
    )

    nome = nome.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    nome = nome.strip().lower()

    nome = re.sub(
        r"[^a-z0-9]+",
        "_",
        nome,
    )

    return nome.strip("_")


def primeiro_valido(serie):
    """
    Retorna o primeiro valor não vazio de uma série.
    """

    serie = serie.dropna()

    for valor in serie:
        valor_texto = str(valor).strip()

        if valor_texto:
            return valor_texto

    return None


def juntar_valores(serie):
    """
    Junta valores únicos para apresentação no hover.
    """

    valores = []

    for valor in serie.dropna():
        valor_texto = str(valor).strip()

        if (
            valor_texto
            and valor_texto not in valores
        ):
            valores.append(valor_texto)

    if not valores:
        return None

    return ", ".join(valores)


def formatar_duracao(delta):
    total_segundos = max(
        int(delta.total_seconds()),
        0,
    )

    dias = total_segundos // 86400
    horas = (total_segundos % 86400) // 3600
    minutos = (total_segundos % 3600) // 60

    if dias > 0:
        return f"{dias}d {horas:02d}h {minutos:02d}min"

    return f"{horas}h {minutos:02d}min"


def obter_referencia(linha):
    """
    Define o nome do local ou ativo associado à posição.
    """

    tipo_referencia = str(
        linha.get("tipo_referencia", "")
    ).strip().upper()

    classificacao = str(
        linha.get("classificacao_operacional", "")
    ).strip().upper()

    if tipo_referencia == "ATIVO":
        nome_ativo = linha.get("nome_ativo")

        if pd.notna(nome_ativo):
            return str(nome_ativo).strip()

    if tipo_referencia == "LOCAL_FIXO":
        nome_local = linha.get("nome_local")

        if pd.notna(nome_local):
            return str(nome_local).strip()

    if classificacao in {
        "PORTO",
        "ESTALEIRO",
        "FUNDEIO",
        "PROXIMIDADE_LOCAL_FIXO",
    }:
        nome_local = linha.get("nome_local")

        if pd.notna(nome_local):
            return str(nome_local).strip()

    if classificacao == "ATENDIMENTO_OFFSHORE":
        nome_ativo = linha.get("nome_ativo")

        if pd.notna(nome_ativo):
            return str(nome_ativo).strip()

    return None


# ============================================================
# CONSULTA AO BANCO
# ============================================================

def consultar_posicoes(
    engine,
    empresa,
    data_inicio,
    data_fim,
):
    """
    Consulta as posições classificadas de uma empresa.

    A data final é inclusiva. Internamente, a consulta utiliza
    o primeiro instante do dia seguinte como limite exclusivo.
    """

    inicio = pd.Timestamp(data_inicio)
    fim_exclusivo = pd.Timestamp(data_fim) + pd.Timedelta(days=1)

    sql = text(
        """
        SELECT
            v.empresa,
            v.id_embarcacao,
            e.nome_embarcacao,
            v.data_consulta,
            v.data_reportada,
            v.latitude,
            v.longitude,
            v.status,
            v.tipo_referencia,
            v.id_ativo,
            v.nome_ativo,
            v.tipo_ativo,
            v.data_posicao_ativo,
            v.id_campo,
            v.nome_campo,
            v.id_local,
            v.nome_local,
            v.tipo_local,
            v.menor_distancia_km,
            v.evidencia_proximidade,
            v.classificacao_operacional
        FROM analytics.v_posicoes_classificadas AS v
        INNER JOIN core.embarcacoes AS e
            ON e.id_embarcacao = v.id_embarcacao
        WHERE UPPER(TRIM(v.empresa)) = :empresa
          AND v.data_reportada >= :data_inicio
          AND v.data_reportada < :data_fim_exclusivo
        ORDER BY
            v.id_embarcacao,
            v.data_reportada,
            v.evidencia_proximidade DESC NULLS LAST;
        """
    )

    parametros = {
        "empresa": empresa.upper(),
        "data_inicio": inicio.to_pydatetime(),
        "data_fim_exclusivo": fim_exclusivo.to_pydatetime(),
    }

    return pd.read_sql(
        sql,
        engine,
        params=parametros,
    )


# ============================================================
# PREPARAÇÃO DAS POSIÇÕES
# ============================================================

def preparar_posicoes(df):
    df = df.copy()

    df["data_reportada"] = pd.to_datetime(
        df["data_reportada"],
        errors="coerce",
    )

    df["evidencia_proximidade"] = pd.to_numeric(
        df["evidencia_proximidade"],
        errors="coerce",
    ).fillna(0)

    df["menor_distancia_km"] = pd.to_numeric(
        df["menor_distancia_km"],
        errors="coerce",
    )

    df["classificacao_operacional"] = (
        df["classificacao_operacional"]
        .fillna("TRANSITO")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df = df.dropna(
        subset=[
            "id_embarcacao",
            "nome_embarcacao",
            "data_reportada",
        ]
    )

    # Quando existem várias classificações no mesmo instante,
    # prioriza a linha com maior evidência de proximidade.
    df = (
        df.sort_values(
            [
                "id_embarcacao",
                "data_reportada",
                "evidencia_proximidade",
            ],
            ascending=[True, True, False],
        )
        .drop_duplicates(
            subset=[
                "id_embarcacao",
                "data_reportada",
            ],
            keep="first",
        )
        .sort_values(
            [
                "id_embarcacao",
                "data_reportada",
            ]
        )
        .reset_index(drop=True)
    )

    df["Referencia"] = df.apply(
        obter_referencia,
        axis=1,
    )

    df["Tipo"] = np.where(
        df["classificacao_operacional"].isin(
            CLASSIFICACOES_PARADO
        ),
        "Parado",
        "Trânsito",
    )

    # Um registro só pode ser considerado parado quando existe
    # uma referência identificada.
    sem_referencia = (
        df["Tipo"].eq("Parado")
        & df["Referencia"].isna()
    )

    df.loc[sem_referencia, "Tipo"] = "Trânsito"

    df.loc[
        df["Tipo"].eq("Trânsito"),
        "Referencia",
    ] = "TRANSITO"

    return df


# ============================================================
# CONSTRUÇÃO DOS EVENTOS
# ============================================================

def construir_eventos(df_embarcacao):
    df = (
        df_embarcacao
        .sort_values("data_reportada")
        .reset_index(drop=True)
        .copy()
    )

    if df.empty:
        return pd.DataFrame()

    # Inicia um novo grupo quando muda o tipo ou a referência.
    mudou_tipo = df["Tipo"].ne(
        df["Tipo"].shift()
    )

    mudou_referencia = df["Referencia"].ne(
        df["Referencia"].shift()
    )

    df["grupo_evento"] = (
        mudou_tipo | mudou_referencia
    ).cumsum()

    eventos = []

    for _, grupo in df.groupby(
        "grupo_evento",
        sort=True,
    ):
        tipo = grupo["Tipo"].iloc[0]
        referencia = grupo["Referencia"].iloc[0]

        evento = {
            "Inicio": grupo["data_reportada"].min(),
            "Ultima_observacao": grupo["data_reportada"].max(),
            "Tipo": tipo,
            "Referencia": referencia,
            "Classificacao": juntar_valores(
                grupo["classificacao_operacional"]
            ),
            "Status": juntar_valores(
                grupo["status"]
            ),
            "Ativo": juntar_valores(
                grupo["nome_ativo"]
            ),
            "Tipo_ativo": juntar_valores(
                grupo["tipo_ativo"]
            ),
            "Campo": juntar_valores(
                grupo["nome_campo"]
            ),
            "Local": juntar_valores(
                grupo["nome_local"]
            ),
            "Tipo_local": juntar_valores(
                grupo["tipo_local"]
            ),
            "Distancia_min_km": grupo[
                "menor_distancia_km"
            ].min(),
            "Distancia_max_km": grupo[
                "menor_distancia_km"
            ].max(),
            "Evidencia_maxima": grupo[
                "evidencia_proximidade"
            ].max(),
            "Quantidade_posicoes": len(grupo),
        }

        eventos.append(evento)

    df_eventos = pd.DataFrame(eventos)

    # O fim de cada evento coincide com o início do evento seguinte.
    df_eventos["Fim"] = df_eventos[
        "Inicio"
    ].shift(-1)

    # Para o último evento, utiliza a última observação disponível.
    indice_final = df_eventos.index[-1]

    fim_final = df_eventos.loc[
        indice_final,
        "Ultima_observacao",
    ]

    inicio_final = df_eventos.loc[
        indice_final,
        "Inicio",
    ]

    if fim_final <= inicio_final:
        fim_final = (
            inicio_final
            + pd.Timedelta(
                minutes=DURACAO_MINIMA_MINUTOS
            )
        )

    df_eventos.loc[
        indice_final,
        "Fim",
    ] = fim_final

    # Impede barras com duração igual a zero.
    duracao_invalida = (
        df_eventos["Fim"]
        <= df_eventos["Inicio"]
    )

    df_eventos.loc[
        duracao_invalida,
        "Fim",
    ] = (
        df_eventos.loc[
            duracao_invalida,
            "Inicio",
        ]
        + pd.Timedelta(
            minutes=DURACAO_MINIMA_MINUTOS
        )
    )

    # --------------------------------------------------------
    # NOMEIA OS EVENTOS DE TRÂNSITO
    # --------------------------------------------------------

    referencias_paradas = (
        df_eventos["Referencia"]
        .where(
            df_eventos["Tipo"].eq("Parado")
        )
    )

    referencia_anterior = (
        referencias_paradas
        .ffill()
        .shift()
    )

    proxima_referencia = (
        referencias_paradas
        .bfill()
        .shift(-1)
    )

    atividades = []

    for indice, evento in df_eventos.iterrows():
        if evento["Tipo"] == "Parado":
            atividade = evento["Referencia"]

        else:
            origem = referencia_anterior.loc[indice]
            destino = proxima_referencia.loc[indice]

            if pd.isna(origem):
                origem = "ORIGEM NÃO IDENTIFICADA"

            if pd.isna(destino):
                destino = "DESTINO NÃO IDENTIFICADO"

            atividade = f"{origem} → {destino}"

        atividades.append(atividade)

    df_eventos["Atividade"] = atividades

    # Remove trânsitos repetidos consecutivos com o mesmo nome.
    mudou_evento = (
        df_eventos["Tipo"].ne(
            df_eventos["Tipo"].shift()
        )
        | df_eventos["Atividade"].ne(
            df_eventos["Atividade"].shift()
        )
    )

    df_eventos["grupo_final"] = mudou_evento.cumsum()

    df_eventos = (
        df_eventos.groupby(
            "grupo_final",
            as_index=False,
        )
        .agg(
            Inicio=("Inicio", "min"),
            Fim=("Fim", "max"),
            Tipo=("Tipo", "first"),
            Atividade=("Atividade", "first"),
            Classificacao=("Classificacao", primeiro_valido),
            Status=("Status", primeiro_valido),
            Ativo=("Ativo", primeiro_valido),
            Tipo_ativo=("Tipo_ativo", primeiro_valido),
            Campo=("Campo", primeiro_valido),
            Local=("Local", primeiro_valido),
            Tipo_local=("Tipo_local", primeiro_valido),
            Distancia_min_km=("Distancia_min_km", "min"),
            Distancia_max_km=("Distancia_max_km", "max"),
            Evidencia_maxima=("Evidencia_maxima", "max"),
            Quantidade_posicoes=("Quantidade_posicoes", "sum"),
        )
    )

    df_eventos["Duracao"] = (
        df_eventos["Fim"]
        - df_eventos["Inicio"]
    )

    df_eventos["Duracao_display"] = (
        df_eventos["Duracao"]
        .apply(formatar_duracao)
    )

    df_eventos["id_evento"] = np.arange(
        len(df_eventos)
    )

    df_eventos["Atividade_Y"] = (
        df_eventos["id_evento"].astype(str)
        + " - "
        + df_eventos["Atividade"]
    )

    return df_eventos


# ============================================================
# CRIAÇÃO DO GRÁFICO
# ============================================================

def criar_gantt(
    df_gantt,
    empresa,
    nome_embarcacao,
):
    ordem_eventos = df_gantt[
        "Atividade_Y"
    ].tolist()

    fig = px.timeline(
        df_gantt,
        x_start="Inicio",
        x_end="Fim",
        y="Atividade_Y",
        color="Tipo",
        color_discrete_map=CORES_TIPO,
        category_orders={
            "Atividade_Y": ordem_eventos,
            "Tipo": ["Parado", "Trânsito"],
        },
        hover_data={
            "Atividade_Y": False,
            "Atividade": True,
            "Tipo": True,
            "Classificacao": True,
            "Inicio": True,
            "Fim": True,
            "Duracao_display": True,
            "Status": True,
            "Ativo": True,
            "Tipo_ativo": True,
            "Campo": True,
            "Local": True,
            "Tipo_local": True,
            "Distancia_min_km": ":.2f",
            "Distancia_max_km": ":.2f",
            "Evidencia_maxima": ":.2f",
            "Quantidade_posicoes": True,
        },
    )

    fig.update_traces(
        marker_line_color=COR_FUNDO,
        marker_line_width=1,
    )

    fig.update_xaxes(
        title_text="Data / Hora",
        title_font={
            "size": 18,
            "color": COR_TEXTO,
        },
        tickfont={
            "size": 13,
            "color": COR_TEXTO,
        },
        tickformat="%d/%m %H:%M",
        dtick=6 * 60 * 60 * 1000,
        tickangle=90,
        automargin=True,
        color=COR_TEXTO,
        gridcolor="rgba(255,255,255,0.15)",
        zerolinecolor="rgba(255,255,255,0.20)",
    )

    fig.update_yaxes(
        title_text="Atividade",
        title_font={
            "size": 18,
            "color": COR_TEXTO,
        },
        tickfont={
            "size": 14,
            "color": COR_TEXTO,
        },
        automargin=True,
        autorange="reversed",
        color=COR_TEXTO,
        gridcolor="rgba(255,255,255,0.08)",
        zerolinecolor="rgba(255,255,255,0.15)",
    )

    altura_gantt = max(
        500,
        len(df_gantt) * 70 + 250,
    )

    fig.update_layout(
        autosize=True,
        height=altura_gantt,
        paper_bgcolor=COR_FUNDO,
        plot_bgcolor=COR_FUNDO,
        margin={
            "l": 300,
            "r": 50,
            "t": 120,
            "b": 140,
        },
        font={
            "size": 16,
            "family": "Arial",
            "color": COR_TEXTO,
        },
        title={
            "text": (
                "<b>Atendimento Offshore</b><br>"
                f"<span style='font-size:16px'>"
                f"{nome_embarcacao}</span><br>"
                f"<span style='font-size:12px'>"
                f"{empresa} · "
                f"{pd.Timestamp(DATA_INICIO):%d/%m/%Y} a "
                f"{pd.Timestamp(DATA_FIM):%d/%m/%Y}"
                f"</span>"
            ),
            "font": {
                "size": 22,
                "color": COR_TEXTO,
            },
            "x": 0.5,
            "xanchor": "center",
        },
        legend={
            "title": {
                "text": "Tipo de atendimento",
                "font": {
                    "size": 14,
                    "color": COR_TEXTO,
                },
            },
            "font": {
                "size": 13,
                "color": COR_TEXTO,
            },
            "bgcolor": "rgba(0,0,0,0)",
        },
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "font": {
                "color": "#111111",
                "size": 13,
            },
        },
    )

    return fig


# ============================================================
# PROCESSAMENTO POR EMPRESA
# ============================================================

def processar_empresa(
    engine,
    empresa,
):
    print("\n" + "=" * 70)
    print(f"EMPRESA: {empresa}")
    print("=" * 70)

    df = consultar_posicoes(
        engine=engine,
        empresa=empresa,
        data_inicio=DATA_INICIO,
        data_fim=DATA_FIM,
    )

    if df.empty:
        print(
            f"Nenhuma posição encontrada para {empresa} "
            f"entre {DATA_INICIO} e {DATA_FIM}."
        )
        return 0

    df = preparar_posicoes(df)

    pasta_empresa = (
        PASTA_SAIDA
        / empresa.lower()
    )

    pasta_empresa.mkdir(
        parents=True,
        exist_ok=True,
    )

    arquivos_gerados = 0

    embarcacoes = (
        df[
            [
                "id_embarcacao",
                "nome_embarcacao",
            ]
        ]
        .drop_duplicates()
        .sort_values("nome_embarcacao")
    )

    for _, embarcacao in embarcacoes.iterrows():
        id_embarcacao = embarcacao["id_embarcacao"]
        nome_embarcacao = embarcacao["nome_embarcacao"]

        print(
            f"\nProcessando: {nome_embarcacao} "
            f"(ID {id_embarcacao})"
        )

        df_embarcacao = df[
            df["id_embarcacao"].eq(id_embarcacao)
        ].copy()

        df_gantt = construir_eventos(
            df_embarcacao
        )

        if df_gantt.empty:
            print("Nenhum evento válido.")
            continue

        fig = criar_gantt(
            df_gantt=df_gantt,
            empresa=empresa,
            nome_embarcacao=nome_embarcacao,
        )

        nome_arquivo = normalizar_nome_arquivo(
            nome_embarcacao
        )

        arquivo_saida = (
            pasta_empresa
            / f"{nome_arquivo}.html"
        )

        fig.write_html(
            arquivo_saida,
            full_html=True,
            include_plotlyjs=True,
            config={
                "responsive": True,
                "displayModeBar": True,
                "scrollZoom": False,
            },
        )

        arquivos_gerados += 1

        print(f"Eventos: {len(df_gantt)}")
        print(f"Gantt salvo em: {arquivo_saida}")

    print(
        f"\nArquivos gerados para {empresa}: "
        f"{arquivos_gerados}"
    )

    return arquivos_gerados


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    print("=" * 70)
    print("GERAÇÃO DOS GRÁFICOS GANTT — OFI")
    print("=" * 70)

    print(
        f"Período: {DATA_INICIO} a {DATA_FIM}"
    )

    PASTA_SAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    engine = criar_engine()

    total_arquivos = 0

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))

        print(
            "Conexão com PostgreSQL realizada com sucesso."
        )

        for empresa in EMPRESAS:
            try:
                total_arquivos += processar_empresa(
                    engine=engine,
                    empresa=empresa,
                )

            except Exception as erro:
                print(
                    f"\nERRO AO PROCESSAR {empresa}: "
                    f"{erro}"
                )

    finally:
        engine.dispose()

    print("\n" + "=" * 70)
    print("PROCESSAMENTO CONCLUÍDO")
    print("=" * 70)
    print(
        f"Total de arquivos gerados: {total_arquivos}"
    )
    print(f"Diretório: {PASTA_SAIDA}")


if __name__ == "__main__":
    main()