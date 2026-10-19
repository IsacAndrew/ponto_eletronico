from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, session

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
        current_app.logger.warning("PONTO_E01: localização ausente ou inválida")
        return jsonify(
            sucesso=False,
            codigo_erro="E01",
            mensagem="Localização inválida. Informe o código E01 ao suporte.",
        ), 400

    if (
        not all(isfinite(valor) for valor in (latitude, longitude, precisao))
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or precisao <= 0
    ):
        current_app.logger.warning("PONTO_E01: coordenadas ou precisão fora do formato esperado")
        return jsonify(
            sucesso=False,
            codigo_erro="E01",
            mensagem="Não foi possível validar a localização. Informe o código E01 ao suporte.",
        ), 400

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
                    current_app.logger.error("PONTO_E02: marco zero sem coordenadas")
                    return jsonify(
                        sucesso=False,
                        codigo_erro="E02",
                        mensagem="Não foi possível validar o marco zero. Informe o código E02 ao suporte.",
                    ), 503

                distancia = calcular_distancia_metros(
                    latitude, longitude, latitude_marco, longitude_marco
                )
                if distancia > raio_metros:
                    current_app.logger.warning(
                        "PONTO_E03: posição fora do raio (distância=%sm, raio=%sm)",
                        round(distancia), raio_metros,
                    )
                    return jsonify(
                        sucesso=False,
                        codigo_erro="E03",
                        mensagem=(
                            "Ponto não registrado por localização fora do raio. "
                            "Informe o código E03 ao suporte."
                        ),
                    ), 403
                if distancia + precisao > raio_metros:
                    current_app.logger.warning(
                        "PONTO_E04: precisão insuficiente (distância=%sm, precisão=%sm, raio=%sm)",
                        round(distancia), round(precisao), raio_metros,
                    )
                    return jsonify(
                        sucesso=False,
                        codigo_erro="E04",
                        mensagem=(
                            "Não foi possível confirmar sua localização. "
                            "Ative a localização precisa e informe o código E04 ao suporte."
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
