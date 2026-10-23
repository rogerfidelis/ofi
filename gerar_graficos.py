"""Orquestrador OFI. Salve este arquivo na raiz do projeto ofi.

Execute no ambiente do projeto: python gerar_graficos.py
Os scripts rodam em sequencia, sem argumentos, com a raiz como pasta de trabalho.
Uma falha interrompe a sequencia; arquivos ja gerados nao sao desfeitos.
"""

from pathlib import Path
import subprocess
import sys
from time import perf_counter


RAIZ = Path(__file__).resolve().parent
SCRIPTS = (
    "graficos/gerar_campo_atendimento.py",
    "graficos/gerar_distancia_acumulada.py",
    "graficos/gerar_gantt_atendimento.py",
    "graficos/gerar_status_navegacao.py",
)


def main():
    faltantes = [script for script in SCRIPTS if not (RAIZ / script).is_file()]
    if faltantes:
        print("ERRO: arquivos nao encontrados:", flush=True)
        for script in faltantes:
            print(f"  {RAIZ / script}", flush=True)
        print("Salve gerar_graficos.py na raiz do projeto ofi.", flush=True)
        return 1

    inicio = perf_counter()
    print(f"OFI - Geracao dos graficos\nProjeto: {RAIZ}", flush=True)
    print(f"Python: {sys.executable}", flush=True)

    for numero, script in enumerate(SCRIPTS, start=1):
        print(f"\n[{numero}/{len(SCRIPTS)}] Executando {script}", flush=True)
        etapa = perf_counter()
        try:
            subprocess.run(
                [sys.executable, "-u", str(RAIZ / script)],
                cwd=RAIZ,
                check=True,
            )
        except subprocess.CalledProcessError as erro:
            print(
                f"\nERRO em {script} (codigo {erro.returncode}). "
                "Sequencia interrompida.",
                flush=True,
            )
            return 1
        except OSError as erro:
            print(f"\nNao foi possivel executar {script}: {erro}", flush=True)
            return 1
        except KeyboardInterrupt:
            print("\nExecucao interrompida pelo usuario.", flush=True)
            return 130
        print(f"Concluido em {perf_counter() - etapa:.1f} s.", flush=True)

    print(f"\nTodos os scripts concluidos em {perf_counter() - inicio:.1f} s.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
