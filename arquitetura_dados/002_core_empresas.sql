CREATE TABLE core.empresas (
    id_empresa INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_empresa VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO core.empresas (nome_empresa)
VALUES
    ('CBO'),
    ('BRAM'),
    ('STARNAV');

SELECT *
FROM core.empresas
ORDER BY id_empresa;