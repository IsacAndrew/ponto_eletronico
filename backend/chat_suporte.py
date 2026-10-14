from flask import Blueprint, g, jsonify, request, session

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_chat_suporte = Blueprint("chat_suporte", __name__)


def garantir_tabelas_chat(conexao):
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS conversas_suporte (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            usuario_nome TEXT NOT NULL,
            iniciada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conexao.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS conversas_suporte_usuario_aberto_idx
        ON conversas_suporte (usuario_id)
        """
    )
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS mensagens_suporte (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            conversa_id BIGINT NOT NULL REFERENCES conversas_suporte(id) ON DELETE CASCADE,
            remetente_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            remetente_tipo TEXT NOT NULL CHECK (remetente_tipo IN ('Suporte', 'Usuario')),
            mensagem TEXT NOT NULL CHECK (char_length(mensagem) BETWEEN 1 AND 2000),
            enviada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _obter_conversa_usuario(conexao, usuario_id, nome):
    conversa = conexao.execute(
        "SELECT id FROM conversas_suporte WHERE usuario_id = %s", (usuario_id,)
    ).fetchone()
    if conversa:
        return conversa[0]
    conversa = conexao.execute(
        """
        INSERT INTO conversas_suporte (usuario_id, usuario_nome)
        VALUES (%s, %s) RETURNING id
        """,
        (usuario_id, nome),
    ).fetchone()
    return conversa[0]


@rota_chat_suporte.route("/chat-suporte")
@exigir_tipos_conta("Suporte", "Professor", "Colaborador")
def exibir_chat_suporte():
    suporte = g.tipo_conta_real == "Suporte" and not g.modo_visualizacao
    conversas = []
    conversa_id = None
    if suporte:
        with criar_conexao() as conexao:
            garantir_tabelas_chat(conexao)
            conversas = conexao.execute(
                """
                SELECT conversa.id, conversa.usuario_nome, conversa.iniciada_em,
                       COUNT(mensagem.id) AS quantidade_mensagens
                FROM conversas_suporte AS conversa
                LEFT JOIN mensagens_suporte AS mensagem ON mensagem.conversa_id = conversa.id
                GROUP BY conversa.id
                ORDER BY conversa.iniciada_em
                """
            ).fetchall()
        selecionada = request.args.get("conversa", type=int)
        if selecionada and any(item[0] == selecionada for item in conversas):
            conversa_id = selecionada
    else:
        with criar_conexao() as conexao:
            garantir_tabelas_chat(conexao)
            conversa_id = _obter_conversa_usuario(
                conexao, session["usuario_id"], session.get("usuario_nome", "Usuário")
            )
    return renderizar_pagina(
        "chat_suporte.html",
        "chat_suporte",
        suporte_chat=suporte,
        conversas=conversas,
        conversa_id=conversa_id,
    )


@rota_chat_suporte.get("/chat-suporte/atualizacoes")
@exigir_tipos_conta("Suporte", "Professor", "Colaborador")
def obter_mensagens():
    conversa_id = request.args.get("conversa", type=int)
    desde_id = max(request.args.get("desde", default=0, type=int), 0)
    suporte = g.tipo_conta_real == "Suporte" and not g.modo_visualizacao
    if not conversa_id:
        return jsonify(sucesso=False), 400
    with criar_conexao() as conexao:
        if suporte:
            conversa = conexao.execute(
                "SELECT id FROM conversas_suporte WHERE id = %s", (conversa_id,)
            ).fetchone()
        else:
            conversa = conexao.execute(
                "SELECT id FROM conversas_suporte WHERE id = %s AND usuario_id = %s",
                (conversa_id, session["usuario_id"]),
            ).fetchone()
        if not conversa:
            return jsonify(sucesso=False, encerrada=True), 404
        mensagens = conexao.execute(
            """
            SELECT id, remetente_tipo, mensagem,
                   TO_CHAR(enviada_em AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI:SS')
            FROM mensagens_suporte WHERE conversa_id = %s AND id > %s ORDER BY id
            """,
            (conversa_id, desde_id),
        ).fetchall()
    return jsonify(
        sucesso=True,
        mensagens=[
            {"id": m[0], "remetente": m[1], "texto": m[2], "horario": m[3]}
            for m in mensagens
        ],
    )


@rota_chat_suporte.post("/chat-suporte/mensagem")
@exigir_tipos_conta("Suporte", "Professor", "Colaborador")
def enviar_mensagem():
    dados = request.get_json(silent=True) or {}
    texto = str(dados.get("mensagem", "")).strip()
    conversa_id = dados.get("conversa")
    suporte = g.tipo_conta_real == "Suporte" and not g.modo_visualizacao
    if not texto or len(texto) > 2000:
        return jsonify(sucesso=False, mensagem="A mensagem deve ter até 2.000 caracteres."), 400
    try:
        conversa_id = int(conversa_id)
    except (TypeError, ValueError):
        return jsonify(sucesso=False, mensagem="Conversa inválida."), 400
    with criar_conexao() as conexao:
        if suporte:
            conversa = conexao.execute(
                "SELECT id FROM conversas_suporte WHERE id = %s", (conversa_id,)
            ).fetchone()
        else:
            conversa = conexao.execute(
                "SELECT id FROM conversas_suporte WHERE id = %s AND usuario_id = %s",
                (conversa_id, session["usuario_id"]),
            ).fetchone()
        if not conversa:
            return jsonify(sucesso=False, encerrada=True), 404
        conexao.execute(
            """
            INSERT INTO mensagens_suporte (conversa_id, remetente_id, remetente_tipo, mensagem)
            VALUES (%s, %s, %s, %s)
            """,
            (conversa_id, session["usuario_id"], "Suporte" if suporte else "Usuario", texto),
        )
    return jsonify(sucesso=True)


@rota_chat_suporte.post("/chat-suporte/<int:conversa_id>/encerrar")
@exigir_tipos_conta("Suporte")
def encerrar_conversa(conversa_id):
    if g.modo_visualizacao:
        return jsonify(sucesso=False), 403
    with criar_conexao() as conexao:
        conexao.execute("DELETE FROM conversas_suporte WHERE id = %s", (conversa_id,))
    return jsonify(sucesso=True)
