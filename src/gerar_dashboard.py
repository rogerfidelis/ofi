from pathlib import Path
from html import escape
import re

import pandas as pd


# ============================================================
# CONFIGURAÇÃO
# ============================================================

EMPRESAS = ["bram", "starnav", "cbo"]

# Caminho relativo às páginas em dashboards/<empresa>/.
# Ajuste caso sua página inicial tenha outro nome.
LINK_HOME = "../../index.html"


# ============================================================
# FUNÇÕES
# ============================================================

def encontrar_base():
    """Localiza a raiz do projeto pela existência do template."""
    pasta_script = Path(__file__).resolve().parent

    for pasta in (pasta_script, *pasta_script.parents):
        template = pasta / "templates" / "dashboard_rev2.html"

        if template.is_file():
            return pasta

    raise FileNotFoundError(
        "Não foi encontrado templates/dashboard_rev2.html "
        "na pasta do script nem nas pastas superiores."
    )


def normalizar_nome(nome):
    """Mantém a mesma regra de nomes utilizada nos gráficos."""
    return (
        str(nome)
        .strip()
        .lower()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )


def preencher_template(template, valores):
    """Substitui os marcadores com escape adequado para HTML."""
    marcadores = set(re.findall(r"\{\{([A-Z_]+)\}\}", template))
    faltantes = marcadores - valores.keys()

    if faltantes:
        raise ValueError(
            "Marcadores sem configuração: "
            + ", ".join(sorted(faltantes))
        )

    return re.sub(
        r"\{\{([A-Z_]+)\}\}",
        lambda resultado: escape(
            str(valores[resultado.group(1)]),
            quote=True,
        ),
        template,
    )


# ============================================================
# GERAÇÃO
# ============================================================

def main():
    base = encontrar_base()

    caminho_template = base / "templates" / "dashboard_rev2.html"
    caminho_embarcacoes = (
        base / "dados" / "SURVEY_VESSELS" / "SURVEY_VESSELS.xlsx"
    )

    if not caminho_embarcacoes.is_file():
        raise FileNotFoundError(
            f"Arquivo de embarcações não encontrado: {caminho_embarcacoes}"
        )

    template = caminho_template.read_text(encoding="utf-8")
    vessels = pd.read_excel(caminho_embarcacoes)

    vessels.columns = (
        vessels.columns.astype(str).str.strip().str.lower()
    )

    colunas_faltantes = set(EMPRESAS) - set(vessels.columns)

    if colunas_faltantes:
        raise ValueError(
            "Empresas ausentes nas colunas do Excel: "
            + ", ".join(sorted(colunas_faltantes))
        )

    # Prepara e valida os nomes antes de gravar os dashboards.
    embarcacoes_por_empresa = {}

    for empresa in EMPRESAS:
        nomes = (
            vessels[empresa]
            .dropna()
            .astype(str)
            .str.strip()
        )
        nomes = nomes[nomes.ne("")].drop_duplicates()

        arquivos = {}

        for nome in nomes:
            arquivo = normalizar_nome(nome)

            if arquivo in arquivos:
                raise ValueError(
                    f"Nomes geram o mesmo arquivo em {empresa.upper()}: "
                    f"{arquivos[arquivo]!r} e {nome!r}."
                )

            arquivos[arquivo] = nome

        embarcacoes_por_empresa[empresa] = arquivos

    total = 0
    total_com_pendencias = 0

    print("=" * 70)
    print("GERAÇÃO DOS DASHBOARDS — OFI")
    print("=" * 70)
    print(f"Projeto: {base}")

    for empresa, embarcacoes in embarcacoes_por_empresa.items():
        saida = base / "dashboards" / empresa
        saida.mkdir(parents=True, exist_ok=True)

        print(f"\nEMPRESA: {empresa.upper()}")

        for arquivo, nome in embarcacoes.items():
            caminhos = {
                "MAPA": f"mapas/{empresa}/{arquivo}.html",
                "STATUS": (
                    f"graficos/status_navegacao/{empresa}/{arquivo}.html"
                ),
                "ATENDIMENTO": (
                    f"graficos/campo_atendimento/{empresa}/{arquivo}.html"
                ),
                "ACUMULADA": (
                    f"graficos/distancia_acumulada/{empresa}/{arquivo}.html"
                ),
                "GANTT": (
                    f"graficos/gantt_atendimento/{empresa}/{arquivo}.html"
                ),
                "LOGO": "imagens/logo_ofi.png",
            }

            valores = {
                "NOME": nome,
                "HOME": LINK_HOME,
                **{
                    marcador: f"../../{caminho}"
                    for marcador, caminho in caminhos.items()
                },
            }

            html = preencher_template(template, valores)

            destino = saida / f"{arquivo}.html"
            destino.write_text(html, encoding="utf-8")

            total += 1
            print(f"  Gerado: {destino.name}")

            ausentes = [
                caminho
                for caminho in caminhos.values()
                if not (base / caminho).is_file()
            ]

            if ausentes:
                total_com_pendencias += 1
                for caminho in ausentes:
                    print(f"    AVISO — arquivo não encontrado: {caminho}")

    print("\n" + "=" * 70)
    print(f"Dashboards gerados: {total}")
    print(f"Dashboards com arquivos ausentes: {total_com_pendencias}")
    print("=" * 70)


if __name__ == "__main__":
    main()