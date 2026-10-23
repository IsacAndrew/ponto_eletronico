from threading import Lock

from .banco_dados import criar_conexao

_estrutura_pronta = False
_trava_estrutura = Lock()


def garantir_estrutura_jornada():
    global _estrutura_pronta
    if _estrutura_pronta:
        return
    with _trava_estrutura:
        if _estrutura_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS quantidade_batidas SMALLINT"
            )
            conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS dias_trabalho_semana SMALLINT"
            )
            conexao.execute(
                """
                UPDATE usuarios
                SET quantidade_batidas = CASE WHEN tipo_conta = 'Professor' THEN 2 ELSE 4 END
                WHERE quantidade_batidas IS NULL
                """
            )
            conexao.execute(
                """
                UPDATE usuarios AS usuario
                SET dias_trabalho_semana = COALESCE(
                    NULLIF((SELECT COUNT(*) FROM jornadas_usuarios AS jornada
                            WHERE jornada.usuario_id = usuario.id), 0), 5
                )
                WHERE dias_trabalho_semana IS NULL
                """
            )
            conexao.execute(
                "ALTER TABLE usuarios ALTER COLUMN quantidade_batidas SET DEFAULT 4"
            )
            conexao.execute(
                "ALTER TABLE usuarios ALTER COLUMN quantidade_batidas SET NOT NULL"
            )
            conexao.execute(
                "ALTER TABLE usuarios ALTER COLUMN dias_trabalho_semana SET DEFAULT 5"
            )
            conexao.execute(
                "ALTER TABLE usuarios ALTER COLUMN dias_trabalho_semana SET NOT NULL"
            )
            conexao.execute(
                "ALTER TABLE jornadas_usuarios ALTER COLUMN intervalo DROP NOT NULL"
            )
            conexao.execute(
                "ALTER TABLE jornadas_usuarios ALTER COLUMN retorno_intervalo DROP NOT NULL"
            )
            conexao.execute("DROP TABLE IF EXISTS jornadas_quantidade_batidas")
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS ajustes_batidas_diarias (
                    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    data_ponto DATE NOT NULL,
                    quantidade_batidas SMALLINT NOT NULL CHECK (quantidade_batidas = 4),
                    PRIMARY KEY (usuario_id, data_ponto)
                )
                """
            )
        _estrutura_pronta = True
