from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, request

from .banco_dados import criar_conexao
from .estrutura_registros import garantir_indices_registros
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_ponto_hoje = Blueprint("ponto_hoje", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")


def buscar_batidas_de_hoje(busca):
    garantir_indices_registros()
    hoje = datetime.now(FUSO_HORARIO).date()
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
    parametros = [hoje]
    if busca:
        consulta += " AND COALESCE(usuario.nome_completo, registro.usuario_nome, '') ILIKE %s"
        parametros.append(f"%{busca}%")
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


@rota_ponto_hoje.route("/ponto-hoje")
@exigir_tipos_conta("Suporte", "Administração")
def exibir_ponto_hoje():
    busca = request.args.get("busca", "").strip()
    return renderizar_pagina(
        "ponto_hoje.html",
        "ponto_hoje",
        busca=busca,
        registros=buscar_batidas_de_hoje(busca),
        data_hoje=datetime.now(FUSO_HORARIO).date().isoformat(),
    )
