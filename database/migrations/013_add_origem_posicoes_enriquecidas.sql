ALTER TABLE analytics.posicoes_enriquecidas
ADD COLUMN IF NOT EXISTS id_empresa INTEGER;

ALTER TABLE analytics.posicoes_enriquecidas
ADD COLUMN IF NOT EXISTS id_posicao_origem BIGINT;

ALTER TABLE analytics.posicoes_enriquecidas
ADD CONSTRAINT posicoes_enriquecidas_empresa_fkey
FOREIGN KEY (id_empresa)
REFERENCES core.empresas (id_empresa);

CREATE UNIQUE INDEX IF NOT EXISTS
ux_posicoes_enriquecidas_origem
ON analytics.posicoes_enriquecidas (
    id_empresa,
    id_posicao_origem
);