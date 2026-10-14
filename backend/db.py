import os

from flask import Blueprint, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_db = Blueprint("db", __name__)
LIMITE_ARMAZENAMENTO_PADRAO = 500_000_000
TABELAS_DADOS_SISTEMA = (
    "usuarios",
    "registros_ponto",
    "jornadas_usuarios",
    "configuracoes_sistema",
)


def obter_limite_armazenamento():
    try:
        return max(1, int(os.getenv("DB_STORAGE_LIMIT_BYTES", LIMITE_ARMAZENAMENTO_PADRAO)))
    except (TypeError, ValueError):
        return LIMITE_ARMAZENAMENTO_PADRAO


@rota_db.route("/db")
@exigir_tipos_conta("Suporte")
def exibir_db():
    with criar_conexao() as conexao:
        nome_banco, tamanho_bytes = conexao.execute(
            "SELECT current_database(), pg_database_size(current_database())"
        ).fetchone()

    limite_bytes = obter_limite_armazenamento()
    percentual = min(100, round(tamanho_bytes / limite_bytes * 100, 1))
    return renderizar_pagina(
        "db.html",
        "db",
        nome_banco=nome_banco,
        tamanho_bytes=tamanho_bytes,
        limite_bytes=limite_bytes,
        percentual=percentual,
        mensagem_erro=request.args.get("erro"),
    )


@rota_db.post("/db/apagar-tudo")
@exigir_tipos_conta("Suporte")
def apagar_dados_sistema():
    confirmacao = request.form.get("confirmacao", "").strip()
    senha = request.form.get("senha", "")
    usuario_id = session["usuario_id"]

    if confirmacao != "APAGAR TUDO":
        return redirect(url_for("db.exibir_db", erro="confirmacao"))

    with criar_conexao() as conexao:
        usuario = conexao.execute(
            "SELECT senha_hash FROM usuarios WHERE id = %s AND ativo = TRUE",
            (usuario_id,),
        ).fetchone()
        if not usuario or not check_password_hash(usuario[0], senha):
            return redirect(url_for("db.exibir_db", erro="senha"))

        tabelas_existentes = []
        for tabela in TABELAS_DADOS_SISTEMA:
            existe = conexao.execute(
                "SELECT to_regclass(%s)", (f"public.{tabela}",)
            ).fetchone()[0]
            if existe:
                tabelas_existentes.append(f'public."{tabela}"')

        if tabelas_existentes:
            conexao.execute(
                "TRUNCATE TABLE "
                + ", ".join(tabelas_existentes)
                + " RESTART IDENTITY CASCADE"
            )

    session.clear()
    return redirect(url_for("login.exibir_login"))
