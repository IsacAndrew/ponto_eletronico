from flask import Blueprint

from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_grade_curricular = Blueprint("grade_curricular", __name__)


@rota_grade_curricular.route("/grade-curricular")
@exigir_tipos_conta("Professor", "Colaborador")
def exibir_grade_curricular():
    return renderizar_pagina("grade_curricular.html", "grade_curricular")
