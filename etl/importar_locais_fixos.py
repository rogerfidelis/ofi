from pathlib import Path
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# CONFIGURACAO
# ============================================================

BASE = Path(__file__).resolve().parents[1]
ARQUIVO_EXCEL = BASE / "dados" / "SURVEY_POSICOES.xlsx"

load_dotenv(BASE / ".env")


# ============================================================
# CONEXÃO
# ============================================================

DB_HOST = os.getenv("OFI_DB_HOST")
DB_PORT = os.getenv("OFI_DB_PORT")
DB_NAME = os.getenv("OFI_DB_NAME")
DB_USER = os.getenv("OFI_DB_USER")
DB_PASSWORD = os.getenv("OFI_DB_PASSWORD")

variaveis = {
    "OFI_DB_HOST": DB_HOST,
    "OFI_DB_PORT": DB_PORT,
    "OFI_DB_NAME": DB_NAME,
    "OFI_DB_USER": DB_USER,
    "OFI_DB_PASSWORD": DB_PASSWORD,
}

ausentes = [
    nome
    for nome, valor in variaveis.items()
    if not valor
]

if ausentes:
    raise RuntimeError(
        "Variáveis ausentes no arquivo .env: "
        + ", ".join(ausentes)
    )

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
    query={"sslmode": "require"}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


# ============================================================
# LEITURA E TRATAMENTO
# ============================================================

def preparar_locais_fixos() -> pd.DataFrame:
    if not ARQUIVO_EXCEL.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ARQUIVO_EXCEL}"
        )

    df = pd.read_excel(
        ARQUIVO_EXCEL,
        sheet_name="posicoes"
    )

    # Normaliza os nomes das colunas
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
    )

    colunas_obrigatorias = {
        "unidade",
        "tipo",
        "latitude",
        "longitude"
    }

    colunas_ausentes = colunas_obrigatorias - set(df.columns)

    if colunas_ausentes:
        raise ValueError(
            "Colunas obrigatórias ausentes no Excel: "
            f"{sorted(colunas_ausentes)}"
        )

    quantidade_excel = len(df)

    # Normaliza o tipo antes do filtro
    df["tipo"] = (
        df["tipo"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    # Mantém somente portos e estaleiros
    df = df[
        df["tipo"].isin(["porto", "estaleiro","fundeio"])
    ].copy()

    # Seleciona e renomeia as colunas
    df = df[
        ["unidade", "tipo", "latitude", "longitude"]
    ].rename(
        columns={
            "unidade": "nome",
            "tipo": "tipo_local"
        }
    )

    # Normalização dos valores
    df["nome"] = (
        df["nome"]
        .astype("string")
        .str.strip()
    )

    df["tipo_local"] = (
        df["tipo_local"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    # Remove registros incompletos
    antes_invalidos = len(df)

    df = df.dropna(
        subset=[
            "nome",
            "tipo_local",
            "latitude",
            "longitude"
        ]
    )

    removidos_invalidos = antes_invalidos - len(df)

    # Remove duplicidades dentro do próprio Excel
    antes_duplicidades = len(df)

    df = df.drop_duplicates(
        subset=[
            "nome",
            "tipo_local",
            "latitude",
            "longitude"
        ]
    )

    duplicidades_removidas = antes_duplicidades - len(df)

    print("=" * 70)
    print("CADASTRO DE LOCAIS FIXOS — core.locais_fixos")
    print("=" * 70)
    print(f"Registros no Excel: {quantidade_excel}")
    print(f"Portos e estaleiros encontrados: {len(df)}")
    print(f"Registros inválidos removidos: {removidos_invalidos}")
    print(f"Duplicidades removidas: {duplicidades_removidas}")

    return df


# ============================================================
# CARGA
# ============================================================
def carregar_locais_fixos(df: pd.DataFrame) -> None:

    sql_upsert = text("""
        INSERT INTO core.locais_fixos (
            nome_local,
            tipo_local,
            latitude,
            longitude
        )
        VALUES (
            CAST(:nome AS VARCHAR),
            CAST(:tipo_local AS VARCHAR),
            CAST(:latitude AS NUMERIC),
            CAST(:longitude AS NUMERIC)
        )

        ON CONFLICT (nome_local)
        DO UPDATE SET
            tipo_local = EXCLUDED.tipo_local,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude;
    """)

    processados = 0

    with engine.begin() as connection:

        for registro in df.to_dict(orient="records"):

            connection.execute(
                sql_upsert,
                {
                    "nome": registro["nome"],
                    "tipo_local": registro["tipo_local"],
                    "latitude": float(registro["latitude"]),
                    "longitude": float(registro["longitude"])
                }
            )

            processados += 1

    print(f"Locais processados: {processados}")
    print("Carga concluída com sucesso.")



# ============================================================
# EXECUÇÃO
# ============================================================

def main() -> None:
    df_locais = preparar_locais_fixos()

    if df_locais.empty:
        print("Nenhum porto ou estaleiro válido encontrado.")
        return

    carregar_locais_fixos(df_locais)


if __name__ == "__main__":
    main()