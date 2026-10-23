import hashlib
import hmac
import secrets

import qrcode
from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from qrcode.image.svg import SvgPathFillImage

from .banco_dados import criar_conexao
from .localizacao import obter_marco_zero
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_ponto_qr = Blueprint("ponto_qr", __name__)
NOME_COOKIE_DISPOSITIVO = "dispositivo_ponto"
TEMPO_COOKIE_DISPOSITIVO = 60 * 60 * 24 * 365


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def garantir_tabela_dispositivos(conexao):
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS dispositivos_ponto (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            token_hash CHAR(64) NOT NULL UNIQUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ultimo_uso_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '365 days'
        )
        """
    )


def revogar_dispositivo(conexao, token):
    if not token or not conexao.execute(
        "SELECT to_regclass('public.dispositivos_ponto')"
    ).fetchone()[0]:
        return
    conexao.execute(
        "DELETE FROM dispositivos_ponto WHERE token_hash = %s",
        (hash_token(token),),
    )


def revogar_dispositivos_usuario(conexao, usuario_id):
    if not conexao.execute(
        "SELECT to_regclass('public.dispositivos_ponto')"
    ).fetchone()[0]:
        return
    conexao.execute(
        "DELETE FROM dispositivos_ponto WHERE usuario_id = %s", (usuario_id,)
    )


def obter_token_qr(conexao, regenerar=False):
    obter_marco_zero(conexao)
    if regenerar:
        token = secrets.token_urlsafe(32)
        conexao.execute(
            "UPDATE configuracoes_sistema SET qr_ponto_token = %s WHERE id = 1",
            (token,),
        )
        return token

    token = secrets.token_urlsafe(32)
    return conexao.execute(
        """
        UPDATE configuracoes_sistema
        SET qr_ponto_token = COALESCE(qr_ponto_token, %s)
        WHERE id = 1
        RETURNING qr_ponto_token
        """,
        (token,),
    ).fetchone()[0]


def _buscar_usuario(conexao, usuario_id):
    return conexao.execute(
        """
        SELECT id, nome_completo, tipo_conta, deve_trocar_senha
        FROM usuarios WHERE id = %s AND ativo = TRUE
        """,
        (usuario_id,),
    ).fetchone()


def _url_ponto_presencial(token):
    protocolo = request.headers.get("X-Forwarded-Proto", request.scheme)
    protocolo = protocolo.split(",", 1)[0].strip()
    if protocolo not in {"http", "https"}:
        protocolo = request.scheme
    return url_for(
        "ponto_qr.exibir_ponto_presencial",
        token=token,
        _external=True,
        _scheme=protocolo,
    )


@rota_ponto_qr.get("/configuracoes/qr-ponto")
@exigir_tipos_conta("Suporte")
def exibir_qr_ponto():
    with criar_conexao() as conexao:
        obter_token_qr(conexao)
    return renderizar_pagina("qr_ponto.html", "configuracoes")


@rota_ponto_qr.get("/configuracoes/qr-ponto.svg")
@exigir_tipos_conta("Suporte")
def imagem_qr_ponto():
    with criar_conexao() as conexao:
        token = obter_token_qr(conexao)
    codigo = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    codigo.add_data(_url_ponto_presencial(token))
    codigo.make(fit=True)
    imagem = codigo.make_image(image_factory=SvgPathFillImage)
    resposta = make_response(imagem.to_string(encoding="unicode"))
    resposta.mimetype = "image/svg+xml"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@rota_ponto_qr.post("/configuracoes/qr-ponto/gerar-novo")
@exigir_tipos_conta("Suporte")
def gerar_novo_qr_ponto():
    with criar_conexao() as conexao:
        obter_token_qr(conexao, regenerar=True)
    return redirect(url_for("ponto_qr.exibir_qr_ponto"))


@rota_ponto_qr.get("/bater-ponto/<token>")
def exibir_ponto_presencial(token):
    with criar_conexao() as conexao:
        registro_qr = conexao.execute(
            "SELECT qr_ponto_token FROM configuracoes_sistema WHERE id = 1"
        ).fetchone()
        if (
            not registro_qr
            or not registro_qr[0]
            or not hmac.compare_digest(registro_qr[0], token)
        ):
            abort(404)
        garantir_tabela_dispositivos(conexao)
        conexao.execute("DELETE FROM dispositivos_ponto WHERE expira_em <= NOW()")

        usuario = None
        usuario_id = session.get("usuario_id")
        if usuario_id:
            usuario = _buscar_usuario(conexao, usuario_id)

        token_dispositivo = request.cookies.get(NOME_COOKIE_DISPOSITIVO, "")
        definir_cookie = False

        if not usuario and token_dispositivo:
            usuario = conexao.execute(
                """
                SELECT usuario.id, usuario.nome_completo, usuario.tipo_conta,
                       usuario.deve_trocar_senha
                FROM dispositivos_ponto AS dispositivo
                JOIN usuarios AS usuario ON usuario.id = dispositivo.usuario_id
                WHERE dispositivo.token_hash = %s
                  AND dispositivo.expira_em > NOW()
                  AND usuario.ativo = TRUE
                """,
                (hash_token(token_dispositivo),),
            ).fetchone()
            if usuario:
                usuario_id = usuario[0]
                conexao.execute(
                    """
                    UPDATE dispositivos_ponto
                    SET ultimo_uso_em = NOW(), expira_em = NOW() + INTERVAL '365 days'
                    WHERE token_hash = %s
                    """,
                    (hash_token(token_dispositivo),),
                )
                conexao.execute(
                    "UPDATE usuarios SET ultimo_acesso = NOW() WHERE id = %s",
                    (usuario_id,),
                )
                session["usuario_id"] = usuario[0]
                session["usuario_nome"] = usuario[1]
                session["tipo_conta"] = usuario[2]

        if not usuario:
            session["ponto_qr_destino"] = token
            return redirect(url_for("login.exibir_login", ponto_qr=token))

        if usuario[3]:
            session["ponto_qr_destino"] = token
            return redirect(url_for("login.trocar_senha"))

        session.pop("ponto_qr_destino", None)

        vinculo = None
        if token_dispositivo:
            vinculo = conexao.execute(
                "SELECT usuario_id FROM dispositivos_ponto WHERE token_hash = %s",
                (hash_token(token_dispositivo),),
            ).fetchone()

        if not vinculo or vinculo[0] != usuario[0]:
            if token_dispositivo:
                conexao.execute(
                    "DELETE FROM dispositivos_ponto WHERE token_hash = %s",
                    (hash_token(token_dispositivo),),
                )
            token_dispositivo = secrets.token_urlsafe(32)
            conexao.execute(
                """
                INSERT INTO dispositivos_ponto (usuario_id, token_hash)
                VALUES (%s, %s)
                """,
                (usuario[0], hash_token(token_dispositivo)),
            )
            definir_cookie = True
        else:
            conexao.execute(
                """
                UPDATE dispositivos_ponto
                SET ultimo_uso_em = NOW(), expira_em = NOW() + INTERVAL '365 days'
                WHERE token_hash = %s
                """,
                (hash_token(token_dispositivo),),
            )

    resposta = make_response(
        render_template("ponto_presencial.html", nome_usuario=usuario[1], token=token)
    )
    if definir_cookie:
        resposta.set_cookie(
            NOME_COOKIE_DISPOSITIVO,
            token_dispositivo,
            max_age=TEMPO_COOKIE_DISPOSITIVO,
            httponly=True,
            secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
            samesite="Lax",
        )
    return resposta
