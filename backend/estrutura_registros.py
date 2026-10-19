from threading import Lock

from .banco_dados import criar_conexao

_indices_prontos = False
_trava_indices = Lock()


def garantir_indices_registros():
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
