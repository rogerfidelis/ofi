from pathlib import Path
import os
import re
import unicodedata

import folium
from folium.plugins import AntPath
import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from shapely import wkt
from sqlalchemy import create_engine, text


# ============================================================
# DIRETÓRIOS
# ============================================================

# Arquivo:
# C:\Users\roger\projetos\ofi\mapas\gerar_mapas.py
#
# BASE:
# C:\Users\roger\projetos\ofi

BASE = Path(__file__).resolve().parents[1]

PASTA_SAIDA = BASE / "mapas"


# ============================================================
# CONFIGURAÇÕES DA ANÁLISE
# ============================================================

EMPRESAS = [
    "cbo",
    "bram",
    "starnav",
]

DATA_INICIO = pd.Timestamp("2026-07-16 00:00:00")
DATA_FIM = pd.Timestamp("2026-09-13 23:59:59")

CENTRO_MAPA = [-22.872174, -41.983981]
ZOOM_INICIAL = 9


# ============================================================
# CONEXÃO COM O POSTGRESQL
# ============================================================

load_dotenv(BASE / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    host = os.getenv("OFI_DB_HOST")
    port = os.getenv("OFI_DB_PORT", "5432")
    database = os.getenv("OFI_DB_NAME")
    user = os.getenv("OFI_DB_USER")
    password = os.getenv("OFI_DB_PASSWORD")

    variaveis_ausentes = []

    if not host:
        variaveis_ausentes.append("OFI_DB_HOST")

    if not database:
        variaveis_ausentes.append("OFI_DB_NAME")

    if not user:
        variaveis_ausentes.append("OFI_DB_USER")

    if not password:
        variaveis_ausentes.append("OFI_DB_PASSWORD")

    if variaveis_ausentes:
        raise RuntimeError(
            "Não foi possível montar a conexão com o PostgreSQL. "
            "Variáveis ausentes no arquivo .env: "
            + ", ".join(variaveis_ausentes)
        )

    DATABASE_URL = (
        f"postgresql+psycopg2://{user}:{password}"
        f"@{host}:{port}/{database}"
    )

elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1,
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def nome_arquivo(texto):
    """
    Converte o nome da embarcação para um nome seguro de arquivo.

    Exemplo:
        CBO IPANEMA -> cbo_ipanema
    """

    texto = str(texto).strip()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = texto.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    texto = re.sub(
        r"[^\w\s-]",
        "",
        texto,
    )

    texto = re.sub(
        r"[\s-]+",
        "_",
        texto,
    )

    return texto.lower().strip("_")


def formatar_data(valor):
    """Formata datas para os pop-ups do mapa."""

    if valor is None or pd.isna(valor):
        return "Não informado"

    return pd.Timestamp(valor).strftime(
        "%d/%m/%Y %H:%M:%S"
    )


def formatar_texto(valor, padrao="Não informado"):
    """Evita exibir None ou NaN nos pop-ups."""

    if valor is None or pd.isna(valor):
        return padrao

    texto_formatado = str(valor).strip()

    if not texto_formatado:
        return padrao

    return texto_formatado


def normalizar_tipo(tipo):
    """Normaliza o tipo para utilização no dicionário de cores."""

    if tipo is None or pd.isna(tipo):
        return ""

    return str(tipo).strip().lower()


def cor_ponto(tipo):
    """Retorna a cor correspondente ao tipo de ativo ou local."""

    cores = {
        "porto": "red",
        "estaleiro": "white",
        "fundeio": "lightblue",
        "navio sonda": "blue",
        "fpso": "purple",
        "semi-sub/prod/perfuração": "green",
        "semi-sub/perfuração": "orange",
        "fixa (habitada)": "darkred",
        "semi-sub/produção": "cadetblue",
        "fixa (rebombeio)": "darkpurple",
    }

    return cores.get(
        normalizar_tipo(tipo),
        "gray",
    )


# ============================================================
# CONSULTAS AO BANCO
# ============================================================

def carregar_campos():
    """
    Carrega os polígonos dos campos diretamente de core.campos.
    """

    consulta = text("""
        SELECT
            id_campo,
            nome,
            bacia,
            ST_AsText(geom) AS geometria
        FROM core.campos
        WHERE geom IS NOT NULL
          AND COALESCE(ativo, TRUE) = TRUE
        ORDER BY nome;
    """)

    campos = pd.read_sql(
        consulta,
        engine,
    )

    if campos.empty:
        return gpd.GeoDataFrame(
            campos,
            geometry=[],
            crs="EPSG:4326",
        )

    campos["geometry"] = campos["geometria"].apply(
        wkt.loads
    )

    campos = gpd.GeoDataFrame(
        campos.drop(columns="geometria"),
        geometry="geometry",
        crs="EPSG:4674",
    )

    campos = campos.to_crs(
        epsg=4326
    )

    return campos


def carregar_ativos():
    """
    Carrega a posição mais recente disponível de cada ativo.

    A data_consulta de raw.posicoes_ativos representa o momento
    em que o registro foi carregado. Por isso, os ativos não são
    filtrados pelo período da trajetória da embarcação.
    """

    consulta = text("""
        WITH ultima_posicao AS (
            SELECT DISTINCT ON (pa.id_ativo)
                pa.id_ativo,
                pa.latitude,
                pa.longitude,
                pa.data_consulta
            FROM raw.posicoes_ativos pa
            WHERE pa.latitude IS NOT NULL
              AND pa.longitude IS NOT NULL
            ORDER BY
                pa.id_ativo,
                pa.data_consulta DESC,
                pa.id_posicao DESC
        )
        SELECT
            a.id_ativo,
            a.nome_ativo,
            a.tipo_ativo,
            up.latitude,
            up.longitude,
            up.data_consulta,
            campo_encontrado.nome AS campo,
            campo_encontrado.bacia
        FROM core.ativos a
        INNER JOIN ultima_posicao up
            ON up.id_ativo = a.id_ativo
        LEFT JOIN LATERAL (
            SELECT
                c.nome,
                c.bacia
            FROM core.campos c
            WHERE c.geom IS NOT NULL
              AND ST_Contains(
                    c.geom,
                    ST_SetSRID(
                        ST_MakePoint(
                            up.longitude,
                            up.latitude
                        ),
                        4674
                    )
                  )
            LIMIT 1
        ) campo_encontrado
            ON TRUE
        ORDER BY a.nome_ativo;
    """)

    return pd.read_sql(
        consulta,
        engine,
        parse_dates=["data_consulta"],
    )


def carregar_locais_fixos():
    """
    Carrega portos, estaleiros e fundeadouros.
    """

    consulta = text("""
        SELECT
            id_local,
            nome_local,
            tipo_local,
            latitude,
            longitude
        FROM core.locais_fixos
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY nome_local;
    """)

    return pd.read_sql(
        consulta,
        engine,
    )


def carregar_embarcacoes(empresa):
    """
    Retorna somente embarcações que possuem posições no período.
    """

    if empresa not in EMPRESAS:
        raise ValueError(
            f"Empresa não autorizada: {empresa}"
        )

    tabela = f"raw.posicoes_{empresa}"

    consulta = text(f"""
        SELECT DISTINCT
            e.id_embarcacao,
            e.nome_embarcacao
        FROM {tabela} p
        INNER JOIN core.embarcacoes e
            ON e.id_embarcacao = p.id_embarcacao
        WHERE p.data_reportada >= :data_inicio
          AND p.data_reportada <= :data_fim
          AND p.latitude IS NOT NULL
          AND p.longitude IS NOT NULL
        ORDER BY e.nome_embarcacao;
    """)

    return pd.read_sql(
        consulta,
        engine,
        params={
            "data_inicio": DATA_INICIO,
            "data_fim": DATA_FIM,
        },
    )


def carregar_trajetoria(
    empresa,
    id_embarcacao,
):
    """
    Carrega e ordena cronologicamente as posições da embarcação.
    """

    if empresa not in EMPRESAS:
        raise ValueError(
            f"Empresa não autorizada: {empresa}"
        )

    tabela = f"raw.posicoes_{empresa}"

    consulta = text(f"""
        SELECT
            p.id_posicao,
            p.data_consulta,
            p.data_reportada,
            p.latitude,
            p.longitude,
            p.status
        FROM {tabela} p
        WHERE p.id_embarcacao = :id_embarcacao
          AND p.data_reportada >= :data_inicio
          AND p.data_reportada <= :data_fim
          AND p.latitude IS NOT NULL
          AND p.longitude IS NOT NULL
        ORDER BY
            p.data_reportada ASC,
            p.id_posicao ASC;
    """)

    dados = pd.read_sql(
        consulta,
        engine,
        params={
            "id_embarcacao": int(id_embarcacao),
            "data_inicio": DATA_INICIO,
            "data_fim": DATA_FIM,
        },
        parse_dates=[
            "data_consulta",
            "data_reportada",
        ],
    )

    if dados.empty:
        return dados

    dados["latitude"] = pd.to_numeric(
        dados["latitude"],
        errors="coerce",
    )

    dados["longitude"] = pd.to_numeric(
        dados["longitude"],
        errors="coerce",
    )

    dados = dados.dropna(
        subset=[
            "latitude",
            "longitude",
            "data_reportada",
        ]
    )

    # Limites geográficos válidos
    dados = dados[
        dados["latitude"].between(-90, 90)
        & dados["longitude"].between(-180, 180)
    ].copy()

    # Evita desenhar duas vezes exatamente o mesmo registro
    dados = dados.drop_duplicates(
        subset=[
            "data_reportada",
            "latitude",
            "longitude",
            "status",
        ],
        keep="first",
    )

    dados = dados.sort_values(
        by=[
            "data_reportada",
            "id_posicao",
        ]
    ).reset_index(drop=True)

    return dados


# ============================================================
# MAPA BASE
# ============================================================

def criar_mapa_base():
    """
    Cria um mapa sem carregar automaticamente o servidor
    público do OpenStreetMap.

    As camadas de base utilizadas são servidas pela Esri.
    """

    mapa = folium.Map(
        location=CENTRO_MAPA,
        zoom_start=ZOOM_INICIAL,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # Camada padrão
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles © Esri",
        name="Mapa de ruas",
        overlay=False,
        control=True,
        show=True,
    ).add_to(mapa)

    # Camada alternativa
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles © Esri",
        name="Imagem de satélite",
        overlay=False,
        control=True,
        show=False,
    ).add_to(mapa)

    return mapa


# ============================================================
# CAMADA DOS CAMPOS
# ============================================================

def adicionar_campos(
    mapa,
    campos,
):
    if campos.empty:
        print("Aviso: nenhum campo foi carregado.")
        return

    grupo = folium.FeatureGroup(
        name="Campos de Produção",
        show=True,
    )

    folium.GeoJson(
        data=campos.to_json(),
        name="Campos de Produção",
        style_function=lambda feature: {
            "fillColor": "yellow",
            "color": "orange",
            "weight": 2,
            "fillOpacity": 0.25,
        },
        highlight_function=lambda feature: {
            "fillColor": "#FFD700",
            "color": "#FF8C00",
            "weight": 4,
            "fillOpacity": 0.45,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "nome",
                "bacia",
            ],
            aliases=[
                "Campo:",
                "Bacia:",
            ],
            sticky=True,
        ),
    ).add_to(grupo)

    grupo.add_to(mapa)


# ============================================================
# CAMADA DOS ATIVOS
# ============================================================

def adicionar_ativos(
    mapa,
    ativos,
):
    if ativos.empty:
        print("Aviso: nenhum ativo foi carregado.")
        return

    grupo = folium.FeatureGroup(
        name="Ativos offshore",
        show=True,
    )

    for _, ativo in ativos.iterrows():
        nome = formatar_texto(
            ativo["nome_ativo"]
        )

        tipo = formatar_texto(
            ativo["tipo_ativo"]
        )

        campo = formatar_texto(
            ativo["campo"],
            "Não identificado",
        )

        bacia = formatar_texto(
            ativo["bacia"],
            "Não identificada",
        )

        cor = cor_ponto(tipo)

        popup = f"""
        <div style="min-width:250px;">
            <b>Ativo:</b> {nome}<br>
            <b>Tipo:</b> {tipo}<br>
            <b>Campo:</b> {campo}<br>
            <b>Bacia:</b> {bacia}<br>
            <b>Posição de referência:</b>
            {formatar_data(ativo["data_consulta"])}
        </div>
        """

        folium.CircleMarker(
            location=[
                float(ativo["latitude"]),
                float(ativo["longitude"]),
            ],
            radius=6,
            color=cor,
            weight=2,
            fill=True,
            fill_color=cor,
            fill_opacity=0.85,
            tooltip=nome,
            popup=folium.Popup(
                popup,
                max_width=350,
            ),
        ).add_to(grupo)

    grupo.add_to(mapa)


# ============================================================
# CAMADA DOS LOCAIS FIXOS
# ============================================================

def adicionar_locais_fixos(
    mapa,
    locais,
):
    if locais.empty:
        print("Aviso: nenhum local fixo foi carregado.")
        return

    grupo = folium.FeatureGroup(
        name="Portos, estaleiros e fundeadouros",
        show=True,
    )

    for _, local in locais.iterrows():
        nome = formatar_texto(
            local["nome_local"]
        )

        tipo = formatar_texto(
            local["tipo_local"]
        )

        cor = cor_ponto(tipo)

        popup = f"""
        <div style="min-width:220px;">
            <b>Local:</b> {nome}<br>
            <b>Tipo:</b> {tipo}
        </div>
        """

        folium.CircleMarker(
            location=[
                float(local["latitude"]),
                float(local["longitude"]),
            ],
            radius=7,
            color=cor,
            weight=2,
            fill=True,
            fill_color=cor,
            fill_opacity=0.90,
            tooltip=nome,
            popup=folium.Popup(
                popup,
                max_width=300,
            ),
        ).add_to(grupo)

    grupo.add_to(mapa)


# ============================================================
# CAMADA DAS POSIÇÕES E TRAJETÓRIA
# ============================================================

def adicionar_trajetoria(
    mapa,
    dados,
    nome_embarcacao,
):
    if dados.empty:
        return

    trajetoria = dados[
        ["latitude", "longitude"]
    ].values.tolist()

    grupo_posicoes = folium.FeatureGroup(
        name=f"Posições — {nome_embarcacao}",
        show=True,
    )

    for _, posicao in dados.iterrows():
        status = formatar_texto(
            posicao["status"]
        )

        popup = f"""
        <div style="min-width:250px;">
            <b>Embarcação:</b> {nome_embarcacao}<br>
            <b>Data reportada:</b>
            {formatar_data(posicao["data_reportada"])}<br>
            <b>Status:</b> {status}
        </div>
        """

        folium.CircleMarker(
            location=[
                float(posicao["latitude"]),
                float(posicao["longitude"]),
            ],
            radius=3,
            color="#00BFFF",
            weight=1,
            fill=True,
            fill_color="#00BFFF",
            fill_opacity=0.75,
            popup=folium.Popup(
                popup,
                max_width=320,
            ),
        ).add_to(grupo_posicoes)

    grupo_posicoes.add_to(mapa)

    if len(trajetoria) >= 2:
        grupo_trajetoria = folium.FeatureGroup(
            name="Trajetória AIS",
            show=True,
        )

        AntPath(
            locations=trajetoria,
            color="#0077FF",
            weight=5,
            opacity=0.85,
            delay=900,
            dash_array=[5, 10],
            pulse_color="white",
        ).add_to(grupo_trajetoria)

        grupo_trajetoria.add_to(mapa)

    inicio = dados.iloc[0]
    fim = dados.iloc[-1]

    folium.Marker(
        location=trajetoria[0],
        icon=folium.Icon(
            color="green",
            icon="play",
            prefix="glyphicon",
        ),
        popup=folium.Popup(
            (
                "<b>INÍCIO DA TRAJETÓRIA</b><br>"
                f"{formatar_data(inicio['data_reportada'])}"
            ),
            max_width=300,
        ),
    ).add_to(mapa)

    folium.Marker(
        location=trajetoria[-1],
        icon=folium.Icon(
            color="red",
            icon="stop",
            prefix="glyphicon",
        ),
        popup=folium.Popup(
            (
                "<b>ÚLTIMA POSIÇÃO</b><br>"
                f"{formatar_data(fim['data_reportada'])}"
            ),
            max_width=300,
        ),
    ).add_to(mapa)

    lat_min = dados["latitude"].min()
    lat_max = dados["latitude"].max()
    lon_min = dados["longitude"].min()
    lon_max = dados["longitude"].max()

    # Evita erro de enquadramento quando há apenas uma coordenada
    if lat_min == lat_max:
        lat_min -= 0.01
        lat_max += 0.01

    if lon_min == lon_max:
        lon_min -= 0.01
        lon_max += 0.01

    mapa.fit_bounds(
        [
            [lat_min, lon_min],
            [lat_max, lon_max],
        ],
        padding=[30, 30],
    )


# ============================================================
# LEGENDA
# ============================================================

def adicionar_legenda(mapa):
    legenda = """
    <style>
        .legenda-ofi {
            position: fixed;
            bottom: 25px;
            right: 25px;
            width: 290px;
            max-width: calc(100vw - 30px);
            background: #0B1F3A;
            border: 2px solid #1CA3EC;
            border-radius: 10px;
            padding: 15px;
            color: white;
            font-family: Arial, sans-serif;
            font-size: 13px;
            z-index: 9999;
            box-sizing: border-box;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
        }

        .legenda-ofi h3 {
            margin: 0 0 10px 0;
            color: #1CA3EC;
        }

        @media (max-width: 768px) {
            .legenda-ofi {
                right: 15px;
                bottom: 15px;
                width: 235px;
                padding: 10px;
                font-size: 11px;
            }
        }
    </style>

    <div class="legenda-ofi">
        <h3>Legenda</h3>

        <span style="color:red;">●</span> Porto<br>
        <span style="color:white;">●</span> Estaleiro<br>
        <span style="color:lightblue;">●</span> Fundeio<br>
        <span style="color:purple;">●</span> FPSO<br>
        <span style="color:blue;">●</span> Navio-sonda<br>
        <span style="color:green;">●</span>
        Semi-Sub/Prod/Perfuração<br>
        <span style="color:orange;">●</span>
        Semi-Sub/Perfuração<br>
        <span style="color:darkred;">●</span>
        Plataforma fixa<br>
        <span style="color:cadetblue;">●</span>
        Semi-Sub/Produção<br>
        <span style="color:gray;">●</span>
        Tipo não classificado<br><br>

        <span style="color:#00BFFF;">
            ━ ━ ━ ━
        </span>
        Trajetória AIS<br>

        🟢 Início da trajetória<br>
        🔴 Última posição
    </div>
    """

    mapa.get_root().html.add_child(
        folium.Element(legenda)
    )


# ============================================================
# GERAÇÃO DE UM MAPA
# ============================================================

def gerar_mapa_embarcacao(
    empresa,
    embarcacao,
    campos,
    ativos,
    locais,
):
    id_embarcacao = int(
        embarcacao["id_embarcacao"]
    )

    nome_embarcacao = formatar_texto(
        embarcacao["nome_embarcacao"]
    )

    dados = carregar_trajetoria(
        empresa=empresa,
        id_embarcacao=id_embarcacao,
    )

    if dados.empty:
        print(
            f"{empresa.upper()} | {nome_embarcacao}: "
            "nenhuma posição válida encontrada no período."
        )

        return False

    mapa = criar_mapa_base()

    adicionar_campos(
        mapa,
        campos,
    )

    adicionar_ativos(
        mapa,
        ativos,
    )

    adicionar_locais_fixos(
        mapa,
        locais,
    )

    adicionar_trajetoria(
        mapa,
        dados,
        nome_embarcacao,
    )

    adicionar_legenda(mapa)

    folium.LayerControl(
        collapsed=False,
    ).add_to(mapa)

    pasta_empresa = (
        PASTA_SAIDA / empresa
    )

    pasta_empresa.mkdir(
        parents=True,
        exist_ok=True,
    )

    arquivo_saida = (
        pasta_empresa
        / f"{nome_arquivo(nome_embarcacao)}.html"
    )

    mapa.save(
        str(arquivo_saida)
    )

    print(
        f"{empresa.upper()} | "
        f"{nome_embarcacao}: "
        f"{len(dados)} posições | "
        f"{arquivo_saida}"
    )

    return True


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    print("=" * 72)
    print("GERAÇÃO DOS MAPAS DE TRAJETÓRIA — OFI")
    print("=" * 72)

    print(
        f"Período da análise: "
        f"{DATA_INICIO:%d/%m/%Y} a "
        f"{DATA_FIM:%d/%m/%Y}"
    )

    print(
        f"Diretório de saída: {PASTA_SAIDA}"
    )

    print()

    try:
        with engine.connect() as conexao:
            conexao.execute(
                text("SELECT 1")
            )

        print(
            "Conexão com PostgreSQL realizada com sucesso."
        )

    except Exception as erro:
        print(
            "Não foi possível conectar ao PostgreSQL."
        )

        raise erro

    print()
    print("Carregando campos de produção...")

    campos = carregar_campos()

    print(
        f"Campos carregados: {len(campos)}"
    )

    print(
        "Carregando as posições mais recentes dos ativos..."
    )

    ativos = carregar_ativos()

    print(
        f"Ativos carregados: {len(ativos)}"
    )

    print(
        "Carregando portos, estaleiros e fundeadouros..."
    )

    locais = carregar_locais_fixos()

    print(
        f"Locais fixos carregados: {len(locais)}"
    )

    total_gerados = 0
    total_sem_dados = 0

    for empresa in EMPRESAS:
        print()
        print("=" * 72)
        print(f"EMPRESA: {empresa.upper()}")
        print("=" * 72)

        try:
            embarcacoes = carregar_embarcacoes(
                empresa
            )

        except Exception as erro:
            print(
                f"Erro ao consultar a empresa "
                f"{empresa.upper()}: {erro}"
            )

            continue

        print(
            "Embarcações com posições no período: "
            f"{len(embarcacoes)}"
        )

        for _, embarcacao in embarcacoes.iterrows():
            try:
                mapa_gerado = gerar_mapa_embarcacao(
                    empresa=empresa,
                    embarcacao=embarcacao,
                    campos=campos,
                    ativos=ativos,
                    locais=locais,
                )

                if mapa_gerado:
                    total_gerados += 1
                else:
                    total_sem_dados += 1

            except Exception as erro:
                nome = formatar_texto(
                    embarcacao["nome_embarcacao"]
                )

                total_sem_dados += 1

                print(
                    f"ERRO | {empresa.upper()} | "
                    f"{nome}: {erro}"
                )

    print()
    print("=" * 72)
    print("GERAÇÃO CONCLUÍDA")
    print("=" * 72)

    print(
        f"Mapas gerados: {total_gerados}"
    )

    print(
        "Embarcações não geradas ou com erro: "
        f"{total_sem_dados}"
    )

    print(
        f"Diretório: {PASTA_SAIDA}"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()