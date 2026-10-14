from flask import Blueprint

from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_db = Blueprint("db", __name__)


@rota_db.route("/db")
@exigir_tipos_conta("Suporte")
def exibir_db():
    return renderizar_pagina("db.html", "db")
