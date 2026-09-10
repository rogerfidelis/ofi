-- ============================================================
-- OFI - Offshore Fleet Intelligence
-- Seed 002
-- Cadastro inicial de embarcações
-- Fonte: SURVEY_BRAM.xlsx, SURVEY_CBO.xlsx e SURVEY_STARNAV.xlsx
-- ============================================================


-- ============================================================
-- BRAM
-- ============================================================

INSERT INTO core.embarcacoes (nome_embarcacao, id_empresa)
SELECT v.nome_embarcacao, e.id_empresa
FROM (
    VALUES
        ('BRAM ATLAS'),
        ('BRAM BAHIA'),
        ('BRAM BELEM'),
        ('BRAM BRASIL'),
        ('BRAM BRASILIA'),
        ('BRAM BRAVO'),
        ('BRAM BREEZE'),
        ('BRAM BUCK'),
        ('BRAM BUZIOS'),
        ('BRAM HERO'),
        ('BRAM POWER'),
        ('BRAM RIO'),
        ('BRAM SPIRIT'),
        ('BRAM TITAN')
) AS v(nome_embarcacao)
CROSS JOIN core.empresas e
WHERE e.nome_empresa = 'BRAM'
ON CONFLICT (nome_embarcacao) DO NOTHING;


-- ============================================================
-- CBO
-- ============================================================

INSERT INTO core.embarcacoes (nome_embarcacao, id_empresa)
SELECT v.nome_embarcacao, e.id_empresa
FROM (
    VALUES
        ('CBO ALESSANDRA'),
        ('CBO ALIANCA'),
        ('CBO ANITA'),
        ('CBO ARPOADOR'),
        ('CBO CAMPOS'),
        ('CBO CAROLINA'),
        ('CBO COPACABANA'),
        ('CBO ENERGY'),
        ('CBO FLAMENGO'),
        ('CBO IPANEMA'),
        ('CBO ISABELLA'),
        ('CBO ITAJAI'),
        ('CBO MANOELLA'),
        ('CBO OCEANA'),
        ('CBO RENATA'),
        ('CBO RIO'),
        ('CBO SUPPORTER'),
        ('CBO VITORIA'),
        ('CBO WAVE'),
        ('CBO WISER'),
        ('DELTA CARDINAL'),
        ('DELTA COMMANDER')
) AS v(nome_embarcacao)
CROSS JOIN core.empresas e
WHERE e.nome_empresa = 'CBO'
ON CONFLICT (nome_embarcacao) DO NOTHING;


-- ============================================================
-- STARNAV
-- ============================================================

INSERT INTO core.embarcacoes (nome_embarcacao, id_empresa)
SELECT v.nome_embarcacao, e.id_empresa
FROM (
    VALUES
        ('STARNAV ANDROMEDA'),
        ('STARNAV AQUARIUS'),
        ('STARNAV AQUILA'),
        ('STARNAV CENTAURUS'),
        ('STARNAV CEPHEUS'),
        ('STARNAV CIRCINUS'),
        ('STARNAV CYGNUS'),
        ('STARNAV DELPHINUS'),
        ('STARNAV DRACO'),
        ('STARNAV HYDRA'),
        ('STARNAV LIBRA'),
        ('STARNAV PERSEUS'),
        ('STARNAV PHOENIX'),
        ('STARNAV REGULUS'),
        ('STARNAV TAURUS'),
        ('STARNAV URSUS'),
        ('STARNAV VOLANS')
) AS v(nome_embarcacao)
CROSS JOIN core.empresas e
WHERE e.nome_empresa = 'STARNAV'
ON CONFLICT (nome_embarcacao) DO NOTHING;