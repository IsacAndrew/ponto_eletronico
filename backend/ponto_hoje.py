from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, redirect, request, url_for

from .banco_dados import criar_conexao
from .estrutura_registros import garantir_indices_registros
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_ponto_hoje = Blueprint("ponto_hoje", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")


def buscar_batidas_do_dia(data_consulta):
    garantir_indices_registros()
    consulta = """
        SELECT COALESCE(usuario.nome_completo, registro.usuario_nome, 'Usuário removido') AS nome,
               registro.usuario_id,
               MAX(registro.registrado_em) FILTER (WHERE registro.tipo_batida = 'Entrada'),
               MAX(registro.registrado_em) FILTER (WHERE registro.tipo_batida = 'Intervalo'),
               MAX(registro.registrado_em) FILTER (WHERE registro.tipo_batida = 'Retorno intervalo'),
               MAX(registro.registrado_em) FILTER (WHERE registro.tipo_batida = 'Saída')
        FROM registros_ponto AS registro
        LEFT JOIN usuarios AS usuario ON usuario.id = registro.usuario_id
        WHERE registro.data_ponto = %s
    """
    parametros = [data_consulta]
    consulta += """
        GROUP BY registro.usuario_id, COALESCE(usuario.nome_completo, registro.usuario_nome, 'Usuário removido')
        HAVING COUNT(*) FILTER (WHERE registro.tipo_batida = 'Entrada') > 0
        ORDER BY nome
    """

    with criar_conexao() as conexao:
        registros = conexao.execute(consulta, parametros).fetchall()

    return [
        {
            "nome": linha[0],
            "batidas": [
                horario.astimezone(FUSO_HORARIO).strftime("%H:%M") if horario else None
                for horario in linha[2:]
            ],
        }
        for linha in registros
    ]


@rota_ponto_hoje.get("/ponto-hoje")
def redirecionar_ponto_hoje():
    return redirect(
        url_for("ponto_hoje.exibir_historico_batidas", **request.args),
        code=301,
    )


@rota_ponto_hoje.get("/historico-batidas")
@exigir_tipos_conta("Suporte", "Administração")
def exibir_historico_batidas():
    hoje = datetime.now(FUSO_HORARIO).date()
    data_consulta = hoje
    erro_filtro = None
    valor_data = request.args.get("data", "").strip()
    if valor_data:
        try:
            data_consulta = datetime.strptime(valor_data, "%d-%m-%Y").date()
            if data_consulta > hoje:
                raise ValueError
        except ValueError:
            data_consulta = hoje
            erro_filtro = "Selecione uma data válida, até hoje."

    return renderizar_pagina(
        "ponto_hoje.html",
        "historico_batidas",
        registros=buscar_batidas_do_dia(data_consulta),
        data_exibicao=data_consulta.strftime("%d-%m-%Y"),
        data_hoje=hoje.isoformat(),
        erro_filtro=erro_filtro,
    )
