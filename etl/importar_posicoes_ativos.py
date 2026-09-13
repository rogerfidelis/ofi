import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE = Path(__file__).resolve().parents[1]

ARQUIVO = BASE / "dados" / "SURVEY_POSICOES.xlsx"
ABA_EXCEL = "posicoes"

TIPOS_EXCLUIDOS = {"porto", "estaleiro"}

# A coluna do banco é TIMESTAMP sem fuso.
# Convenção: armazenar todas as consultas em UTC.
DATA_CONSULTA = (
    datetime.now(ZoneInfo("UTC"))
    .replace(tzinfo=None)
)


# ============================================================
# LEITURA E VALIDAÇÃO DO EXCEL
# ============================================================

if not ARQUIVO.exists():
    raise FileNotFoundError(
        f"Arquivo não encontrado: {ARQUIVO}"
    )

df = pd.read_excel(
    ARQUIVO,
    sheet_name=ABA_EXCEL,
    usecols=["unidade", "tipo", "latitude", "longitude"],
)

quantidade_original = len(df)

df["unidade"] = (
    df["unidade"]
    .astype("string")
    .str.strip()
    .replace("", pd.NA)
)

df["tipo"] = (
    df["tipo"]
    .astype("string")
    .str.strip()
    .replace("", pd.NA)
)

# Excluir portos e estaleiros
mascara_excluidos = (
    df["tipo"]
    .str.casefold()
    .isin(TIPOS_EXCLUIDOS)
)

quantidade_excluidos = int(mascara_excluidos.sum())
df = df.loc[~mascara_excluidos].copy()

# Registros sem tipo ficam pendentes:
# não é possível aplicar o filtro com segurança.
mascara_pendentes = (
    df["unidade"].isna()
    | df["tipo"].isna()
)

pendentes = df.loc[mascara_pendentes].copy()
df = df.loc[~mascara_pendentes].copy()

if not pendentes.empty:
    print("\nRegistros pendentes — não serão inseridos:")
    print(
        pendentes[["unidade", "tipo"]]
        .to_string(index=False)
    )

# Padronizar coordenadas
for coluna in ["latitude", "longitude"]:
    df[coluna] = pd.to_numeric(
        df[coluna]
        .astype("string")
        .str.replace(",", ".", regex=False),
        errors="coerce",
    ).round(8)

# Ignorar ativos sem latitude ou longitude
mascara_sem_coordenadas = (
    df["latitude"].isna()
    | df["longitude"].isna()
)

sem_coordenadas = df.loc[
    mascara_sem_coordenadas,
    ["unidade", "latitude", "longitude"],
].copy()

quantidade_sem_coordenadas = len(sem_coordenadas)

if not sem_coordenadas.empty:
    print("\nAtivos ignorados por falta de coordenadas:")
    print(sem_coordenadas.to_string(index=False))

df = df.loc[~mascara_sem_coordenadas].copy()

# Coordenadas preenchidas precisam estar dentro dos limites
mascara_fora_limites = (
    ~df["latitude"].between(-90, 90)
    | ~df["longitude"].between(-180, 180)
)

if mascara_fora_limites.any():
    raise ValueError(
        "Coordenadas fora dos limites geográficos. "
        "Nenhuma posição será inserida:\n"
        + df.loc[
            mascara_fora_limites,
            ["unidade", "latitude", "longitude"],
        ].to_string(index=False)
    )

# Identificar nomes equivalentes
df["_chave_nome"] = df["unidade"].str.casefold()

# Remover repetições idênticas
df = df.drop_duplicates(
    subset=["_chave_nome", "latitude", "longitude"]
).copy()

# Uma consulta não pode atribuir duas posições ao mesmo ativo
mascara_posicoes_conflitantes = df.duplicated(
    subset="_chave_nome",
    keep=False,
)

if mascara_posicoes_conflitantes.any():
    raise ValueError(
        "O mesmo ativo possui posições diferentes no Excel:\n"
        + df.loc[
            mascara_posicoes_conflitantes,
            ["unidade", "latitude", "longitude"],
        ].to_string(index=False)
    )

if df.empty:
    raise ValueError(
        "Nenhuma posição válida encontrada. "
        "O banco não será alterado."
    )


# ============================================================
# CONEXÃO COM POSTGRESQL
# ============================================================

load_dotenv(BASE / ".env")

senha = os.getenv("OFI_DB_PASSWORD")

if not senha:
    raise ValueError(
        "OFI_DB_PASSWORD não encontrada no arquivo .env."
    )

url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("OFI_DB_USER", "postgres"),
    password=senha,
    host=os.getenv("OFI_DB_HOST", "localhost"),
    port=int(os.getenv("OFI_DB_PORT", "5432")),
    database=os.getenv("OFI_DB_NAME", "ofi"),
)

engine = create_engine(url)


# ============================================================
# RELACIONAMENTO E INSERÇÃO HISTÓRICA
# ============================================================

sql_insert = text("""
    INSERT INTO raw.posicoes_ativos (
        id_ativo,
        data_consulta,
        latitude,
        longitude
    )
    VALUES (
        :id_ativo,
        :data_consulta,
        :latitude,
        :longitude
    )
    ON CONFLICT ON CONSTRAINT posicoes_ativos_unique
    DO NOTHING
    RETURNING id_posicao;
""")

inseridos = 0

try:
    with engine.begin() as conexao:

        # Mantém o cadastro estável durante a carga
        conexao.execute(
            text("LOCK TABLE core.ativos IN SHARE MODE;")
        )

        ativos = conexao.execute(
            text("""
                SELECT id_ativo, nome_ativo
                FROM core.ativos;
            """)
        ).mappings().all()

        mapa_ativos = {}

        for ativo in ativos:
            chave = ativo["nome_ativo"].strip().casefold()

            if chave in mapa_ativos:
                raise ValueError(
                    "Nomes equivalentes duplicados em core.ativos: "
                    f"{ativo['nome_ativo']}"
                )

            mapa_ativos[chave] = ativo["id_ativo"]

        # Todos os nomes devem ter cadastro correspondente
        nao_cadastrados = df.loc[
            ~df["_chave_nome"].isin(mapa_ativos),
            "unidade",
        ].tolist()

        if nao_cadastrados:
            raise ValueError(
                "Unidades não encontradas em core.ativos. "
                "Nenhuma posição será inserida:\n"
                + "\n".join(nao_cadastrados)
            )

        for linha in df.itertuples(index=False):
            id_ativo = mapa_ativos[
                linha.unidade.casefold()
            ]

            id_posicao = conexao.execute(
                sql_insert,
                {
                    "id_ativo": id_ativo,
                    "data_consulta": DATA_CONSULTA,
                    "latitude": float(linha.latitude),
                    "longitude": float(linha.longitude),
                },
            ).scalar_one_or_none()

            if id_posicao is not None:
                inseridos += 1

    print(
    f"Ativos ignorados por falta de coordenadas: "
    f"{quantidade_sem_coordenadas}")
            
    print("\nIMPORTAÇÃO CONCLUÍDA")
    print(f"Data da consulta (UTC): {DATA_CONSULTA}")
    print(f"Registros no Excel: {quantidade_original}")
    print(f"Portos e estaleiros excluídos: {quantidade_excluidos}")
    print(f"Registros pendentes: {len(pendentes)}")
    print(f"Novas posições inseridas: {inseridos}")

finally:
    engine.dispose()