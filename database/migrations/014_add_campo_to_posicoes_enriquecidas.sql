-- ============================================================
-- OFI - Migration 014
-- Identifica o campo petrolífero que contém cada posição da embarcação.
-- Usa a geometria core.campos.geom (EPSG:4674).
-- ============================================================

ALTER TABLE analytics.posicoes_enriquecidas
ADD COLUMN IF NOT EXISTS campo VARCHAR(150);

-- Preenche também os registros já existentes.
-- Posições fora de qualquer polígono permanecem com campo = NULL.
UPDATE analytics.posicoes_enriquecidas p
SET campo = (
    SELECT c.nome
    FROM core.campos c
    WHERE ST_Covers(
        c.geom,
        ST_Transform(
            ST_SetSRID(
                ST_MakePoint(
                    p.longitude::double precision,
                    p.latitude::double precision
                ),
                4326
            ),
            ST_SRID(c.geom)
        )
    )
    ORDER BY c.id_campo
    LIMIT 1
);
