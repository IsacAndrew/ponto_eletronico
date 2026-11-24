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


@rota_inicio.route("/inicio")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def exibir_inicio():
    usuario_id = session["usuario_id"]
    hoje = datetime.now(FUSO_HORARIO).date()

    garantir_estrutura_jornada()
    with criar_conexao() as conexao:
        quantidade_batidas = conexao.execute(
            """
            SELECT COALESCE(quantidade_semana.quantidade_batidas,
                            usuario.quantidade_batidas)
            FROM usuarios AS usuario
            LEFT JOIN quantidades_batidas_semanais AS quantidade_semana
              ON quantidade_semana.usuario_id = usuario.id
             AND quantidade_semana.dia_semana = %s
            WHERE usuario.id = %s AND usuario.ativo = TRUE
            """,
            (hoje.weekday(), usuario_id),
        ).fetchone()[0]
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
        "inicio.html", "inicio", ultimo_registro=dados_ultimo_registro,
        quantidade_batidas=quantidade_batidas,
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


def avisar_registro_incompleto(cursor, usuario_id, quantidades_semanais, hoje):
    cursor.execute(
        """SELECT registro.data_ponto,
                  ARRAY_AGG(registro.tipo_batida ORDER BY registro.registrado_em, registro.id)
           FROM registros_ponto AS registro
           LEFT JOIN registros_ponto_verificados AS verificacao
             ON verificacao.usuario_id = registro.usuario_id
            AND verificacao.data_ponto = registro.data_ponto
           WHERE registro.usuario_id = %s
             AND registro.data_ponto < %s
             AND verificacao.usuario_id IS NULL
           GROUP BY registro.data_ponto
           ORDER BY registro.data_ponto""",
        (usuario_id, hoje),
    )
    datas_verificadas = []
    primeiro_aviso = None
    for data_ponto, tipos_registrados in cursor.fetchall():
        quantidade_prevista = quantidades_semanais[data_ponto.weekday()]
        tipos_previstos = (
            ("Entrada", "Saída") if quantidade_prevista == 2
            else TIPOS_BATIDA if quantidade_prevista == 4
            else ()
        )
        tipos_faltantes = [
            tipo for tipo in tipos_previstos if tipo not in set(tipos_registrados)
        ]
        aviso_emitido = bool(tipos_faltantes)
        datas_verificadas.append((usuario_id, data_ponto, aviso_emitido))
        if aviso_emitido and primeiro_aviso is None:
            data_formatada = data_ponto.strftime("%d/%m/%y")
            if tipos_faltantes == ["Saída"]:
                primeiro_aviso = (
                    f"No dia {data_formatada} você não registrou sua saída. "
                    "Se atente ao dia de hoje."
                )
            else:
                nomes_faltantes = ", ".join(tipos_faltantes)
                primeiro_aviso = (
                    f"No dia {data_formatada} seu registro ficou incompleto "
                    f"(faltaram: {nomes_faltantes}). Se atente ao dia de hoje."
                )

    if datas_verificadas:
        cursor.executemany(
            """INSERT INTO registros_ponto_verificados
               (usuario_id, data_ponto, aviso_emitido)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            datas_verificadas,
        )
    return primeiro_aviso


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
                    mensagem="Você não possui batidas de ponto configuradas para hoje. Fale com o suporte do sistema se precisar de ajuda.",
                ), 409

            if ultima_batida and agora - ultima_batida < timedelta(minutes=5):
                return jsonify(
                    sucesso=False,
                    mensagem="Aguarde pelo menos 5 minutos entre uma batida e outra.",
                ), 409

            if quantidade_batidas >= len(TIPOS_BATIDA):
                return jsonify(
                    sucesso=False,
                    mensagem=f"As {quantidade_prevista} batidas de hoje já foram registradas.",
                ), 409

            if quantidade_batidas >= quantidade_prevista:
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

            aviso_registro_incompleto = avisar_registro_incompleto(
                cursor, usuario_id, quantidades_semanais, agora.date()
            )

    return jsonify(
        sucesso=True,
        tipo_batida=tipo_batida,
        horario=agora.strftime("%H:%M:%S"),
        mensagem=f"{tipo_batida} registrada às {agora.strftime('%H:%M:%S')}.",
        aviso_registro_incompleto=aviso_registro_incompleto,
    )
