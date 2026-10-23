from threading import Lock

from .banco_dados import criar_conexao

_indices_prontos = False
_trava_indices = Lock()
_estrutura_pronta = False
_trava_estrutura = Lock()


def garantir_estrutura_registros():
    """Garante os campos usados pelo histórico de batidas."""
    global _estrutura_pronta
    if _estrutura_pronta:
        return
    with _trava_estrutura:
        if _estrutura_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                ALTER TABLE registros_ponto
                ADD COLUMN IF NOT EXISTS origem_registro TEXT NOT NULL DEFAULT 'site'
                """
            )
            conexao.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'registros_ponto'::regclass
                          AND conname = 'registros_ponto_tipo_batida_check'
                    ) THEN
                        ALTER TABLE registros_ponto
                        ADD CONSTRAINT registros_ponto_tipo_batida_check
                        CHECK (tipo_batida IN (
                            'Entrada', 'Intervalo', 'Retorno intervalo', 'Saída'
                        )) NOT VALID;
                    END IF;
                END $$;
                """
            )
        _estrutura_pronta = True


def garantir_indices_registros():
    garantir_estrutura_registros()
    global _indices_prontos
    if _indices_prontos:
        return
    with _trava_indices:
        if _indices_prontos:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                CREATE INDEX IF NOT EXISTS registros_ponto_data_usuario_idx
                ON registros_ponto (data_ponto, usuario_id)
                """
            )
        _indices_prontos = True
