from datetime import datetime, timedelta
from hmac import compare_digest
from math import isfinite
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, jsonify, request, session

from .permissoes import exigir_tipos_conta, renderizar_pagina
from .banco_dados import criar_conexao
from .localizacao import calcular_distancia_metros, obter_marco_zero
from .jornada import garantir_estrutura_jornada
from .estrutura_registros import garantir_estrutura_registros
from .estrutura_usuarios import garantir_estrutura_usuarios

rota_inicio = Blueprint("inicio", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TIPOS_BATIDA = ("Entrada", "Intervalo", "Retorno intervalo", "Saída")
QUANTIDADES_VALIDAS = {0, 2, 4}


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
    return _registrar_ponto(exigir_localizacao=True)


@rota_inicio.post("/registrar-ponto-qr/<token>")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def registrar_ponto_qr(token):
    with criar_conexao() as conexao:
        registro_qr = conexao.execute(
            "SELECT qr_ponto_token FROM configuracoes_sistema WHERE id = 1"
        ).fetchone()
    if not registro_qr or not registro_qr[0] or not compare_digest(registro_qr[0], token):
        abort(404)
    return _registrar_ponto(exigir_localizacao=False)


def obter_quantidades_semanais(cursor, usuario_id, quantidade_padrao):
    cursor.execute(
        "SELECT dia_semana FROM jornadas_usuarios WHERE usuario_id = %s",
        (usuario_id,),
    )
    dias_com_jornada = {linha[0] for linha in cursor.fetchall()}
    if dias_com_jornada:
        quantidades = [quantidade_padrao if dia in dias_com_jornada else 0 for dia in range(7)]
    else:
        quantidades = [quantidade_padrao] * 5 + [0, 0]

    cursor.execute(
        """SELECT dia_semana, quantidade_batidas
           FROM quantidades_batidas_semanais WHERE usuario_id = %s""",
        (usuario_id,),
    )
    for dia_semana, quantidade in cursor.fetchall():
        quantidades[dia_semana] = quantidade
    return quantidades


def validar_quantidades_semanais(valores, dia_atual):
    if not isinstance(valores, list) or len(valores) != 7:
        return None
    if any(type(quantidade) is not int or quantidade not in QUANTIDADES_VALIDAS for quantidade in valores):
        return None
    if valores[dia_atual] != 4:
        return None
    return valores


def _registrar_ponto(exigir_localizacao):
    usuario_id = session["usuario_id"]
    agora = datetime.now(FUSO_HORARIO)
    dados_localizacao = request.get_json(silent=True) or {}
    if exigir_localizacao:
        try:
            latitude = float(dados_localizacao.get("latitude"))
            longitude = float(dados_localizacao.get("longitude"))
            precisao = float(dados_localizacao.get("precisao"))
        except (TypeError, ValueError):
            current_app.logger.warning("PONTO_LOCALIZACAO_AUSENTE_OU_INVALIDA")
            return jsonify(
                sucesso=False,
                mensagem="Não foi possível obter sua localização. Ative a localização do aparelho e tente novamente.",
            ), 400

        if (
            not all(isfinite(valor) for valor in (latitude, longitude, precisao))
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
            or precisao <= 0
        ):
            current_app.logger.warning("PONTO_COORDENADAS_OU_PRECISAO_INVALIDAS")
            return jsonify(
                sucesso=False,
                mensagem="Não foi possível validar a localização. Confira as permissões e tente novamente.",
            ), 400
    else:
        latitude = longitude = precisao = None

    garantir_estrutura_jornada()
    garantir_estrutura_registros()
    garantir_estrutura_usuarios()
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, quantidade_batidas, registro_fora_unidade, tipo_conta
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
            quantidades_semanais = obter_quantidades_semanais(cursor, usuario_id, usuario[1])
            quantidade_prevista = quantidades_semanais[agora.weekday()]
            tipos_batida = ("Entrada", "Saída") if quantidade_prevista == 2 else TIPOS_BATIDA

            if exigir_localizacao and not usuario[2]:
                marco_zero = obter_marco_zero(conexao)
                latitude_marco, longitude_marco, _, raio_metros = marco_zero
                if latitude_marco is None or longitude_marco is None:
                    current_app.logger.error("MARCO_ZERO_SEM_COORDENADAS")
                    return jsonify(
                        sucesso=False,
                        mensagem="A localização da escola não está configurada corretamente. Avise o suporte.",
                    ), 503

                distancia = calcular_distancia_metros(
                    latitude, longitude, latitude_marco, longitude_marco
                )
                if distancia - precisao > raio_metros:
                    current_app.logger.warning(
                        "PONTO_FORA_DO_RAIO: posição fora do raio mesmo considerando a precisão "
                        "(distância=%sm, precisão=%sm, raio=%sm)",
                        round(distancia), round(precisao), raio_metros,
                    )
                    return jsonify(
                        sucesso=False,
                        mensagem=(
                            "Ponto não registrado: você está fora do raio permitido da escola."
                        ),
                    ), 403
                if distancia + precisao > raio_metros:
                    current_app.logger.warning(
                        "PONTO_PRECISAO_INSUFICIENTE (distância=%sm, precisão=%sm, raio=%sm)",
                        round(distancia), round(precisao), raio_metros,
                    )
                    return jsonify(
                        sucesso=False,
                        mensagem=(
                            "Não foi possível confirmar sua localização. "
                            "Ative a localização precisa do aparelho e tente novamente."
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

            if quantidade_prevista == 0:
                return jsonify(
                    sucesso=False,
                    mensagem="Você não possui batidas de ponto configuradas para hoje. Fale com o Isac se precisar de ajuda.",
                ), 409

            if ultima_batida and agora - ultima_batida < timedelta(minutes=5):
                return jsonify(
                    sucesso=False,
                    mensagem="Aguarde pelo menos 5 minutos entre uma batida e outra.",
                ), 409

            if quantidade_batidas >= len(TIPOS_BATIDA):
                return jsonify(
                    sucesso=False,
                    mensagem="As 4 batidas de hoje já foram registradas.",
                ), 409

            confirmou_quatro_batidas = dados_localizacao.get("quatro_batidas_hoje") is True
            confirmar_quantidade = False
            if confirmou_quatro_batidas:
                novas_quantidades = validar_quantidades_semanais(
                    dados_localizacao.get("quantidades_semanais"), agora.weekday()
                )
                if not novas_quantidades or quantidade_batidas < quantidade_prevista:
                    return jsonify(sucesso=False, mensagem="Ajuste de batidas não solicitado."), 400

                for dia_semana, quantidade in enumerate(novas_quantidades):
                    cursor.execute(
                        """INSERT INTO quantidades_batidas_semanais
                           (usuario_id, dia_semana, quantidade_batidas)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (usuario_id, dia_semana)
                           DO UPDATE SET quantidade_batidas = EXCLUDED.quantidade_batidas""",
                        (usuario_id, dia_semana, quantidade),
                    )
                quantidade_prevista = 4
                tipos_batida = TIPOS_BATIDA
                cursor.execute(
                    """SELECT id FROM registros_ponto
                       WHERE usuario_id = %s AND data_ponto = %s
                       ORDER BY registrado_em, id""",
                    (usuario_id, agora.date()),
                )
                registros_hoje = cursor.fetchall()
                for indice, (registro_id,) in enumerate(registros_hoje):
                    cursor.execute(
                        "UPDATE registros_ponto SET tipo_batida = %s WHERE id = %s",
                        (tipos_batida[indice], registro_id),
                    )
                confirmar_quantidade = True

            if quantidade_batidas >= quantidade_prevista and not confirmar_quantidade:
                if (
                    quantidade_prevista < 4
                    and quantidade_batidas < 4
                ):
                    return jsonify(
                        sucesso=False,
                        perguntar_quantidade_batidas=True,
                        mensagem="Hoje você possui 4 batidas?",
                        quantidades_semanais=[
                            4 if dia == agora.weekday() else quantidade
                            for dia, quantidade in enumerate(quantidades_semanais)
                        ],
                    ), 409
                return jsonify(
                    sucesso=False,
                    mensagem=f"As {quantidade_prevista} batidas de hoje já foram registradas.",
                ), 409

            tipo_batida = tipos_batida[quantidade_batidas]
            cursor.execute(
                """
                INSERT INTO registros_ponto (
                    usuario_id, usuario_nome, data_ponto, tipo_batida, registrado_em,
                    origem_registro
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    usuario_id,
                    session.get("usuario_nome"),
                    agora.date(),
                    tipo_batida,
                    agora,
                    "site" if exigir_localizacao else "qr",
                ),
            )

    return jsonify(
        sucesso=True,
        tipo_batida=tipo_batida,
        horario=agora.strftime("%H:%M:%S"),
        mensagem=f"{tipo_batida} registrada às {agora.strftime('%H:%M:%S')}.",
        confirmacao_quantidade=confirmar_quantidade,
    )
