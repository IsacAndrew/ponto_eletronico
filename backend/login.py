from flask import (
    abort,
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .banco_dados import criar_conexao
from .ponto_qr import NOME_COOKIE_DISPOSITIVO, revogar_dispositivo


rota_login = Blueprint("login", __name__)


@rota_login.post("/visualizar-como")
def visualizar_como():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("login.exibir_login"))

    with criar_conexao() as conexao:
        usuario = conexao.execute(
            "SELECT tipo_conta FROM usuarios WHERE id = %s AND ativo = TRUE",
            (usuario_id,),
        ).fetchone()

    if not usuario or usuario[0] != "Suporte":
        abort(403)

    modo = request.form.get("modo", "Suporte")
    if modo == "Suporte":
        session.pop("modo_visualizacao", None)
    elif modo in {"Professor", "Administração"}:
        session["modo_visualizacao"] = modo
    else:
        abort(400)

    return redirect(url_for("inicio.exibir_inicio"))


@rota_login.route("/alterar-senha-obrigatoria", methods=["GET", "POST"])
def trocar_senha():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("login.exibir_login"))

    with criar_conexao() as conexao:
        usuario = conexao.execute(
            "SELECT deve_trocar_senha FROM usuarios WHERE id = %s AND ativo = TRUE",
            (usuario_id,),
        ).fetchone()

    if not usuario:
        session.clear()
        return redirect(url_for("login.exibir_login"))

    if not usuario[0]:
        destino_qr = session.get("ponto_qr_destino")
        if destino_qr:
            return redirect(
                url_for("ponto_qr.exibir_ponto_presencial", token=destino_qr)
            )
        return redirect(url_for("inicio.exibir_inicio"))

    mensagem_erro = None

    if request.method == "POST":
        destino_qr = (
            session.get("ponto_qr_destino")
            or request.form.get("ponto_qr", "").strip()
        )
        senha_nova = request.form.get("senha_nova", "")
        confirmacao_senha = request.form.get("confirmacao_senha", "")

        if len(senha_nova) < 6:
            mensagem_erro = "A nova senha deve ter pelo menos 6 caracteres."
        elif senha_nova == "102030":
            mensagem_erro = "Escolha uma senha diferente da senha temporária."
        elif senha_nova != confirmacao_senha:
            mensagem_erro = "As senhas digitadas não conferem."
        else:
            with criar_conexao() as conexao:
                conexao.execute(
                    """
                    UPDATE usuarios
                    SET senha_hash = %s, deve_trocar_senha = FALSE
                    WHERE id = %s
                    """,
                    (generate_password_hash(senha_nova), usuario_id),
                )

            destino_qr = session.get("ponto_qr_destino")
            if destino_qr:
                return redirect(
                    url_for("ponto_qr.exibir_ponto_presencial", token=destino_qr)
                )
            return redirect(url_for("inicio.exibir_inicio"))

    return render_template("trocar_senha.html", mensagem_erro=mensagem_erro)


@rota_login.post("/sair")
def sair():
    token_dispositivo = request.cookies.get(NOME_COOKIE_DISPOSITIVO)
    if token_dispositivo:
        with criar_conexao() as conexao:
            revogar_dispositivo(conexao, token_dispositivo)

    session.clear()
    resposta = redirect(url_for("login.exibir_login"))
    resposta.delete_cookie(NOME_COOKIE_DISPOSITIVO)
    return resposta


@rota_login.route("/", methods=["GET", "POST"])
def exibir_login():
    mensagem_erro = None
    destino_qr = ""

    if request.method == "POST":
        destino_qr = (
            session.get("ponto_qr_destino")
            or request.form.get("ponto_qr", "").strip()
        )
        login_usuario = request.form.get("login", "").strip()
        senha_usuario = request.form.get("senha", "")

        try:
            with criar_conexao() as conexao:
                usuario = conexao.execute(
                    """
                    SELECT id, nome_completo, senha_hash, tipo_conta, deve_trocar_senha
                    FROM usuarios
                    WHERE login = %s AND ativo = TRUE
                    """,
                    (login_usuario,),
                ).fetchone()
        except Exception:
            current_app.logger.exception("Não foi possível consultar o usuário.")
            return (
                render_template(
                    "login.html",
                    mensagem_erro="O sistema está temporariamente indisponível.",
                ),
                503,
            )

        if usuario and check_password_hash(usuario[2], senha_usuario):
            try:
                with criar_conexao() as conexao:
                    conexao.execute(
                        "UPDATE usuarios SET ultimo_acesso = NOW() WHERE id = %s",
                        (usuario[0],),
                    )
            except Exception:
                current_app.logger.exception("Não foi possível atualizar o último acesso.")
                return (
                    render_template(
                        "login.html",
                        mensagem_erro="O sistema está temporariamente indisponível.",
                    ),
                    503,
                )

            token_dispositivo = request.cookies.get(NOME_COOKIE_DISPOSITIVO)
            if token_dispositivo and not destino_qr:
                with criar_conexao() as conexao:
                    revogar_dispositivo(conexao, token_dispositivo)

            session.clear()
            session["usuario_id"] = usuario[0]
            session["usuario_nome"] = usuario[1]
            session["tipo_conta"] = usuario[3]
            if destino_qr:
                session["ponto_qr_destino"] = destino_qr

            if usuario[4]:
                return redirect(url_for("login.trocar_senha"))

            if destino_qr:
                return redirect(
                    url_for("ponto_qr.exibir_ponto_presencial", token=destino_qr)
                )
            return redirect(url_for("inicio.exibir_inicio"))

        mensagem_erro = "Login ou senha incorreta"
    else:
        destino_qr = session.get("ponto_qr_destino") or request.args.get("ponto_qr", "")
        if destino_qr:
            session["ponto_qr_destino"] = destino_qr

    return render_template(
        "login.html", mensagem_erro=mensagem_erro, ponto_qr=destino_qr or ""
    )
