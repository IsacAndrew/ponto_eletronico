import atexit
import os
from pathlib import Path
from threading import Lock

from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

diretorio_projeto = Path(__file__).resolve().parent.parent
load_dotenv(diretorio_projeto / ".env")
_pool_conexoes = None
_trava_pool = Lock()


def _obter_pool():
    """Cria um pool pequeno de conexões reutilizáveis com o Supabase."""
    global _pool_conexoes

    if _pool_conexoes is not None:
        return _pool_conexoes

    with _trava_pool:
        if _pool_conexoes is not None:
            return _pool_conexoes

        configuracao_banco = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "dbname": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "sslmode": "require",
        }

        campos_obrigatorios = {
            "host": "DB_HOST",
            "port": "DB_PORT",
            "dbname": "DB_NAME",
            "user": "DB_USER",
            "password": "DB_PASSWORD",
        }
        campos_ausentes = [
            nome_variavel
            for campo, nome_variavel in campos_obrigatorios.items()
            if not configuracao_banco[campo]
        ]

        if campos_ausentes:
            nomes_variaveis = ", ".join(campos_ausentes)
            raise RuntimeError(
                f"Configure as variáveis do banco de dados: {nomes_variaveis}."
            )

        configuracao_banco["port"] = int(configuracao_banco["port"])
        _pool_conexoes = ConnectionPool(
            kwargs=configuracao_banco,
            min_size=1,
            max_size=5,
            timeout=10,
            name="ponto-eletronico",
        )
        atexit.register(_pool_conexoes.close)
    return _pool_conexoes


def criar_conexao():
    """Retorna uma conexão do pool; o contexto a devolve para reutilização."""
    return _obter_pool().connection()
