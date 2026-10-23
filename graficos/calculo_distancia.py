"""Metodologia compartilhada de distância para os gráficos do OFI."""

import numpy as np
import pandas as pd

RAIO_TERRA_KM = 6371.0088


def preparar_e_calcular_distancias(df):
    """
    Valida posições, resolve duplicidade por horário reportado mantendo
    a coleta mais recente e calcula Haversine entre posições consecutivas.

    Requer: id_embarcacao, id_posicao, data_consulta, data_reportada,
    latitude e longitude. Retorna (DataFrame, inválidos, duplicados).
    """
    obrigatorias = [
        "id_embarcacao", "id_posicao", "data_consulta",
        "data_reportada", "latitude", "longitude",
    ]
    ausentes = sorted(set(obrigatorias) - set(df.columns))
    if ausentes:
        raise ValueError(f"Colunas obrigatórias ausentes: {ausentes}")

    dados = df.copy()
    for coluna in ("data_consulta", "data_reportada"):
        dados[coluna] = pd.to_datetime(dados[coluna], errors="coerce")
    for coluna in ("latitude", "longitude"):
        dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce")

    valido = (
        dados["data_reportada"].notna()
        & dados["latitude"].between(-90, 90)
        & dados["longitude"].between(-180, 180)
    )
    invalidos = int((~valido).sum())
    dados = dados.loc[valido].copy()

    # Para o mesmo horário reportado, mantém a coleta mais recente.
    dados = dados.sort_values(
        ["data_reportada", "data_consulta", "id_posicao"],
        na_position="first",
        kind="stable",
    )
    antes = len(dados)
    dados = dados.drop_duplicates(
        subset=["id_embarcacao", "data_reportada"], keep="last"
    )
    duplicados = antes - len(dados)

    dados = dados.sort_values(
        ["data_reportada", "data_consulta", "id_posicao"],
        kind="stable",
    ).reset_index(drop=True)

    lat = np.radians(dados["latitude"].to_numpy(dtype=float))
    lon = np.radians(dados["longitude"].to_numpy(dtype=float))
    segmentos = np.zeros(len(dados), dtype=float)

    if len(dados) > 1:
        dlat = np.diff(lat)
        dlon = np.diff(lon)
        a = (
            np.sin(dlat / 2.0) ** 2
            + np.cos(lat[:-1]) * np.cos(lat[1:])
            * np.sin(dlon / 2.0) ** 2
        )
        a = np.clip(a, 0.0, 1.0)
        segmentos[1:] = 2.0 * RAIO_TERRA_KM * np.arcsin(np.sqrt(a))

    dados["distancia_km"] = segmentos
    dados["distancia_acumulada_km"] = np.cumsum(segmentos)
    return dados, invalidos, duplicados
