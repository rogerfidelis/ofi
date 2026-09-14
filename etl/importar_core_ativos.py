import os
from pathlib import Path

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

# Valores permitidos pelo CHECK de core.ativos
TIPOS_PERMITIDOS = {
    "navio sonda",
    "FPSO",
    "Semi-Sub/Prod/Perfuração",
    "Semi-Sub/Perfuração",
    "Fixa (Habitada)",
    "Semi-Sub/Produção",
    "Fixa (Rebombeio)",
}

MAPA_TIPOS = {
    tipo.casefold(): tipo
    for tipo in TIPOS_PERMITIDOS
}


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
    usecols=["unidade", "tipo"],
).rename(
    columns={
        "unidade": "nome_ativo",
        "tipo": "tipo_ativo",
    }
)

quantidade_original = len(df)

# Limpar espaços e preservar valores ausentes
for coluna in ["nome_ativo", "tipo_ativo"]:
    df[coluna] = (
        df[coluna]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

# ------------------------------------------------------------
# Excluir portos e estaleiros
# ------------------------------------------------------------

mascara_excluidos = (
    df["tipo_ativo"]
    .str.casefold()
    .isin(TIPOS_EXCLUIDOS)
)

quantidade_excluidos = int(mascara_excluidos.sum())
df = df.loc[~mascara_excluidos].copy()

# ------------------------------------------------------------
# Separar registros sem nome ou tipo
# ------------------------------------------------------------

mascara_pendentes = (
    df["nome_ativo"].isna()
    | df["tipo_ativo"].isna()
)

pendentes = df.loc[mascara_pendentes].copy()
df = df.loc[~mascara_pendentes].copy()

# ------------------------------------------------------------
# Validar e padronizar os tipos
# ------------------------------------------------------------

tipos_normalizados = df["tipo_ativo"].str.casefold()

mascara_tipo_invalido = ~tipos_normalizados.isin(MAPA_TIPOS)

if mascara_tipo_invalido.any():
    raise ValueError(
        "Tipos não permitidos em core.ativos. "
        "Nenhum cadastro será alterado:\n"
        + df.loc[
            mascara_tipo_invalido,
            ["nome_ativo", "tipo_ativo"],
        ].to_string(index=False)
    )

df["tipo_ativo"] = tipos_normalizados.map(MAPA_TIPOS)

# ------------------------------------------------------------
# Validar o tamanho dos campos
# ------------------------------------------------------------

mascara_tamanho_invalido = (
    df["nome_ativo"].str.len().gt(100)
    | df["tipo_ativo"].str.len().gt(50)
)

if mascara_tamanho_invalido.any():
    raise ValueError(
        "Valores maiores que o limite das colunas:\n"
        + df.loc[
            mascara_tamanho_invalido,
            ["nome_ativo", "tipo_ativo"],
        ].to_string(index=False)
    )

# ------------------------------------------------------------
# Detectar nomes equivalentes com tipos conflitantes
# ------------------------------------------------------------

df["_chave_nome"] = df["nome_ativo"].str.casefold()

tipos_por_nome = (
    df.groupby("_chave_nome")["tipo_ativo"]
    .nunique()
)

chaves_conflitantes = tipos_por_nome[
    tipos_por_nome.gt(1)
].index

if len(chaves_conflitantes) > 0:
    raise ValueError(
        "Um mesmo ativo aparece com tipos diferentes no Excel:\n"
        + df.loc[
            df["_chave_nome"].isin(chaves_conflitantes),
            ["nome_ativo", "tipo_ativo"],
        ].to_string(index=False)
    )

# ------------------------------------------------------------
# Remover duplicidades equivalentes
# ------------------------------------------------------------

quantidade_antes = len(df)

df = df.drop_duplicates(
    subset="_chave_nome",
    keep="first",
).copy()

quantidade_duplicados = quantidade_antes - len(df)

print("=" * 70)
print("CADASTRO DE ATIVOS — core.ativos")
print("=" * 70)

print(f"Registros no Excel: {quantidade_original}")
print(f"Portos e estaleiros excluídos: {quantidade_excluidos}")
print(f"Registros pendentes: {len(pendentes)}")
print(f"Duplicidades removidas: {quantidade_duplicados}")
print(f"Ativos válidos: {len(df)}")

if not pendentes.empty:
    print("\nPendentes por falta de nome ou tipo:")
    print(pendentes.to_string(index=False))

if df.empty:
    raise ValueError(
        "Nenhum ativo válido encontrado. "
        "O banco não será alterado."
    )


# ============================================================
# VARIÁVEIS DE AMBIENTE E CONEXÃO
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
# COMANDOS DE INSERÇÃO E ATUALIZAÇÃO
# ============================================================

sql_insert = text("""
    INSERT INTO core.ativos (
        nome_ativo,
        tipo_ativo
    )
    VALUES (
        :nome_ativo,
        :tipo_ativo
    )
    RETURNING id_ativo;
""")

sql_update = text("""
    UPDATE core.ativos
    SET
        nome_ativo = :nome_ativo,
        tipo_ativo = :tipo_ativo
    WHERE id_ativo = :id_ativo;
""")


# ============================================================
# CARGA DO CADASTRO
# ============================================================

inseridos = 0
atualizados = 0
inalterados = 0

try:
    with engine.begin() as conexao:

        # Serializar cargas e manter o cadastro estável
        conexao.execute(
            text("""
                LOCK TABLE core.ativos
                IN SHARE ROW EXCLUSIVE MODE;
            """)
        )

        ativos_banco = conexao.execute(
            text("""
                SELECT
                    id_ativo,
                    nome_ativo,
                    tipo_ativo
                FROM core.ativos;
            """)
        ).mappings().all()

        mapa_ativos = {}

        for ativo in ativos_banco:
            chave = ativo["nome_ativo"].strip().casefold()

            if chave in mapa_ativos:
                raise ValueError(
                    "Nomes equivalentes duplicados em core.ativos: "
                    f"{ativo['nome_ativo']}. "
                    "Corrija os cadastros antes da carga."
                )

            mapa_ativos[chave] = dict(ativo)

        registros = df[
            ["nome_ativo", "tipo_ativo"]
        ].to_dict(orient="records")

        for registro in registros:
            chave = registro["nome_ativo"].casefold()
            ativo_existente = mapa_ativos.get(chave)

            # ----------------------------------------------------
            # Ativo existente: atualizar mantendo o ID
            # ----------------------------------------------------

            if ativo_existente is not None:
                houve_alteracao = (
                    ativo_existente["nome_ativo"]
                    != registro["nome_ativo"]
                    or ativo_existente["tipo_ativo"]
                    != registro["tipo_ativo"]
                )

                if houve_alteracao:
                    conexao.execute(
                        sql_update,
                        {
                            "id_ativo": ativo_existente["id_ativo"],
                            **registro,
                        },
                    )

                    atualizados += 1

                    mapa_ativos[chave] = {
                        "id_ativo": ativo_existente["id_ativo"],
                        **registro,
                    }
                else:
                    inalterados += 1

            # ----------------------------------------------------
            # Ativo novo: inserir e gerar um novo ID
            # ----------------------------------------------------

            else:
                novo_id = conexao.execute(
                    sql_insert,
                    registro,
                ).scalar_one()

                mapa_ativos[chave] = {
                    "id_ativo": novo_id,
                    **registro,
                }

                inseridos += 1

        quantidade_banco = conexao.execute(
            text("""
                SELECT COUNT(*)
                FROM core.ativos;
            """)
        ).scalar_one()

    # A transação já foi confirmada neste ponto
    print("\n" + "=" * 70)
    print("CARGA CONCLUÍDA COM SUCESSO")
    print("=" * 70)

    print(f"Novos ativos inseridos: {inseridos}")
    print(f"Ativos atualizados: {atualizados}")
    print(f"Ativos sem alterações: {inalterados}")
    print(f"Total em core.ativos: {quantidade_banco}")

except Exception:
    print(
        "\nA carga falhou. Nenhuma alteração desta execução "
        "foi confirmada no banco."
    )
    raise

finally:
    engine.dispose()