from pathlib import Path
import os

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# CONFIGURAÇÃO
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
# VARIÁVEIS DE AMBIENTE
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
        "Variáveis de ambiente ausentes: "
        + ", ".join(faltantes)
    )


# ============================================================
# CONEXÃO COM POSTGRESQL
# ============================================================

url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)

engine = create_engine(
    url,
    connect_args={
        "sslmode": DB_SSLMODE
    },
)


# ============================================================
# INÍCIO
# ============================================================

print("=" * 70)
print("IMPORTAÇÃO DE OPERADORES — core.operadores")
print("=" * 70)


# ============================================================
# TESTE DE CONEXÃO
# ============================================================

with engine.connect() as conn:
    conn.execute(text("SELECT 1"))

print("Conexão com PostgreSQL estabelecida.")


# ============================================================
# VERIFICAÇÃO DO SHAPEFILE
# ============================================================

if not ARQUIVO_SHAPEFILE.exists():
    raise FileNotFoundError(
        f"Shapefile não encontrado:\n{ARQUIVO_SHAPEFILE}"
    )

print()
print("Lendo shapefile:")
print(ARQUIVO_SHAPEFILE)


# ============================================================
# LEITURA
# ============================================================

gdf = gpd.read_file(ARQUIVO_SHAPEFILE)

print(f"Registros encontrados: {len(gdf)}")


# ============================================================
# VALIDAÇÃO DA COLUNA
# ============================================================

COLUNA_OPERADOR = "OPERADOR_C"

if COLUNA_OPERADOR not in gdf.columns:
    raise ValueError(
        f"A coluna {COLUNA_OPERADOR} não existe no shapefile."
    )

print(f"Coluna {COLUNA_OPERADOR} encontrada.")


# ============================================================
# PREPARAÇÃO DOS OPERADORES
# ============================================================

operadores = (
    gdf[[COLUNA_OPERADOR]]
    .rename(
        columns={
            COLUNA_OPERADOR: "nome_operador"
        }
    )
    .copy()
)


# Remove valores nulos
operadores = operadores.dropna(
    subset=["nome_operador"]
)


# Remove espaços no início e no final
operadores["nome_operador"] = (
    operadores["nome_operador"]
    .astype(str)
    .str.strip()
)


# Remove strings vazias
operadores = operadores[
    operadores["nome_operador"] != ""
]


quantidade_antes = len(operadores)


# Remove operadores repetidos
operadores = (
    operadores
    .drop_duplicates(
        subset=["nome_operador"]
    )
    .sort_values("nome_operador")
    .reset_index(drop=True)
)


print()
print(
    f"Ocorrências de operadores no shapefile: "
    f"{quantidade_antes}"
)

print(
    f"Operadores únicos encontrados: "
    f"{len(operadores)}"
)


# ============================================================
# VERIFICAÇÃO DA TABELA
# ============================================================

with engine.connect() as conn:

    tabela_existe = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'core'
                  AND table_name = 'operadores'
            );
            """
        )
    ).scalar()


if not tabela_existe:
    raise RuntimeError(
        "A tabela core.operadores não existe. "
        "Execute primeiro a migration "
        "010_create_core_operadores.sql."
    )


# ============================================================
# IMPORTAÇÃO INCREMENTAL
# ============================================================

novos = 0
existentes = 0


sql_insert = text(
    """
    INSERT INTO core.operadores (
        nome_operador
    )
    VALUES (
        :nome_operador
    )
    ON CONFLICT (nome_operador)
    DO NOTHING
    RETURNING id_operador;
    """
)


with engine.begin() as conn:

    for nome_operador in operadores["nome_operador"]:

        resultado = conn.execute(
            sql_insert,
            {
                "nome_operador": nome_operador
            },
        ).scalar()

        if resultado is None:
            existentes += 1
        else:
            novos += 1


# ============================================================
# VALIDAÇÃO FINAL
# ============================================================

with engine.connect() as conn:

    total_banco = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM core.operadores;
            """
        )
    ).scalar()


print()
print("-" * 70)
print(f"Novos operadores inseridos: {novos}")
print(f"Operadores já existentes: {existentes}")
print(f"Total em core.operadores: {total_banco}")
print("-" * 70)

print()
print("Carga concluída com sucesso.")


engine.dispose()