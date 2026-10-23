import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

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
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
    == "true",
)


@app.after_request
def adicionar_cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "strict-origin"
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


if __name__ == "__main__":
    app.run()
