from threading import Lock

from .banco_dados import criar_conexao

_estrutura_pronta = False
_trava_estrutura = Lock()


def garantir_estrutura_usuarios():
    """Aplica as colunas e restrições necessárias para as contas de usuário."""
    global _estrutura_pronta
    if _estrutura_pronta:
        return
    with _trava_estrutura:
        if _estrutura_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS registro_fora_unidade BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            conexao.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS funcao TEXT")
            conexao.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rg TEXT")
            conexao.execute(
                """
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
                  )
                """
            )
            conexao.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS usuarios_login_normalizado_uidx
                ON usuarios (LOWER(BTRIM(login)))
                """
            )
            conexao.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_normalizado_uidx
                ON usuarios (LOWER(BTRIM(email)))
                WHERE email IS NOT NULL AND BTRIM(email) <> ''
                """
            )
        _estrutura_pronta = True
