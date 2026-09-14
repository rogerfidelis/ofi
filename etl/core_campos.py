from pathlib import Path
import os

import pandas as pd
import geopandas as gpd

from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine, text, URL
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÃO DO PROJETO
# ============================================================

BASE = Path(__file__).resolve().parents[1]

ARQUIVO_SHAPEFILE = (
    BASE
    / "shapefiles"
    / "CAMPOS_PRODUCAO_SIRGAS"
    / "CAMPOS_PRODUCAO_SIRGASPolygon.shp"
)

ARQUIVO_ENV = BASE / ".env"


# ============================================================
# CARREGA VARIÁVEIS DE AMBIENTE
# ============================================================

load_dotenv(ARQUIVO_ENV)

DB_HOST = os.getenv("OFI_DB_HOST")
DB_PORT = os.getenv("OFI_DB_PORT")
DB_NAME = os.getenv("OFI_DB_NAME")
DB_USER = os.getenv("OFI_DB_USER")
DB_PASSWORD = os.getenv("OFI_DB_PASSWORD")
DB_SSLMODE = os.getenv("OFI_DB_SSLMODE", "require")


variaveis_obrigatorias = {
    "OFI_DB_HOST": DB_HOST,
    "OFI_DB_PORT": DB_PORT,
    "OFI_DB_NAME": DB_NAME,
    "OFI_DB_USER": DB_USER,
    "OFI_DB_PASSWORD": DB_PASSWORD,
}

faltantes = [
    nome
    for nome, valor in variaveis_obrigatorias.items()
    if not valor
]

if faltantes:
    raise RuntimeError(
        "Variáveis ausentes no .env: "
        + ", ".join(faltantes)
    )


# ============================================================
# CONEXÃO COM POSTGRESQL / AIVEN
# ============================================================

url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
    query={
        "sslmode": DB_SSLMODE
    },
)

engine = create_engine(url)


# ============================================================
# TESTE DE CONEXÃO
# ============================================================

print("=" * 70)
print("IMPORTAÇÃO DE CAMPOS DE PETRÓLEO")
print("=" * 70)

with engine.connect() as conn:

    resultado = conn.execute(
        text(
            """
            SELECT
                current_database(),
                current_user;
            """
        )
    ).fetchone()

    print()
    print("Conexão com PostgreSQL realizada com sucesso.")
    print(f"Banco:   {resultado[0]}")
    print(f"Usuário: {resultado[1]}")


# ============================================================
# VERIFICA ARQUIVO SHAPEFILE
# ============================================================

print()
print("Shapefile:")
print(ARQUIVO_SHAPEFILE)

if not ARQUIVO_SHAPEFILE.exists():
    raise FileNotFoundError(
        f"Shapefile não encontrado:\n{ARQUIVO_SHAPEFILE}"
    )


# ============================================================
# LEITURA DO SHAPEFILE
# ============================================================

print()
print("Lendo shapefile...")

gdf = gpd.read_file(ARQUIVO_SHAPEFILE)

print(f"Registros encontrados: {len(gdf)}")
print(f"CRS encontrado: {gdf.crs}")

print()
print("Colunas encontradas:")
print(gdf.columns.tolist())


# ============================================================
# VALIDAÇÃO DO CRS
# ============================================================

if gdf.crs is None:
    raise ValueError(
        "O shapefile não possui CRS definido."
    )

if gdf.crs.to_epsg() != 4674:

    print()
    print(
        f"Convertendo CRS {gdf.crs} "
        "para SIRGAS 2000 / EPSG:4674..."
    )

    gdf = gdf.to_crs(epsg=4674)

print("CRS validado: EPSG:4674")


# ============================================================
# VALIDAÇÃO DAS COLUNAS DE ORIGEM
# ============================================================

MAPEAMENTO_COLUNAS = {

    "ID": "id_origem",
    "COD_CAMPO": "codigo_campo",
    "SIG_CAMPO": "sigla",
    "NOM_CAMPO": "nome",

    "NOM_BACIA": "bacia",

    "AREA": "area_km2",

    "NUM_CONTRA": "numero_contrato",
    "NUM_RODADA": "numero_rodada",

    "DAT_ASSINA": "data_assinatura",
    "DAT_TERMIN": "data_termino",
    "DAT_DESCOB": "data_descoberta",
    "DAT_INICIO": "data_inicio",

    "ETAPA": "etapa",

    "MED_LAMINA": "lamina_agua_m",

    "FLUIDO_PRI": "fluido_principal",
    "AMBIENTE": "ambiente",
}


colunas_ausentes = [
    coluna
    for coluna in MAPEAMENTO_COLUNAS
    if coluna not in gdf.columns
]

if colunas_ausentes:

    print()
    print("ERRO: algumas colunas esperadas não existem.")
    print("Colunas ausentes:")
    print(colunas_ausentes)

    print()
    print("Colunas disponíveis no shapefile:")
    print(gdf.columns.tolist())

    raise ValueError(
        "Estrutura do shapefile diferente da esperada."
    )


print("Colunas de origem validadas.")


# ============================================================
# SELEÇÃO E RENOMEAÇÃO
# ============================================================

gdf = gdf[
    list(MAPEAMENTO_COLUNAS.keys())
    + ["geometry"]
].copy()

gdf = gdf.rename(
    columns=MAPEAMENTO_COLUNAS
)


# ============================================================
# TRATAMENTO DAS GEOMETRIAS
# ============================================================

print()
print("Validando geometrias...")

gdf["geometry"] = gdf.geometry.make_valid()


def converter_multipolygon(geom):

    if geom is None:
        return None

    if geom.is_empty:
        return None

    if isinstance(geom, Polygon):
        return MultiPolygon([geom])

    if isinstance(geom, MultiPolygon):
        return geom

    return None


gdf["geometry"] = gdf["geometry"].apply(
    converter_multipolygon
)

antes = len(gdf)

gdf = gdf[
    gdf["geometry"].notna()
].copy()

removidos = antes - len(gdf)

print(f"Geometrias descartadas: {removidos}")


# ============================================================
# TRATAMENTO DOS CAMPOS OBRIGATÓRIOS
# ============================================================

gdf["codigo_campo"] = pd.to_numeric(
    gdf["codigo_campo"],
    errors="coerce"
)

gdf = gdf[
    gdf["codigo_campo"].notna()
    & gdf["nome"].notna()
].copy()

gdf["codigo_campo"] = (
    gdf["codigo_campo"]
    .astype(int)
)


# ============================================================
# TRATAMENTO DE NUMÉRICOS
# ============================================================

gdf["id_origem"] = pd.to_numeric(
    gdf["id_origem"],
    errors="coerce"
)

gdf["id_origem"] = gdf["id_origem"].apply(
    lambda x: int(x) if pd.notna(x) else None
).astype(object)


for coluna in [
    "area_km2",
    "lamina_agua_m",
]:

    gdf[coluna] = pd.to_numeric(
        gdf[coluna],
        errors="coerce"
    )

# ============================================================
# TRATAMENTO DAS DATAS
# ============================================================

colunas_data = [
    "data_assinatura",
    "data_termino",
    "data_descoberta",
    "data_inicio",
]

for coluna in colunas_data:

    gdf[coluna] = pd.to_datetime(
        gdf[coluna],
        errors="coerce",
        dayfirst=True,
    ).dt.date


# ============================================================
# CAMPOS CONTROLADOS PELO OFI
# ============================================================

gdf["operadora_id"] = None
gdf["ativo"] = True


# ============================================================
# RENOMEIA A GEOMETRIA PARA A COLUNA DO POSTGRESQL
# ============================================================

gdf = gdf.rename_geometry("geom")


# ============================================================
# ORDEM FINAL DAS COLUNAS
# ============================================================

colunas_destino = [

    "id_origem",
    "codigo_campo",
    "sigla",
    "nome",
    "bacia",
    "operadora_id",
    "area_km2",
    "numero_contrato",
    "numero_rodada",
    "data_assinatura",
    "data_termino",
    "data_descoberta",
    "data_inicio",
    "etapa",
    "lamina_agua_m",
    "fluido_principal",
    "ambiente",
    "geom",
    "ativo",
]

gdf = gdf[colunas_destino]


# ============================================================
# RESUMO ANTES DA CARGA
# ============================================================

print()
print("=" * 70)
print("DADOS PREPARADOS")
print("=" * 70)

print(f"Registros preparados: {len(gdf)}")
print(f"CRS final: {gdf.crs}")

print()
print(
    gdf[
        [
            "codigo_campo",
            "nome",
            "bacia",
        ]
    ].head()
)


# ============================================================
# CONFIRMA QUE A TABELA EXISTE
# ============================================================

with engine.connect() as conn:

    existe = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'core'
                  AND table_name = 'campos'
            );
            """
        )
    ).scalar()

if not existe:
    raise RuntimeError(
        "A tabela core.campos não existe."
    )


# ============================================================
# CARGA
# ============================================================

print()
print("Validação de id_origem:")
print(gdf["id_origem"].head())
print("dtype:", gdf["id_origem"].dtype)
print("tipo primeiro valor:", type(gdf["id_origem"].iloc[0]))
print()
print("Iniciando carga em core.campos...")


# Estratégia atual:
# reconstrução completa dos dados da tabela.
#
# A estrutura da tabela NÃO é apagada.
# Apenas os registros existentes são removidos.

with engine.begin() as conn:

    conn.execute(
        text(
            """
            TRUNCATE TABLE core.campos
            RESTART IDENTITY;
            """
        )
    )


gdf.to_postgis(
    name="campos",
    con=engine,
    schema="core",
    if_exists="append",
    index=False,
)


# ============================================================
# VALIDAÇÃO FINAL
# ============================================================

with engine.connect() as conn:

    quantidade = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM core.campos;
            """
        )
    ).scalar()


print()
print("=" * 70)
print("IMPORTAÇÃO CONCLUÍDA")
print("=" * 70)

print(
    f"Registros existentes em core.campos: "
    f"{quantidade}"
)

engine.dispose()