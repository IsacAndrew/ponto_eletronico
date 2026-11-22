import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, url_for

from .banco_dados import criar_conexao
from .inicio import rota_inicio
from .login import rota_login
from .usuarios import rota_usuarios
from .planilha import rota_planilha
from .ponto_hoje import rota_ponto_hoje
from .configuracoes import rota_configuracoes
from .db import rota_db
from .ponto_qr import rota_ponto_qr

diretorio_projeto = Path(__file__).resolve().parent.parent
diretorio_scripts = diretorio_projeto / "scripts"
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
    """Gera URL de CSS ou JavaScript com versão baseada na última alteração."""
    if nome_arquivo.startswith("js/"):
        nome_url = nome_arquivo[3:]
        caminho = diretorio_scripts / nome_url
        endpoint = "scripts"
    else:
        nome_url = nome_arquivo
        caminho = diretorio_projeto / "static" / nome_url
        endpoint = "static"

    try:
        versao = caminho.stat().st_mtime_ns
    except OSError:
        return url_for(endpoint, filename=nome_url)

    return url_for(endpoint, filename=nome_url, v=versao)


@app.get("/scripts/<path:filename>", endpoint="scripts")
def servir_script(filename):
    return send_from_directory(diretorio_scripts, filename)


@app.context_processor
def disponibilizar_url_estatica():
    return {"url_estatica": url_estatica}


@app.after_request
def adicionar_cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "strict-origin"

    if request.endpoint in {"static", "scripts"} and resposta.status_code == 200:
        nome_arquivo = request.view_args.get("filename", "")
        diretorio_arquivo = (
            diretorio_scripts if request.endpoint == "scripts"
            else diretorio_projeto / "static"
        )
        try:
            versao_atual = str(
                (diretorio_arquivo / nome_arquivo).stat().st_mtime_ns
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
app.register_blueprint(rota_ponto_qr)


if __name__ == "__main__":
    app.run()
