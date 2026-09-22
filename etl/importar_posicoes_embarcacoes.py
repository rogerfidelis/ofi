from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import os
import re
import unicodedata

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE = Path(__file__).resolve().parents[1]
PASTA_DADOS = BASE / "dados"

load_dotenv(BASE / ".env")

EMPRESAS = {
    "BRAM": 2,
    "CBO": 1,
    "STARNAV": 3,
}

COLUNAS_OBRIGATORIAS = {
    "data_consulta",
    "lat_a",
    "lon_a",
    "data_reportada",
    "status",
}

TAMANHO_LOTE = 1000


# ============================================================
# TRATAMENTO DOS VALORES
# ============================================================

def vazio(valor):
    return pd.isna(valor) or (
        isinstance(valor, str) and not valor.strip()
    )


def normalizar_nome(valor):
    texto = unicodedata.normalize("NFKD", str(valor))

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return re.sub(r"\s+", " ", texto.strip()).upper()


def converter_data(valor, obrigatoria=False):
    """
    Usa somente o conteúdo da coluna de data.
    Não consulta as colunas de hora do Excel.
    """
    if vazio(valor):
        if obrigatoria:
            raise ValueError("Data de consulta ausente.")
        return None

    if isinstance(valor, (int, float)):
        # Número serial de data do Excel.
        data = (
            pd.Timestamp("1899-12-30")
            + pd.to_timedelta(valor, unit="D")
        )
    elif isinstance(valor, (datetime, pd.Timestamp)):
        data = pd.Timestamp(valor)
    else:
        data = pd.to_datetime(
            str(valor).strip(),
            dayfirst=True,
            errors="raise",
        )

    if pd.isna(data):
        raise ValueError(f"Data inválida: {valor}")

    if data.tzinfo is not None:
        raise ValueError(
            f"Data com fuso horário: {valor}. "
            "É necessário definir a conversão antes da carga."
        )

    return data.to_pydatetime()


def converter_coordenada(valor, limite):
    if vazio(valor):
        raise ValueError("Coordenada ausente.")

    try:
        numero = Decimal(
            str(valor).strip().replace(",", ".")
        )
    except InvalidOperation as erro:
        raise ValueError(
            f"Coordenada inválida: {valor}"
        ) from erro

    if not numero.is_finite():
        raise ValueError(f"Coordenada inválida: {valor}")

    if not -limite <= numero <= limite:
        raise ValueError(
            f"Coordenada fora do intervalo "
            f"[-{limite}, {limite}]: {valor}"
        )

    return numero


def converter_status(valor):
    if vazio(valor):
        return None

    return str(valor).strip()


# ============================================================
# CONEXÃO COM O BANCO
# ============================================================

def criar_engine():
    variaveis = [
        "OFI_DB_HOST",
        "OFI_DB_PORT",
        "OFI_DB_NAME",
        "OFI_DB_USER",
        "OFI_DB_PASSWORD",
    ]

    faltantes = [
        nome
        for nome in variaveis
        if not os.getenv(nome)
    ]

    if faltantes:
        raise ValueError(
            "Configure estas variáveis no .env: "
            + ", ".join(faltantes)
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["OFI_DB_USER"],
        password=os.environ["OFI_DB_PASSWORD"],
        host=os.environ["OFI_DB_HOST"],
        port=int(os.environ["OFI_DB_PORT"]),
        database=os.environ["OFI_DB_NAME"],
    )

    return create_engine(
        url,
        pool_pre_ping=True,
    )


# ============================================================
# ARQUIVOS E CADASTRO DE EMBARCAÇÕES
# ============================================================

def localizar_arquivo(empresa):
    if not PASTA_DADOS.is_dir():
        raise FileNotFoundError(
            f"Pasta de dados não encontrada: {PASTA_DADOS}"
        )

    nome_esperado = f"SURVEY_{empresa}.xlsx"

    encontrados = [
        caminho
        for caminho in PASTA_DADOS.iterdir()
        if caminho.is_file()
        and caminho.name.lower() == nome_esperado.lower()
    ]

    if len(encontrados) != 1:
        raise ValueError(
            f"Esperado um arquivo {nome_esperado} "
            f"em {PASTA_DADOS}. "
            f"Encontrados: {len(encontrados)}."
        )

    return encontrados[0]


def montar_cadastro(conexao, empresa, id_empresa):
    registros = conexao.execute(
        text("""
            SELECT
                id_embarcacao,
                nome_embarcacao
            FROM core.embarcacoes
            WHERE id_empresa = :id_empresa
        """),
        {"id_empresa": id_empresa},
    ).mappings().all()

    if not registros:
        raise ValueError(
            f"Nenhuma embarcação cadastrada para {empresa}."
        )

    cadastro = {}
    prefixo = empresa + " "

    for registro in registros:
        nome_completo = normalizar_nome(
            registro["nome_embarcacao"]
        )
        id_embarcacao = registro["id_embarcacao"]

        nomes_aceitos = {nome_completo}

        # Exemplo: reconhece BRAM ATLAS e ATLAS.
        if nome_completo.startswith(prefixo):
            nomes_aceitos.add(
                nome_completo[len(prefixo):]
            )

        for nome in nomes_aceitos:
            if (
                nome in cadastro
                and cadastro[nome] != id_embarcacao
            ):
                raise ValueError(
                    f"Nome ambíguo em {empresa}: {nome}"
                )

            cadastro[nome] = id_embarcacao

    return cadastro


# ============================================================
# LEITURA E VALIDAÇÃO DO EXCEL
# ============================================================

def preparar_registros(conexao, empresa, id_empresa):
    arquivo = localizar_arquivo(empresa)

    cadastro = montar_cadastro(
        conexao,
        empresa,
        id_empresa,
    )

    registros = []

    print(f"\nEMPRESA: {empresa}")
    print(f"Arquivo: {arquivo}")

    with pd.ExcelFile(arquivo) as excel:
        for aba in excel.sheet_names:
            nome_aba = normalizar_nome(aba)

            if nome_aba == "POSICOES":
                continue

            if nome_aba not in cadastro:
                raise ValueError(
                    f"{empresa}: aba '{aba}' sem "
                    "correspondência em core.embarcacoes."
                )

            id_embarcacao = cadastro[nome_aba]

            df = pd.read_excel(
                excel,
                sheet_name=aba,
            )

            df.columns = [
                str(coluna).strip().lower()
                for coluna in df.columns
            ]

            if df.columns.duplicated().any():
                raise ValueError(
                    f"{empresa}/{aba}: "
                    "cabeçalhos duplicados."
                )

            faltantes = (
                COLUNAS_OBRIGATORIAS
                - set(df.columns)
            )

            if faltantes:
                raise ValueError(
                    f"{empresa}/{aba}: "
                    f"colunas ausentes: {sorted(faltantes)}"
                )

            # Ignora apenas linhas totalmente vazias.
            df = df.dropna(how="all")

            quantidade_aba = 0

            for indice, linha in df.iterrows():
                try:
                    registro = {
                        "id_embarcacao": id_embarcacao,
                        "data_consulta": converter_data(
                            linha["data_consulta"],
                            obrigatoria=True,
                        ),
                        "latitude": converter_coordenada(
                            linha["lat_a"],
                            limite=90,
                        ),
                        "longitude": converter_coordenada(
                            linha["lon_a"],
                            limite=180,
                        ),
                        "data_reportada": converter_data(
                            linha["data_reportada"],
                        ),
                        "status": converter_status(
                            linha["status"],
                        ),
                    }

                except Exception as erro:
                    raise ValueError(
                        f"{empresa}/{aba}, "
                        f"linha Excel {indice + 2}: {erro}"
                    ) from erro

                registros.append(registro)
                quantidade_aba += 1

            print(
                f"  {aba}: "
                f"ID {id_embarcacao} — "
                f"{quantidade_aba} posições"
            )

    # Remove duplicidades no próprio arquivo.
    registros_unicos = {}

    for registro in registros:
        chave = (
            registro["id_embarcacao"],
            registro["data_consulta"],
            registro["latitude"],
            registro["longitude"],
            registro["data_reportada"],
            registro["status"],
        )

        registros_unicos.setdefault(
            chave,
            registro,
        )

    print(f"Posições lidas: {len(registros)}")
    print(
        "Duplicidades no arquivo: "
        f"{len(registros) - len(registros_unicos)}"
    )

    return list(registros_unicos.values())


# ============================================================
# INSERÇÃO INCREMENTAL
# ============================================================

def inserir_registros(conexao, empresa, registros):
    tabela = f"raw.posicoes_{empresa.lower()}"

    # Bloqueia outras escritas durante a carga.
    # SELECT continua permitido.
    conexao.execute(
        text(f"LOCK TABLE {tabela} IN EXCLUSIVE MODE")
    )

    quantidade_antes = conexao.execute(
        text(f"SELECT COUNT(*) FROM {tabela}")
    ).scalar_one()

    comando = text(f"""
        INSERT INTO {tabela} (
            id_embarcacao,
            data_consulta,
            latitude,
            longitude,
            data_reportada,
            status
        )
        SELECT
            :id_embarcacao,
            :data_consulta,
            :latitude,
            :longitude,
            :data_reportada,
            :status
        WHERE NOT EXISTS (
            SELECT 1
            FROM {tabela} AS existente
            WHERE existente.id_embarcacao = :id_embarcacao

              AND existente.data_consulta
                  IS NOT DISTINCT FROM
                  CAST(:data_consulta AS timestamp)

              AND existente.latitude
                  IS NOT DISTINCT FROM
                  CAST(:latitude AS numeric)

              AND existente.longitude
                  IS NOT DISTINCT FROM
                  CAST(:longitude AS numeric)

              AND existente.data_reportada
                  IS NOT DISTINCT FROM
                  CAST(:data_reportada AS timestamp)

              AND existente.status
                  IS NOT DISTINCT FROM
                  CAST(:status AS varchar)
        )
        ON CONFLICT (
            id_embarcacao,
            data_consulta,
            latitude,
            longitude,
            data_reportada,
            status
        )
        DO NOTHING
    """)

    for inicio in range(
        0,
        len(registros),
        TAMANHO_LOTE,
    ):
        lote = registros[
            inicio:inicio + TAMANHO_LOTE
        ]

        conexao.execute(comando, lote)

    quantidade_depois = conexao.execute(
        text(f"SELECT COUNT(*) FROM {tabela}")
    ).scalar_one()

    inseridas = (
        quantidade_depois
        - quantidade_antes
    )

    return {
        "empresa": empresa,
        "inseridas": inseridas,
        "ja_existentes": len(registros) - inseridas,
        "total": quantidade_depois,
    }


# ============================================================
# EXECUÇÃO
# ============================================================

def main():
    print("=" * 65)
    print("IMPORTAÇÃO DE POSIÇÕES — BRAM, CBO E STARNAV")
    print("=" * 65)

    engine = criar_engine()

    try:
        resultados = []

        # As três cargas são confirmadas juntas.
        # Qualquer erro provoca rollback da execução.
        with engine.begin() as conexao:
            banco = conexao.execute(
                text("SELECT current_database()")
            ).scalar_one()

            print(f"\nConectado ao banco: {banco}")

            preparados = {}

            # Valida todos os arquivos antes das inserções.
            for empresa, id_empresa in EMPRESAS.items():
                preparados[empresa] = preparar_registros(
                    conexao,
                    empresa,
                    id_empresa,
                )

            for empresa, registros in preparados.items():
                resultado = inserir_registros(
                    conexao,
                    empresa,
                    registros,
                )

                resultados.append(resultado)

        print("\n" + "=" * 65)
        print("CARGA CONFIRMADA COM SUCESSO")
        print("=" * 65)

        for resultado in resultados:
            print(
                f"{resultado['empresa']}: "
                f"{resultado['inseridas']} novas | "
                f"{resultado['ja_existentes']} já existentes | "
                f"{resultado['total']} no banco"
            )

    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()

    except Exception:
        print(
            "\nA carga falhou. "
            "Nenhuma inserção desta execução "
            "foi confirmada no banco."
        )
        raise