from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request, session

from .permissoes import exigir_tipos_conta, renderizar_pagina
from .banco_dados import criar_conexao
from .localizacao import calcular_distancia_metros, obter_marco_zero
from .jornada import garantir_estrutura_jornada
from .estrutura_usuarios import garantir_estrutura_usuarios

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
    dados_localizacao = request.get_json(silent=True) or {}
    try:
        latitude = float(dados_localizacao.get("latitude"))
        longitude = float(dados_localizacao.get("longitude"))
        precisao = float(dados_localizacao.get("precisao"))
    except (TypeError, ValueError):
        return jsonify(
            sucesso=False,
            mensagem="Ative a localização do dispositivo para registrar o ponto.",
        ), 400

    if (
        not all(isfinite(valor) for valor in (latitude, longitude, precisao))
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or precisao <= 0
    ):
        return jsonify(sucesso=False, mensagem="Não foi possível validar sua localização."), 400

    garantir_estrutura_jornada()
    garantir_estrutura_usuarios()
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, quantidade_batidas, registro_fora_unidade
                   FROM usuarios WHERE id = %s AND ativo = TRUE FOR UPDATE""",
                (usuario_id,),
            )
            usuario = cursor.fetchone()
            if not usuario:
                session.clear()
                return (
                    jsonify(
                        sucesso=False,
                        mensagem="Sessão inválida. Entre novamente.",
                    ),
                    401,
                )
            tipos_batida = ("Entrada", "Saída") if usuario[1] == 2 else TIPOS_BATIDA

            if not usuario[2]:
                marco_zero = obter_marco_zero(conexao)
                latitude_marco, longitude_marco, _, raio_metros = marco_zero
                if latitude_marco is None or longitude_marco is None:
                    return jsonify(
                        sucesso=False,
                        mensagem="O marco zero ainda não foi configurado pelo suporte.",
                    ), 503

                distancia = calcular_distancia_metros(
                    latitude, longitude, latitude_marco, longitude_marco
                )
                if distancia > raio_metros:
                    return jsonify(
                        sucesso=False,
                        mensagem=(
                            f"Ponto não registrado: você está a aproximadamente "
                            f"{round(distancia)} m do marco zero. O limite é {raio_metros} m."
                        ),
                    ), 403
                if distancia + precisao > raio_metros:
                    return jsonify(
                        sucesso=False,
                        mensagem=(
                            "Não foi possível confirmar que você está dentro do raio permitido. "
                            "Ative o GPS e tente novamente mais perto do marco zero."
                        ),
                    ), 409

            cursor.execute(
                """
                SELECT COUNT(*), MAX(registrado_em)
                FROM registros_ponto
                WHERE usuario_id = %s AND data_ponto = %s
                """,
                (usuario_id, agora.date()),
            )
            quantidade_batidas, ultima_batida = cursor.fetchone()

            if quantidade_batidas >= len(tipos_batida):
                return jsonify(
                    sucesso=False,
                    mensagem=f"As {len(tipos_batida)} batidas de hoje já foram registradas.",
                ), 409

            if ultima_batida and agora - ultima_batida < timedelta(minutes=5):
                return jsonify(
                    sucesso=False,
                    mensagem="Aguarde pelo menos 5 minutos entre uma batida e outra.",
                ), 409

            tipo_batida = tipos_batida[quantidade_batidas]
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
