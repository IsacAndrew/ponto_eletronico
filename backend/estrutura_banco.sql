ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS ultimo_acesso TIMESTAMPTZ;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS registros_ponto (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    usuario_nome TEXT,
    data_ponto DATE NOT NULL,
    tipo_batida TEXT NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL,
    UNIQUE (usuario_id, data_ponto, tipo_batida)
);

ALTER TABLE registros_ponto
ADD COLUMN IF NOT EXISTS usuario_nome TEXT;

UPDATE registros_ponto AS registro
SET usuario_nome = usuario.nome_completo
FROM usuarios AS usuario
WHERE registro.usuario_id = usuario.id
  AND registro.usuario_nome IS NULL;

ALTER TABLE registros_ponto
ALTER COLUMN usuario_id DROP NOT NULL;

ALTER TABLE registros_ponto
DROP CONSTRAINT IF EXISTS registros_ponto_usuario_id_fkey;

ALTER TABLE registros_ponto
ADD CONSTRAINT registros_ponto_usuario_id_fkey
FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS jornadas_usuarios (
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    entrada TIME NOT NULL,
    intervalo TIME NOT NULL,
    retorno_intervalo TIME NOT NULL,
    saida TIME NOT NULL,
    PRIMARY KEY (usuario_id, dia_semana)
);
