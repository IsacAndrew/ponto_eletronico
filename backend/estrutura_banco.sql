ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS ultimo_acesso TIMESTAMPTZ;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS quantidade_batidas SMALLINT;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS dias_trabalho_semana SMALLINT;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS registro_fora_unidade BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS funcao TEXT;

ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS rg TEXT;

UPDATE usuarios
SET rg = substring(digitos from 1 for 2) || '.' ||
         substring(digitos from 3 for 3) || '.' ||
         substring(digitos from 6 for 3) || '-' ||
         substring(digitos from 9 for 1)
FROM (
    SELECT id, regexp_replace(rg, '[^0-9]', '', 'g') AS digitos
    FROM usuarios
    WHERE rg IS NOT NULL
) AS cadastro
WHERE usuarios.id = cadastro.id
  AND length(cadastro.digitos) = 9
  AND usuarios.rg <> (
      substring(cadastro.digitos from 1 for 2) || '.' ||
      substring(cadastro.digitos from 3 for 3) || '.' ||
      substring(cadastro.digitos from 6 for 3) || '-' ||
      substring(cadastro.digitos from 9 for 1)
  );

CREATE UNIQUE INDEX IF NOT EXISTS usuarios_login_normalizado_uidx
ON usuarios (LOWER(BTRIM(login)));

CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_normalizado_uidx
ON usuarios (LOWER(BTRIM(email)))
WHERE email IS NOT NULL AND BTRIM(email) <> '';

ALTER TABLE usuarios
ALTER COLUMN email DROP NOT NULL,
ALTER COLUMN telefone DROP NOT NULL;

CREATE TABLE IF NOT EXISTS registros_ponto (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    usuario_nome TEXT,
    data_ponto DATE NOT NULL,
    tipo_batida TEXT NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL,
    UNIQUE (usuario_id, data_ponto, tipo_batida)
);

CREATE INDEX IF NOT EXISTS registros_ponto_data_usuario_idx
ON registros_ponto (data_ponto, usuario_id);

ALTER TABLE registros_ponto
ADD COLUMN IF NOT EXISTS usuario_nome TEXT;

ALTER TABLE registros_ponto
ADD COLUMN IF NOT EXISTS origem_registro TEXT NOT NULL DEFAULT 'site';

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
    intervalo TIME,
    retorno_intervalo TIME,
    saida TIME NOT NULL,
    PRIMARY KEY (usuario_id, dia_semana)
);

CREATE TABLE IF NOT EXISTS quantidades_batidas_semanais (
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    quantidade_batidas SMALLINT NOT NULL CHECK (quantidade_batidas IN (0, 2, 4)),
    PRIMARY KEY (usuario_id, dia_semana)
);

ALTER TABLE jornadas_usuarios
ALTER COLUMN intervalo DROP NOT NULL,
ALTER COLUMN retorno_intervalo DROP NOT NULL;

UPDATE usuarios
SET quantidade_batidas = CASE WHEN tipo_conta = 'Professor' THEN 2 ELSE 4 END
WHERE quantidade_batidas IS NULL;

UPDATE usuarios AS usuario
SET dias_trabalho_semana = COALESCE(
    NULLIF((SELECT COUNT(*) FROM jornadas_usuarios AS jornada
            WHERE jornada.usuario_id = usuario.id), 0), 5
)
WHERE dias_trabalho_semana IS NULL;

ALTER TABLE usuarios
ALTER COLUMN quantidade_batidas SET DEFAULT 4,
ALTER COLUMN quantidade_batidas SET NOT NULL,
ALTER COLUMN dias_trabalho_semana SET DEFAULT 5,
ALTER COLUMN dias_trabalho_semana SET NOT NULL;

CREATE TABLE IF NOT EXISTS configuracoes_sistema (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    marco_zero_latitude DOUBLE PRECISION,
    marco_zero_longitude DOUBLE PRECISION,
    marco_zero_endereco TEXT NOT NULL DEFAULT '',
    raio_ponto_metros SMALLINT NOT NULL DEFAULT 100
        CHECK (raio_ponto_metros BETWEEN 1 AND 100),
    qr_ponto_token TEXT,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE configuracoes_sistema
ADD COLUMN IF NOT EXISTS qr_ponto_token TEXT;

INSERT INTO configuracoes_sistema (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS conversas_suporte (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    usuario_nome TEXT NOT NULL,
    iniciada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS conversas_suporte_usuario_aberto_idx
ON conversas_suporte (usuario_id);

CREATE TABLE IF NOT EXISTS mensagens_suporte (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id BIGINT NOT NULL REFERENCES conversas_suporte(id) ON DELETE CASCADE,
    remetente_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    remetente_tipo TEXT NOT NULL CHECK (remetente_tipo IN ('Suporte', 'Usuario')),
    mensagem TEXT NOT NULL CHECK (char_length(mensagem) BETWEEN 1 AND 2000),
    enviada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispositivos_ponto (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_uso_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '365 days'
);
