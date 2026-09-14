from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE = Path(__file__).resolve().parents[1]

EMPRESAS = ["cbo", "bram", "starnav"]

ARQUIVO_ORIGEM = (
    BASE
    / "dados"
    / "SURVEY_VESSELS"
    / "SURVEY_VESSELS_20260803_manha.xlsx"
)

# Cabeçalho no arquivo de origem -> cabeçalho no arquivo destino
MAPEAMENTO_COLUNAS = {
    "data": "data_consulta",
    "hora": "hora_consulta",
    "latitude": "latitude",
    "longitude": "longitude",
    "data reportada": "data_reportada",
    "hora reportada": "hora_reportada",
    "status": "status",
}

# Colunas que determinam se um registro já existe.
# O status não participa porque pode sofrer pequenas variações
# sem que isso represente uma nova posição AIS.
CHAVE_DUPLICIDADE = [
    "data_consulta",
    "hora_consulta",
    "latitude",
    "longitude",
    "data_reportada",
    "hora_reportada",
]


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(valor):
    if valor is None or pd.isna(valor):
        return ""

    return str(valor).strip().lower()


def normalizar_nome_aba(valor):
    if valor is None or pd.isna(valor):
        return ""

    return str(valor).strip().upper()


def normalizar_data(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, pd.Timestamp):
        return valor.date().isoformat()

    if isinstance(valor, datetime):
        return valor.date().isoformat()

    if isinstance(valor, date):
        return valor.isoformat()

    convertido = pd.to_datetime(
        valor,
        dayfirst=True,
        errors="coerce",
    )

    if pd.isna(convertido):
        return normalizar_texto(valor)

    return convertido.date().isoformat()


def normalizar_hora(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%H:%M:%S")

    if isinstance(valor, datetime):
        return valor.strftime("%H:%M:%S")

    if isinstance(valor, time):
        return valor.strftime("%H:%M:%S")

    # Excel pode armazenar horas como fração de um dia.
    if isinstance(valor, (int, float)):
        segundos = round(float(valor) * 24 * 60 * 60)
        segundos = segundos % (24 * 60 * 60)

        horas = segundos // 3600
        minutos = (segundos % 3600) // 60
        segundos = segundos % 60

        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    texto = str(valor).strip()

    convertido = pd.to_datetime(
        texto,
        errors="coerce",
    )

    if not pd.isna(convertido):
        return convertido.strftime("%H:%M:%S")

    return texto


def normalizar_coordenada(valor):
    if valor is None or pd.isna(valor):
        return None

    try:
        # Seis casas decimais representam aproximadamente 11 cm.
        return round(float(valor), 6)
    except (TypeError, ValueError):
        return normalizar_texto(valor)


def normalizar_valor_chave(nome_coluna, valor):
    if nome_coluna in {"data_consulta", "data_reportada"}:
        return normalizar_data(valor)

    if nome_coluna in {"hora_consulta", "hora_reportada"}:
        return normalizar_hora(valor)

    if nome_coluna in {"latitude", "longitude"}:
        return normalizar_coordenada(valor)

    return normalizar_texto(valor)


def converter_valor_excel(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()

    return valor


# ============================================================
# CABEÇALHOS
# ============================================================

def obter_cabecalhos_dataframe(dataframe):
    return {
        normalizar_texto(coluna): coluna
        for coluna in dataframe.columns
    }


def obter_cabecalhos_planilha(ws):
    cabecalhos = {}

    for numero_coluna in range(1, ws.max_column + 1):
        valor = ws.cell(
            row=1,
            column=numero_coluna,
        ).value

        if valor is not None:
            cabecalhos[normalizar_texto(valor)] = numero_coluna

    return cabecalhos


# ============================================================
# CHAVE DE DUPLICIDADE
# ============================================================

def criar_chave_registro(registro):
    """
    Recebe um dicionário no formato:
    {
        "data_consulta": valor,
        "hora_consulta": valor,
        ...
    }
    """
    return tuple(
        normalizar_valor_chave(
            nome_coluna,
            registro.get(nome_coluna),
        )
        for nome_coluna in CHAVE_DUPLICIDADE
    )


def carregar_chaves_existentes(ws, cabecalhos_destino):
    """
    Lê os registros já existentes na aba e monta um conjunto
    de chaves para pesquisa rápida.
    """
    chaves = set()

    for numero_linha in range(2, ws.max_row + 1):
        registro = {
            nome_coluna: ws.cell(
                row=numero_linha,
                column=cabecalhos_destino[nome_coluna],
            ).value
            for nome_coluna in CHAVE_DUPLICIDADE
        }

        chave = criar_chave_registro(registro)

        # Evita considerar linhas totalmente vazias.
        if any(valor is not None for valor in chave):
            chaves.add(chave)

    return chaves


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_empresa(empresa):
    arquivo_destino = (
        BASE
        / "dados"
        / f"SURVEY_{empresa.upper()}.xlsx"
    )

    print()
    print("=" * 70)
    print(f"EMPRESA: {empresa.upper()}")
    print("=" * 70)

    if not ARQUIVO_ORIGEM.exists():
        raise FileNotFoundError(
            f"Arquivo de origem não encontrado: {ARQUIVO_ORIGEM}"
        )

    if not arquivo_destino.exists():
        raise FileNotFoundError(
            f"Arquivo de destino não encontrado: {arquivo_destino}"
        )

    origem = pd.read_excel(
        ARQUIVO_ORIGEM,
        sheet_name=empresa,
    )

    if origem.empty:
        print("A planilha de origem está vazia.")
        return

    cabecalhos_origem = obter_cabecalhos_dataframe(origem)

    colunas_ausentes = [
        coluna
        for coluna in MAPEAMENTO_COLUNAS
        if coluna not in cabecalhos_origem
    ]

    if colunas_ausentes:
        raise ValueError(
            "Colunas ausentes no arquivo de origem: "
            + ", ".join(colunas_ausentes)
        )

    wb = load_workbook(arquivo_destino)

    # Guarda os dados de cada aba para não precisar reler
    # todas as linhas para cada registro.
    cache_abas = {}

    inseridos = 0
    duplicados = 0
    abas_nao_encontradas = set()
    abas_invalidas = set()

    for indice, linha in origem.iterrows():
        numero_linha_origem = indice + 2

        # A primeira coluna deve conter o nome da embarcação.
        aba_destino = normalizar_nome_aba(linha.iloc[0])

        if not aba_destino:
            print(
                f"Linha {numero_linha_origem}: "
                "nome da embarcação vazio."
            )
            continue

        if aba_destino not in wb.sheetnames:
            abas_nao_encontradas.add(aba_destino)
            print(
                f"Linha {numero_linha_origem}: "
                f"aba '{aba_destino}' não encontrada."
            )
            continue

        # Prepara a aba apenas na primeira vez que ela aparece.
        if aba_destino not in cache_abas:
            ws = wb[aba_destino]
            cabecalhos_destino = obter_cabecalhos_planilha(ws)

            colunas_destino_necessarias = set(
                MAPEAMENTO_COLUNAS.values()
            )

            colunas_destino_ausentes = (
                colunas_destino_necessarias
                - set(cabecalhos_destino)
            )

            if colunas_destino_ausentes:
                abas_invalidas.add(aba_destino)

                print(
                    f"Aba '{aba_destino}' sem os cabeçalhos: "
                    + ", ".join(
                        sorted(colunas_destino_ausentes)
                    )
                )

                continue

            chaves_existentes = carregar_chaves_existentes(
                ws,
                cabecalhos_destino,
            )

            cache_abas[aba_destino] = {
                "ws": ws,
                "cabecalhos": cabecalhos_destino,
                "chaves": chaves_existentes,
            }

        if aba_destino in abas_invalidas:
            continue

        dados_aba = cache_abas[aba_destino]

        ws = dados_aba["ws"]
        cabecalhos_destino = dados_aba["cabecalhos"]
        chaves_existentes = dados_aba["chaves"]

        # Monta o registro usando os nomes das colunas de destino.
        registro = {}

        for coluna_origem, coluna_destino in MAPEAMENTO_COLUNAS.items():
            nome_original = cabecalhos_origem[coluna_origem]
            registro[coluna_destino] = linha[nome_original]

        chave = criar_chave_registro(registro)

        if chave in chaves_existentes:
            duplicados += 1

            print(
                f"Linha {numero_linha_origem}: "
                f"registro duplicado de '{aba_destino}' — ignorado."
            )

            continue

        linha_destino = ws.max_row + 1

        for nome_coluna, valor in registro.items():
            ws.cell(
                row=linha_destino,
                column=cabecalhos_destino[nome_coluna],
                value=converter_valor_excel(valor),
            )

        # Impede duplicação nas próximas linhas da mesma execução.
        chaves_existentes.add(chave)

        inseridos += 1

        print(
            f"Linha {numero_linha_origem}: "
            f"'{aba_destino}' inserido na linha {linha_destino}."
        )

    wb.save(arquivo_destino)
    wb.close()

    print()
    print(f"Arquivo atualizado: {arquivo_destino}")
    print(f"Novos registros inseridos: {inseridos}")
    print(f"Registros duplicados ignorados: {duplicados}")
    print(f"Abas não encontradas: {len(abas_nao_encontradas)}")

    if abas_nao_encontradas:
        print(
            "Embarcações sem aba: "
            + ", ".join(sorted(abas_nao_encontradas))
        )


def main():
    inicio = datetime.now()
    empresas_com_erro = []

    print("=" * 70)
    print("COMBINADOR DE DADOS — SURVEY VESSELS")
    print("=" * 70)
    print(f"Origem: {ARQUIVO_ORIGEM}")

    for empresa in EMPRESAS:
        try:
            processar_empresa(empresa)
        except Exception as erro:
            empresas_com_erro.append(empresa.upper())
            print(f"Erro ao processar {empresa.upper()}: {erro}")

    fim = datetime.now()

    print()
    print("=" * 70)
    print("PROCESSAMENTO FINALIZADO")
    print("=" * 70)
    print(f"Novas posições gravadas em {fim - inicio}.")

    if empresas_com_erro:
        print(
            "Empresas com erro: "
            + ", ".join(empresas_com_erro)
        )
    else:
        print("Todas as empresas foram processadas com sucesso.")


if __name__ == "__main__":
    main()