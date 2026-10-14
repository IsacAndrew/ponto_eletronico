from flask import Blueprint

from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_configuracoes = Blueprint("configuracoes", __name__)


@rota_configuracoes.route("/configuracoes")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def exibir_configuracoes():
    return renderizar_pagina("configuracoes.html", "configuracoes")
