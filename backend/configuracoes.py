from flask import Blueprint, g, jsonify, request

from .banco_dados import criar_conexao
from .localizacao import garantir_tabela_marco_zero, obter_marco_zero
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_configuracoes = Blueprint("configuracoes", __name__)


@rota_configuracoes.route("/configuracoes")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def exibir_configuracoes():
    latitude = longitude = None
    endereco = ""
    raio = 100
    configurado = False
    if g.tipo_conta_real == "Suporte" and not g.modo_visualizacao:
        with criar_conexao() as conexao:
            marco_zero = obter_marco_zero(conexao)
        latitude, longitude, endereco, raio = marco_zero
        configurado = latitude is not None and longitude is not None
    return renderizar_pagina(
        "configuracoes.html",
        "configuracoes",
        marco_configurado=configurado,
        marco_endereco=endereco,
        marco_latitude=latitude,
        marco_longitude=longitude,
        raio_ponto=raio,
    )


@rota_configuracoes.post("/configuracoes/marco-zero")
@exigir_tipos_conta("Suporte")
def salvar_marco_zero():
    dados = request.get_json(silent=True) or {}
    endereco = str(dados.get("endereco", "")).strip()

    try:
        latitude = float(dados.get("latitude"))
        longitude = float(dados.get("longitude"))
        raio = int(dados.get("raio_metros", 100))
    except (TypeError, ValueError):
        return jsonify(sucesso=False, mensagem="Informe uma localização válida."), 400

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return jsonify(sucesso=False, mensagem="As coordenadas informadas são inválidas."), 400
    if not 1 <= raio <= 100:
        return jsonify(sucesso=False, mensagem="O raio deve ficar entre 1 e 100 metros."), 400
    if not endereco or len(endereco) > 500:
        return jsonify(sucesso=False, mensagem="Informe o endereço do marco zero."), 400

    with criar_conexao() as conexao:
        garantir_tabela_marco_zero(conexao)
        conexao.execute(
            """
            UPDATE configuracoes_sistema
            SET marco_zero_latitude = %s,
                marco_zero_longitude = %s,
                marco_zero_endereco = %s,
                raio_ponto_metros = %s,
                atualizado_em = NOW()
            WHERE id = 1
            """,
            (latitude, longitude, endereco, raio),
        )

    return jsonify(sucesso=True, mensagem="Marco zero salvo com sucesso.")
