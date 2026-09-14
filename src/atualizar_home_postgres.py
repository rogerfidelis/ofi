"""Salve em OFI/src. Atualiza somente o bloco ESTATISTICAS do script.js.

Dependências: sqlalchemy psycopg2-binary python-dotenv.
Uso: python src/atualizar_home_postgres.py --inicio 2026-07-16 --fim 2026-09-13
Datas seguem o fuso já gravado em data_consulta (timestamp sem fuso).
Distância: segmentos Haversine cujas duas posições estão dentro do período;
primeira posição não soma distância. Não representa a rota real entre coletas.
Campos: inferência por ativo, evidência >= limiar e ausência de local fixo.
Opcional: --classificacao VALOR_EXATO restringe à classificação da view.
"""
from pathlib import Path
from datetime import date, datetime, time, timedelta
import argparse
import json
import os
import re
import shutil
import tempfile

BASE = Path(__file__).resolve().parent
if BASE.name.lower() == "src":
    BASE = BASE.parent

SQL_DISTANCIA = """
WITH pontos AS (
    SELECT DISTINCT p.id_embarcacao, p.data_consulta,
        p.latitude::double precision AS lat,
        p.longitude::double precision AS lon
    FROM analytics.v_posicoes_embarcacoes p
    JOIN core.embarcacoes e USING (id_embarcacao)
    JOIN core.empresas c ON c.id_empresa = e.id_empresa
    WHERE UPPER(TRIM(c.nome_empresa)) IN ('BRAM','CBO','STARNAV')
      AND p.data_consulta >= :inicio AND p.data_consulta < :fim
), conflitos AS (
    SELECT id_embarcacao, data_consulta FROM pontos
    GROUP BY id_embarcacao, data_consulta HAVING COUNT(*) > 1
), sequencia AS (
    SELECT *, LAG(lat) OVER w AS lat_ant, LAG(lon) OVER w AS lon_ant
    FROM pontos
    WINDOW w AS (PARTITION BY id_embarcacao ORDER BY data_consulta)
), trechos AS (
    SELECT *, CASE
        WHEN lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180
         AND lat_ant BETWEEN -90 AND 90 AND lon_ant BETWEEN -180 AND 180
        THEN 2 * 6371.0088 * ASIN(SQRT(LEAST(1.0, GREATEST(0.0,
            POWER(SIN(RADIANS(lat-lat_ant)/2),2)
            + COS(RADIANS(lat_ant))*COS(RADIANS(lat))
            * POWER(SIN(RADIANS(lon-lon_ant)/2),2)) )))
        ELSE 0 END AS km
    FROM sequencia
)
SELECT COALESCE(SUM(km),0) AS km, COUNT(*) AS pontos,
       (SELECT COUNT(*) FROM conflitos) AS conflitos,
       COUNT(*) FILTER (WHERE lat IS NULL OR lon IS NULL
          OR NOT (lat BETWEEN -90 AND 90) OR NOT (lon BETWEEN -180 AND 180)) AS invalidos
FROM trechos
"""

SQL_CADASTRO = """
SELECT COUNT(DISTINCT e.id_embarcacao) AS psvs,
       COUNT(DISTINCT c.id_empresa) AS empresas
FROM core.embarcacoes e JOIN core.empresas c USING (id_empresa)
WHERE UPPER(TRIM(c.nome_empresa)) IN ('BRAM','CBO','STARNAV')
"""

SQL_CAMPOS = """
SELECT COUNT(DISTINCT p.id_campo)
FROM analytics.v_posicoes_classificadas p
JOIN core.embarcacoes e USING (id_embarcacao)
JOIN core.empresas c ON c.id_empresa = e.id_empresa
JOIN core.campos f ON f.id_campo = p.id_campo
WHERE UPPER(TRIM(c.nome_empresa)) IN ('BRAM','CBO','STARNAV')
  AND p.data_consulta >= :inicio AND p.data_consulta < :fim
  AND p.id_ativo IS NOT NULL
  AND p.id_local IS NULL
  AND p.evidencia_proximidade >= :limiar
"""


def conectar():
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL, make_url
    load_dotenv(BASE / '.env')
    url_texto = os.getenv('DATABASE_URL')
    if url_texto:
        url = make_url(url_texto)
        if url.drivername in ('postgres', 'postgresql'):
            url = url.set(drivername='postgresql+psycopg2')
    else:
        def env(*nomes, default=None):
            return next((os.environ[n] for n in nomes if os.getenv(n)), default)
        host = env('OFI_DB_HOST', 'PGHOST')
        usuario = env('OFI_DB_USER', 'PGUSER')
        banco = env('OFI_DB_NAME', 'OFI_DB_DATABASE', 'PGDATABASE')
        if not all((host, usuario, banco)):
            raise ValueError('Configure DATABASE_URL ou OFI_DB_HOST, OFI_DB_USER e OFI_DB_NAME no .env da raiz.')
        query = {}
        ssl = env('OFI_DB_SSLMODE', 'PGSSLMODE')
        if ssl:
            query['sslmode'] = ssl
        certificado = env('OFI_DB_SSLROOTCERT', 'PGSSLROOTCERT')
        if certificado:
            query['sslrootcert'] = certificado
        url = URL.create('postgresql+psycopg2', username=usuario,
            password=env('OFI_DB_PASSWORD', 'PGPASSWORD'), host=host,
            port=int(env('OFI_DB_PORT', 'PGPORT', default='5432')),
            database=banco, query=query)
    return create_engine(url, connect_args={'connect_timeout': 15},
                         isolation_level='REPEATABLE READ')


def atualizar_js(destino, valores):
    # Preserva animação e demais funcionalidades do JavaScript existente.
    original = destino.read_text(encoding='utf-8-sig')
    padrao = r'\bconst\s+ESTATISTICAS\s*=\s*\{[^{}]*\}\s*;'
    if len(re.findall(padrao, original)) != 1:
        raise ValueError('script.js deve conter exatamente um bloco const ESTATISTICAS = {...};')
    bloco = 'const ESTATISTICAS = ' + json.dumps(valores, ensure_ascii=False, indent=4, allow_nan=False) + ';'
    novo = re.sub(padrao, lambda _: bloco, original)
    backup = destino.with_name(destino.name + '.' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.bak')
    shutil.copy2(destino, backup)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent,
                                         suffix='.tmp', delete=False) as f:
            temporario = Path(f.name)
            f.write(novo)
        os.replace(temporario, destino)
    finally:
        if temporario and temporario.exists():
            temporario.unlink()
    print(f'Backup: {backup}')
    print(f'Atualizado: {destino}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inicio', type=date.fromisoformat, required=True)
    parser.add_argument('--fim', type=date.fromisoformat, required=True)
    parser.add_argument('--limiar', type=float, default=0.5)
    parser.add_argument('--classificacao', help='Valor exato de classificacao_operacional para os campos.')
    parser.add_argument('--script', type=Path, default=BASE / 'script.js')
    parser.add_argument('--somente-consultar', action='store_true')
    args = parser.parse_args()
    if args.fim < args.inicio:
        parser.error('A data final deve ser igual ou posterior à inicial.')
    if not 0 <= args.limiar <= 1:
        parser.error('O limiar deve estar entre 0 e 1.')
    if not args.somente_consultar and not args.script.is_file():
        parser.error(f'JavaScript não encontrado: {args.script}')
    from sqlalchemy import text
    params = {'inicio': datetime.combine(args.inicio, time.min),
              'fim': datetime.combine(args.fim + timedelta(days=1), time.min),
              'limiar': args.limiar}
    engine = conectar()
    try:
        with engine.connect() as conn, conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout = '120s'"))
            dist = conn.execute(text(SQL_DISTANCIA), params).mappings().one()
            if dist['conflitos']:
                raise ValueError(f"{dist['conflitos']} horários com coordenadas conflitantes. Corrija-os antes de calcular a distância.")
            if not dist['pontos']:
                raise ValueError('Nenhuma posição no período. script.js preservado.')
            if dist['invalidos']:
                raise ValueError(f"{dist['invalidos']} posições com coordenadas inválidas. script.js preservado.")
            cadastro = conn.execute(text(SQL_CADASTRO)).mappings().one()
            consulta_campos = SQL_CAMPOS
            if args.classificacao:
                categorias = conn.execute(text('SELECT DISTINCT classificacao_operacional FROM analytics.v_posicoes_classificadas')).scalars().all()
                if args.classificacao not in categorias:
                    raise ValueError(f'Classificação desconhecida. Valores disponíveis: {categorias}')
                consulta_campos += ' AND p.classificacao_operacional = :classificacao'
                params['classificacao'] = args.classificacao
            campos = conn.execute(text(consulta_campos), params).scalar_one()
            valores = {'km': round(float(dist['km']), 2),
                       'empresas': int(cadastro['empresas']),
                       'psvs': int(cadastro['psvs']), 'campos': int(campos)}
    finally:
        engine.dispose()
    print('=' * 65)
    print('HOME OFI — POSTGRESQL')
    print(f'Período por data_consulta: {args.inicio} a {args.fim} (inclusivo)')
    print(f"Posições únicas: {dist['pontos']}")
    print(json.dumps(valores, indent=4, ensure_ascii=False))
    print('Empresas/PSVs: cadastro BRAM, CBO e STARNAV, sem filtro temporal.')
    print('Campos: ativo associado, sem local fixo, evidência >=', args.limiar)
    print('Classificação adicional:', args.classificacao or 'nenhuma (proximidade inferida)')
    print('Distância estimada entre coletas; lacunas podem subestimar o percurso.')
    if not args.somente_consultar:
        atualizar_js(args.script, valores)


if __name__ == "__main__":
    from sqlalchemy.exc import SQLAlchemyError

    try:
        main()

    except SQLAlchemyError as erro:
        print("\nERRO DO POSTGRESQL")
        print("=" * 65)

        original = erro.orig
        diagnostico = getattr(original, "diag", None)

        print("Código SQLSTATE:", getattr(original, "pgcode", None))

        if diagnostico:
            print("Mensagem:", diagnostico.message_primary)

            if diagnostico.message_detail:
                print("Detalhe:", diagnostico.message_detail)

            if diagnostico.message_hint:
                print("Sugestão:", diagnostico.message_hint)
        else:
            print("Tipo:", type(original).__name__)

        print("\nNenhuma escrita foi feita no banco.")
        raise SystemExit(1)

    except Exception as erro:
        print(f"\nERRO ({type(erro).__name__}): {erro}")
        raise SystemExit(1)