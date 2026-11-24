import hashlib
import hmac
from threading import Lock
from datetime import timedelta

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
MAX_TENTATIVAS_LOGIN = 5
JANELA_TENTATIVAS_LOGIN = timedelta(minutes=5)
MENSAGEM_LOGIN_BLOQUEADO = "Aguarde 5 minutos ou entre em contato com o Isac"
_estrutura_tentativas_pronta = False
_trava_estrutura_tentativas = Lock()


def garantir_estrutura_tentativas_login():
    global _estrutura_tentativas_pronta
    if _estrutura_tentativas_pronta:
        return
    with _trava_estrutura_tentativas:
        if _estrutura_tentativas_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS tentativas_login (
                    chave CHAR(64) PRIMARY KEY,
                    tentativas SMALLINT NOT NULL
                        CHECK (tentativas BETWEEN 1 AND 5),
                    janela_iniciada TIMESTAMPTZ NOT NULL,
                    bloqueada_ate TIMESTAMPTZ,
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conexao.execute(
                """CREATE INDEX IF NOT EXISTS tentativas_login_atualizado_idx
                   ON tentativas_login (atualizado_em)"""
            )
        _estrutura_tentativas_pronta = True


def _chave_tentativas_login(login_usuario):
    segredo = current_app.config["SECRET_KEY"]
    if isinstance(segredo, str):
        segredo = segredo.encode("utf-8")
    identificador = login_usuario.strip().casefold().encode("utf-8")
    return hmac.new(segredo, identificador, hashlib.sha256).hexdigest()


def autenticar_com_limite(login_usuario, senha_usuario):
    chave = _chave_tentativas_login(login_usuario)
    id_bloqueio = int.from_bytes(bytes.fromhex(chave[:16]), "big", signed=True)

    with criar_conexao() as conexao:
        conexao.execute("SELECT pg_advisory_xact_lock(%s)", (id_bloqueio,))
        estado = conexao.execute(
            """SELECT tentativas, janela_iniciada, bloqueada_ate, NOW()
               FROM tentativas_login WHERE chave = %s""",
            (chave,),
        ).fetchone()

        if estado:
            tentativas, inicio_janela, bloqueada_ate, agora = estado
            if bloqueada_ate and bloqueada_ate > agora:
                return None, True
            if bloqueada_ate or inicio_janela <= agora - JANELA_TENTATIVAS_LOGIN:
                conexao.execute(
                    "DELETE FROM tentativas_login WHERE chave = %s", (chave,)
                )

        usuario = conexao.execute(
            """
            SELECT id, nome_completo, senha_hash, tipo_conta, deve_trocar_senha
            FROM usuarios
            WHERE login = %s AND ativo = TRUE
            """,
            (login_usuario,),
        ).fetchone()

        if usuario and check_password_hash(usuario[2], senha_usuario):
            conexao.execute("DELETE FROM tentativas_login WHERE chave = %s", (chave,))
            return usuario, False

        tentativa = conexao.execute(
            """
            INSERT INTO tentativas_login
                (chave, tentativas, janela_iniciada, bloqueada_ate, atualizado_em)
            VALUES (%s, 1, NOW(), NULL, NOW())
            ON CONFLICT (chave) DO UPDATE SET
                tentativas = CASE
                    WHEN tentativas_login.janela_iniciada
                         <= NOW() - INTERVAL '5 minutes' THEN 1
                    ELSE tentativas_login.tentativas + 1
                END,
                janela_iniciada = CASE
                    WHEN tentativas_login.janela_iniciada
                         <= NOW() - INTERVAL '5 minutes' THEN NOW()
                    ELSE tentativas_login.janela_iniciada
                END,
                bloqueada_ate = CASE
                    WHEN (
                        CASE
                            WHEN tentativas_login.janela_iniciada
                                 <= NOW() - INTERVAL '5 minutes' THEN 1
                            ELSE tentativas_login.tentativas + 1
                        END
                    ) >= 5 THEN NOW() + INTERVAL '5 minutes'
                    ELSE NULL
                END,
                atualizado_em = NOW()
            RETURNING tentativas, bloqueada_ate
            """,
            (chave,),
        ).fetchone()

        if tentativa[0] == 1:
            conexao.execute(
                """DELETE FROM tentativas_login
                   WHERE atualizado_em < NOW() - INTERVAL '1 day'"""
            )
        bloqueado = tentativa[0] >= MAX_TENTATIVAS_LOGIN and tentativa[1] is not None
        return None, bloqueado


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
            "SELECT deve_trocar_senha, senha_hash FROM usuarios WHERE id = %s AND ativo = TRUE",
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
        elif check_password_hash(usuario[1], senha_nova):
            mensagem_erro = "Escolha uma senha diferente da senha atual."
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
    destino_qr = session.get("ponto_qr_destino") or request.args.get("ponto_qr", "")

    if request.method == "POST":
        destino_qr = (
            session.get("ponto_qr_destino")
            or request.form.get("ponto_qr", "").strip()
            or destino_qr
        )
        login_usuario = request.form.get("login", "").strip()
        senha_usuario = request.form.get("senha", "")

        try:
            garantir_estrutura_tentativas_login()
            usuario, login_bloqueado = autenticar_com_limite(
                login_usuario, senha_usuario
            )
        except Exception:
            current_app.logger.exception("Não foi possível consultar o usuário.")
            return (
                render_template(
                    "login.html",
                    mensagem_erro="O sistema está temporariamente indisponível.",
                ),
                503,
            )

        if usuario:
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
            session.permanent = True
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

        if login_bloqueado:
            return render_template(
                "login.html", mensagem_erro=MENSAGEM_LOGIN_BLOQUEADO
            ), 429
        mensagem_erro = "Login ou senha incorreta"

    if destino_qr:
        session["ponto_qr_destino"] = destino_qr
    return render_template(
        "login.html", mensagem_erro=mensagem_erro, ponto_qr=destino_qr or ""
    )
