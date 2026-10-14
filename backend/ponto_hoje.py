from flask import Blueprint

from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_ponto_hoje = Blueprint("ponto_hoje", __name__)


@rota_ponto_hoje.route("/ponto-hoje")
@exigir_tipos_conta("Suporte", "Administração")
def exibir_ponto_hoje():
    return renderizar_pagina("ponto_hoje.html", "ponto_hoje")
