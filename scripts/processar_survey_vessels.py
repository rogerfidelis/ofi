# -*- coding: utf-8 -*-
"""
OFI - Preparação, validação e gravação de surveys de embarcações.
Fluxo seguro: --preparar gera CSVs para transcrição/revisão; --aplicar
só grava CSVs completos e válidos, criando backup e verificando a gravação.
Não faz OCR/visão automaticamente: não inventa valores que não consegue ler.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

BASE = Path(__file__).resolve().parents[1]
PASTA_IMAGENS = Path(r"C:\Users\roger\projetos\print")
PASTA_EXCEL = BASE / "dados" / "SURVEY_VESSELS"
PASTA_REVISAO = PASTA_EXCEL / "revisao_survey"
PASTA_BACKUP = PASTA_EXCEL / "backups_survey"
ABA = "bram"
EMBARCACOES = [
    "bram atlas", "bram bahia", "bram belem", "bram brasil",
    "bram brasilia", "bram bravo", "bram breeze", "bram buck",
    "bram buzios", "bram hero",
]
CAMPOS = ["embarcacao", "lat", "lon", "data_hora_utc", "status"]
STATUS_CONHECIDOS = {
    "underway", "underway using engine", "underway by sail", "stopped",
    "moored", "at anchor", "restricted manoeuvrability",
    "not under command", "constrained by her draught", "engaged in fishing",
    "aground", "unknown",
}


def data_captura(nome_imagem: str) -> datetime:
    # Nome esperado: Captura de tela YYYY-MM-DD HHMMSS.png
    parte = nome_imagem.removeprefix("Captura de tela ").removesuffix(".png")
    return datetime.strptime(parte, "%Y-%m-%d %H%M%S").replace(second=0, microsecond=0)


def pares_arquivos():
    imagens = sorted(PASTA_IMAGENS.glob("Captura de tela *.png"))
    encontrados = []
    sem_planilha = []
    for imagem in imagens:
        try:
            captura = data_captura(imagem.name)
        except ValueError:
            continue
        nome_excel = f"tabela {captura.strftime('%Y-%m-%d %H%M')}.xlsx"
        # Tenta primeiro o nome completo do timestamp, sem segundos (padrão usado nas tabelas).
        excel = PASTA_EXCEL / nome_excel
        if not excel.exists():
            # Mantém os segundos do nome original se houver uma convenção diferente.
            nome_original = imagem.name.replace("Captura de tela", "tabela").replace(".png", ".xlsx")
            excel = PASTA_EXCEL / nome_original
        if excel.exists() and not excel.name.startswith("~$"):
            encontrados.append((imagem, excel, captura))
        else:
            sem_planilha.append(imagem.name)
    return encontrados, sem_planilha


def criar_csv_revisao(imagem: Path, excel: Path, captura: datetime):
    PASTA_REVISAO.mkdir(parents=True, exist_ok=True)
    destino = PASTA_REVISAO / f"{excel.stem}_revisao.csv"
    if destino.exists():
        return destino, "já existe; preservado"
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        for nome in EMBARCACOES:
            writer.writerow({
                "embarcacao": nome, "lat": "", "lon": "",
                "data_hora_utc": "", "status": "",
            })
    return destino, "modelo criado"


def parse_float(valor, campo):
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (ValueError, TypeError):
        raise ValueError(f"{campo} não é numérico: {valor!r}")
    return numero


def validar_csv(caminho: Path):
    with caminho.open("r", newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f))
    if len(linhas) != len(EMBARCACOES):
        raise ValueError(f"{caminho.name}: esperadas 10 linhas; encontradas {len(linhas)}")
    nomes = [str(r.get("embarcacao", "")).strip().lower() for r in linhas]
    if nomes != EMBARCACOES:
        raise ValueError(f"{caminho.name}: embarcações ausentes, duplicadas ou fora da ordem prevista")
    registros = []
    for n, r in enumerate(linhas, start=2):
        lat = parse_float(r.get("lat"), f"linha {n} latitude")
        lon = parse_float(r.get("lon"), f"linha {n} longitude")
        if not -90 <= lat <= 90:
            raise ValueError(f"{caminho.name}, linha {n}: latitude fora de -90..90")
        if not -180 <= lon <= 180:
            raise ValueError(f"{caminho.name}, linha {n}: longitude fora de -180..180")
        raw_dt = str(r.get("data_hora_utc", "")).strip()
        if not raw_dt:
            raise ValueError(f"{caminho.name}, linha {n}: data_hora_utc vazia")
        try:
            dt_utc = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{caminho.name}, linha {n}: data_hora_utc inválida; use YYYY-MM-DD HH:MM")
        if dt_utc.tzinfo is not None:
            dt_utc = dt_utc.replace(tzinfo=None)
        dt_local = dt_utc - timedelta(hours=3)
        status = str(r.get("status", "")).strip()
        if not status:
            raise ValueError(f"{caminho.name}, linha {n}: status vazio")
        if status.lower() not in STATUS_CONHECIDOS:
            raise ValueError(f"{caminho.name}, linha {n}: status não reconhecido: {status!r}")
        registros.append((r["embarcacao"].strip(), lat, lon, dt_local, status))
    return registros


def aplicar_csv(caminho_csv: Path, excel: Path, captura: datetime, simular=False):
    registros = validar_csv(caminho_csv)
    wb = load_workbook(excel)
    try:
        if ABA not in wb.sheetnames:
            raise ValueError(f"Aba '{ABA}' não encontrada em {excel.name}")
        ws = wb[ABA]
        cabecalhos = [str(ws.cell(1, c).value or "").strip().lower() for c in range(1, ws.max_column + 1)]
        if cabecalhos[:8] != ["embarcacao", "data", "hora", "lat", "lon", "data reportada", "hora reportada", "status"]:
            raise ValueError(f"Cabeçalhos inesperados em {excel.name}: {cabecalhos[:8]}")
        # Backup antes de qualquer gravação.
        if simular:
            return f"SIMULAÇÃO válida: {excel.name} ({len(registros)} registros)"
        PASTA_BACKUP.mkdir(parents=True, exist_ok=True)
        backup = PASTA_BACKUP / f"{excel.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        shutil.copy2(excel, backup)
        # As dez embarcações ocupam as linhas 2 a 11, conforme o layout atual.
        for i, (nome, lat, lon, dt_local, status) in enumerate(registros, start=2):
            ws.cell(i, 2, captura.strftime("%Y-%m-%d %H:%M"))
            ws.cell(i, 3, nome.upper())
            ws.cell(i, 4, lat)
            ws.cell(i, 5, lon)
            ws.cell(i, 6, dt_local.strftime("%Y-%m-%d %H:%M"))
            ws.cell(i, 7, None)
            ws.cell(i, 8, status)
        wb.save(excel)
    finally:
        wb.close()
    # Reabre e verifica que os campos escritos correspondem aos dados validados.
    check = load_workbook(excel, read_only=True, data_only=True)
    try:
        ws = check[ABA]
        for i, (nome, lat, lon, dt_local, status) in enumerate(registros, start=2):
            if str(ws.cell(i, 3).value).strip().lower() != nome.lower():
                raise RuntimeError(f"Verificação pós-gravação falhou: {excel.name}, linha {i}, embarcação")
            if abs(float(ws.cell(i, 4).value) - lat) > 1e-7 or abs(float(ws.cell(i, 5).value) - lon) > 1e-7:
                raise RuntimeError(f"Verificação pós-gravação falhou: {excel.name}, linha {i}, coordenadas")
            if str(ws.cell(i, 6).value) != dt_local.strftime("%Y-%m-%d %H:%M"):
                raise RuntimeError(f"Verificação pós-gravação falhou: {excel.name}, linha {i}, horário")
            if str(ws.cell(i, 8).value).strip() != status:
                raise RuntimeError(f"Verificação pós-gravação falhou: {excel.name}, linha {i}, status")
    finally:
        check.close()
    return f"OK: {excel.name} | 10 registros | backup: {backup.name}"


def main():
    parser = argparse.ArgumentParser(description="Preparar, validar e gravar surveys OFI com segurança.")
    parser.add_argument("--preparar", action="store_true", help="cria CSVs para transcrição/revisão")
    parser.add_argument("--validar", action="store_true", help="valida CSVs preenchidos sem gravar Excel")
    parser.add_argument("--aplicar", action="store_true", help="valida, faz backup e grava os CSVs válidos")
    parser.add_argument("--simular", action="store_true", help="com --aplicar, valida sem alterar Excel")
    args = parser.parse_args()
    if sum([args.preparar, args.validar, args.aplicar]) != 1:
        parser.error("Escolha exatamente uma opção: --preparar, --validar ou --aplicar")
    pares, sem_planilha = pares_arquivos()
    print(f"Imagens com planilha correspondente: {len(pares)}")
    if sem_planilha:
        print(f"Imagens sem planilha correspondente: {len(sem_planilha)}")
        for nome in sem_planilha:
            print(f"  SEM PAR: {nome}")
    erros = 0
    for imagem, excel, captura in pares:
        csv_path = PASTA_REVISAO / f"{excel.stem}_revisao.csv"
        if args.preparar:
            csv_path, msg = criar_csv_revisao(imagem, excel, captura)
            print(f"{msg}: {csv_path.name}")
            continue
        if not csv_path.exists():
            erros += 1
            print(f"PENDENTE: não existe CSV de revisão para {excel.name}; execute --preparar")
            continue
        try:
            if args.validar:
                validar_csv(csv_path)
                print(f"VÁLIDO: {csv_path.name}")
            else:
                print(aplicar_csv(csv_path, excel, captura, simular=args.simular))
        except Exception as exc:
            erros += 1
            print(f"ERRO: {csv_path.name}: {exc}")
    print(f"\nConcluído. Pares: {len(pares)} | Erros/pendências: {erros}")
    if erros:
        sys.exit(2)


if __name__ == "__main__":
    main()
