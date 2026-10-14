from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, session

from .permissoes import exigir_tipos_conta, renderizar_pagina
from .banco_dados import criar_conexao

rota_inicio = Blueprint("inicio", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TIPOS_BATIDA = ("Entrada", "Intervalo", "Retorno intervalo", "Saída")


@rota_inicio.route("/inicio")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def exibir_inicio():
    usuario_id = session["usuario_id"]
    hoje = datetime.now(FUSO_HORARIO).date()

    with criar_conexao() as conexao:
        ultimo_registro = conexao.execute(
            """
            SELECT tipo_batida, registrado_em
            FROM registros_ponto
            WHERE usuario_id = %s AND data_ponto = %s
            ORDER BY registrado_em DESC
            LIMIT 1
            """,
            (usuario_id, hoje),
        ).fetchone()

    dados_ultimo_registro = None
    if ultimo_registro:
        dados_ultimo_registro = {
            "tipo": ultimo_registro[0],
            "horario": ultimo_registro[1].astimezone(FUSO_HORARIO).strftime("%H:%M:%S"),
        }

    return renderizar_pagina(
        "inicio.html", "inicio", ultimo_registro=dados_ultimo_registro
    )


@rota_inicio.post("/registrar-ponto")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def registrar_ponto():
    usuario_id = session["usuario_id"]
    agora = datetime.now(FUSO_HORARIO)

    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE id = %s AND ativo = TRUE FOR UPDATE",
                (usuario_id,),
            )
            if not cursor.fetchone():
                session.clear()
                return (
                    jsonify(
                        sucesso=False,
                        mensagem="Sessão inválida. Entre novamente.",
                    ),
                    401,
                )

            cursor.execute(
                """
                SELECT COUNT(*), MAX(registrado_em)
                FROM registros_ponto
                WHERE usuario_id = %s AND data_ponto = %s
                """,
                (usuario_id, agora.date()),
            )
            quantidade_batidas, ultima_batida = cursor.fetchone()

            if quantidade_batidas >= len(TIPOS_BATIDA):
                return jsonify(
                    sucesso=False,
                    mensagem="As quatro batidas de hoje já foram registradas.",
                ), 409

            if ultima_batida and agora - ultima_batida < timedelta(minutes=5):
                return jsonify(
                    sucesso=False,
                    mensagem="Aguarde pelo menos 5 minutos entre uma batida e outra.",
                ), 409

            tipo_batida = TIPOS_BATIDA[quantidade_batidas]
            cursor.execute(
                """
                INSERT INTO registros_ponto (
                    usuario_id, usuario_nome, data_ponto, tipo_batida, registrado_em
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    usuario_id,
                    session.get("usuario_nome"),
                    agora.date(),
                    tipo_batida,
                    agora,
                ),
            )

    return jsonify(
        sucesso=True,
        tipo_batida=tipo_batida,
        horario=agora.strftime("%H:%M:%S"),
        mensagem=f"{tipo_batida} registrada às {agora.strftime('%H:%M:%S')}.",
    )
