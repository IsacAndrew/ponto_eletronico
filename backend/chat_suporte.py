from flask import Blueprint

from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_chat_suporte = Blueprint("chat_suporte", __name__)


@rota_chat_suporte.route("/chat-suporte")
@exigir_tipos_conta("Suporte", "Professor", "Colaborador")
def exibir_chat_suporte():
    return renderizar_pagina("chat_suporte.html", "chat_suporte")
