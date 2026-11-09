import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, url_for

from .banco_dados import criar_conexao
from .inicio import rota_inicio
from .login import rota_login
from .usuarios import rota_usuarios
from .planilha import rota_planilha
from .ponto_hoje import rota_ponto_hoje
from .configuracoes import rota_configuracoes
from .db import rota_db
from .grade_curricular import rota_grade_curricular
from .chat_suporte import rota_chat_suporte
from .ponto_qr import rota_ponto_qr
from .atestados import rota_atestados
from .mensagens_login import rota_mensagens_login

diretorio_projeto = Path(__file__).resolve().parent.parent
load_dotenv(diretorio_projeto / ".env")

chave_secreta = os.getenv("FLASK_SECRET_KEY")

if not chave_secreta:
    raise RuntimeError("Configure FLASK_SECRET_KEY no arquivo .env.")

app = Flask(
    __name__,
    template_folder=str(diretorio_projeto / "templates"),
    static_folder=str(diretorio_projeto / "static"),
)
app.config.update(
    SECRET_KEY=chave_secreta,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
    == "true",
)


def url_estatica(nome_arquivo):
    """Gera URL de arquivo estático com versão baseada na última alteração."""
    caminho = diretorio_projeto / "static" / nome_arquivo
    try:
        versao = caminho.stat().st_mtime_ns
    except OSError:
        return url_for("static", filename=nome_arquivo)

    return url_for("static", filename=nome_arquivo, v=versao)


@app.context_processor
def disponibilizar_url_estatica():
    return {"url_estatica": url_estatica}


@app.after_request
def adicionar_cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "strict-origin"

    if request.endpoint == "static" and resposta.status_code == 200:
        nome_arquivo = request.view_args.get("filename", "")
        try:
            versao_atual = str(
                (diretorio_projeto / "static" / nome_arquivo).stat().st_mtime_ns
            )
        except OSError:
            versao_atual = None

        if request.args.get("v") == versao_atual:
            resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resposta.headers["Cache-Control"] = "public, max-age=3600"

    return resposta


@app.get("/health/database")
def verificar_banco():
    try:
        with criar_conexao() as conexao:
            conexao.execute("SELECT 1").fetchone()
    except Exception:
        app.logger.exception("Verificação de saúde do banco falhou.")
        resposta = jsonify(status="unavailable")
        resposta.status_code = 503
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    resposta = jsonify(status="ok")
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

app.register_blueprint(rota_login)
app.register_blueprint(rota_inicio)
app.register_blueprint(rota_usuarios)
app.register_blueprint(rota_planilha)
app.register_blueprint(rota_ponto_hoje)
app.register_blueprint(rota_configuracoes)
app.register_blueprint(rota_db)
app.register_blueprint(rota_grade_curricular)
app.register_blueprint(rota_chat_suporte)
app.register_blueprint(rota_ponto_qr)
app.register_blueprint(rota_atestados)
app.register_blueprint(rota_mensagens_login)


if __name__ == "__main__":
    app.run()
