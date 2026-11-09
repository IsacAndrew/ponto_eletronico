from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, redirect, request, url_for

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_mensagens_login = Blueprint("mensagens_login", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
DIAS_SEMANA = (
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
)
_estrutura_pronta = False
_trava_estrutura = Lock()


def garantir_estrutura_mensagens_login():
    global _estrutura_pronta
    if _estrutura_pronta:
        return
    with _trava_estrutura:
        if _estrutura_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS mensagens_login (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    texto TEXT NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 4000),
                    modo TEXT NOT NULL CHECK (modo IN ('unica', 'semanal')),
                    dias_semana SMALLINT[] NOT NULL DEFAULT ARRAY[]::SMALLINT[],
                    numero_acesso SMALLINT,
                    ativa BOOLEAN NOT NULL DEFAULT TRUE,
                    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (
                        (modo = 'unica' AND numero_acesso IS NULL)
                        OR
                        (modo = 'semanal' AND numero_acesso BETWEEN 1 AND 3
                         AND cardinality(dias_semana) > 0)
                    )
                )
                """
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS mensagens_login_configuracao (
                    id SMALLINT PRIMARY KEY CHECK (id = 1),
                    habilitada BOOLEAN NOT NULL DEFAULT TRUE
                )
                """
            )
            conexao.execute(
                """INSERT INTO mensagens_login_configuracao (id)
                   VALUES (1) ON CONFLICT (id) DO NOTHING"""
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS mensagens_login_destinatarios (
                    mensagem_id BIGINT NOT NULL REFERENCES mensagens_login(id) ON DELETE CASCADE,
                    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    PRIMARY KEY (mensagem_id, usuario_id)
                )
                """
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS mensagens_login_exibicoes (
                    mensagem_id BIGINT NOT NULL REFERENCES mensagens_login(id) ON DELETE CASCADE,
                    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    exibida_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (mensagem_id, usuario_id)
                )
                """
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS mensagens_login_acessos_diarios (
                    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    data_acesso DATE NOT NULL,
                    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                    PRIMARY KEY (usuario_id, data_acesso)
                )
                """
            )
        _estrutura_pronta = True


def _buscar_mensagens_admin(conexao):
    return conexao.execute(
        """
        SELECT mensagem.id, mensagem.texto, mensagem.modo,
               mensagem.dias_semana, mensagem.numero_acesso, mensagem.ativa,
               COALESCE(
                   ARRAY_AGG(usuario.nome_completo ORDER BY usuario.nome_completo)
                       FILTER (WHERE usuario.id IS NOT NULL),
                   ARRAY[]::TEXT[]
               ) AS destinatarios
        FROM mensagens_login AS mensagem
        LEFT JOIN mensagens_login_destinatarios AS destino
               ON destino.mensagem_id = mensagem.id
        LEFT JOIN usuarios AS usuario ON usuario.id = destino.usuario_id
        GROUP BY mensagem.id
        ORDER BY mensagem.criada_em DESC, mensagem.id DESC
        """
    ).fetchall()


def _buscar_destinatarios_mensagem(conexao, mensagem_id):
    return conexao.execute(
        """
        SELECT usuario_id FROM mensagens_login_destinatarios
        WHERE mensagem_id = %s ORDER BY usuario_id
        """,
        (mensagem_id,),
    ).fetchall()


@rota_mensagens_login.get("/configuracoes/mensagens")
@exigir_tipos_conta("Suporte")
def exibir_mensagens():
    garantir_estrutura_mensagens_login()
    with criar_conexao() as conexao:
        linhas = _buscar_mensagens_admin(conexao)
        habilitada = conexao.execute(
            "SELECT habilitada FROM mensagens_login_configuracao WHERE id = 1"
        ).fetchone()[0]
    mensagens = [
        {
            "id": linha[0], "texto": linha[1], "modo": linha[2],
            "dias_semana": linha[3], "numero_acesso": linha[4],
            "ativa": linha[5], "destinatarios": linha[6],
        }
        for linha in linhas
    ]
    return renderizar_pagina(
        "mensagens.html", "configuracoes", mensagens=mensagens,
        mensagens_habilitadas=habilitada,
    )


@rota_mensagens_login.post("/configuracoes/mensagens/alternar-todas")
@exigir_tipos_conta("Suporte")
def alternar_todas_mensagens():
    garantir_estrutura_mensagens_login()
    with criar_conexao() as conexao:
        conexao.execute(
            """UPDATE mensagens_login_configuracao
               SET habilitada = NOT habilitada WHERE id = 1"""
        )
    return redirect(url_for("mensagens_login.exibir_mensagens"))


@rota_mensagens_login.get("/configuracoes/mensagens/configuracoes")
@exigir_tipos_conta("Suporte")
def configurar_mensagens():
    garantir_estrutura_mensagens_login()
    mensagem_id = request.args.get("editar", type=int)
    mensagem_edicao = None
    destinatarios_edicao = []
    with criar_conexao() as conexao:
        usuarios = conexao.execute(
            """SELECT id, nome_completo, login FROM usuarios
               WHERE ativo = TRUE ORDER BY nome_completo"""
        ).fetchall()
        linhas = _buscar_mensagens_admin(conexao)
        if mensagem_id:
            mensagem_edicao = conexao.execute(
                """SELECT id, texto, modo, dias_semana, numero_acesso, ativa
                   FROM mensagens_login WHERE id = %s""",
                (mensagem_id,),
            ).fetchone()
            if mensagem_edicao:
                mensagem_edicao = {
                    "id": mensagem_edicao[0], "texto": mensagem_edicao[1],
                    "modo": mensagem_edicao[2], "dias_semana": mensagem_edicao[3],
                    "numero_acesso": mensagem_edicao[4], "ativa": mensagem_edicao[5],
                }
                destinatarios_edicao = [
                    linha[0]
                    for linha in _buscar_destinatarios_mensagem(conexao, mensagem_id)
                ]
    mensagens = [
        {
            "id": linha[0], "texto": linha[1], "modo": linha[2],
            "dias_semana": linha[3], "numero_acesso": linha[4],
            "ativa": linha[5], "destinatarios": linha[6],
        }
        for linha in linhas
    ]
    return renderizar_pagina(
        "configuracoes_mensagens.html",
        "configuracoes",
        usuarios=usuarios,
        mensagens=mensagens,
        mensagem_edicao=mensagem_edicao,
        destinatarios_edicao=destinatarios_edicao,
        dias_semana=DIAS_SEMANA,
        resultado=request.args.get("resultado"),
    )


@rota_mensagens_login.post("/configuracoes/mensagens/salvar")
@exigir_tipos_conta("Suporte")
def salvar_mensagem():
    garantir_estrutura_mensagens_login()
    texto = request.form.get("texto", "").strip()
    modo = request.form.get("modo", "unica")
    mensagem_id = request.form.get("mensagem_id", "").strip()
    destinatarios_texto = request.form.getlist("destinatarios")
    dias_texto = request.form.getlist("dias_semana")

    try:
        destinatarios = sorted({int(valor) for valor in destinatarios_texto})
        dias = sorted({int(valor) for valor in dias_texto})
        numero_acesso = int(request.form.get("numero_acesso", "1")) if modo == "semanal" else None
        id_edicao = int(mensagem_id) if mensagem_id else None
    except ValueError:
        return redirect(url_for("mensagens_login.configurar_mensagens", resultado="dados_invalidos"))

    if (
        not texto or len(texto) > 4000 or not destinatarios
        or modo not in {"unica", "semanal"}
        or any(dia not in range(7) for dia in dias)
        or (modo == "semanal" and (not dias or numero_acesso not in {1, 2, 3}))
    ):
        return redirect(url_for("mensagens_login.configurar_mensagens", resultado="dados_invalidos"))

    with criar_conexao() as conexao:
        usuarios_validos = conexao.execute(
            """SELECT COUNT(*) FROM usuarios
               WHERE ativo = TRUE AND id = ANY(%s)""",
            (destinatarios,),
        ).fetchone()[0]
        if usuarios_validos != len(destinatarios):
            return redirect(url_for("mensagens_login.configurar_mensagens", resultado="destinatarios_invalidos"))

        if id_edicao:
            atualizado = conexao.execute(
                """UPDATE mensagens_login
                   SET texto = %s, modo = %s, dias_semana = %s,
                       numero_acesso = %s
                   WHERE id = %s RETURNING id""",
                (texto, modo, dias if modo == "semanal" else [], numero_acesso, id_edicao),
            ).fetchone()
            if not atualizado:
                return redirect(url_for("mensagens_login.configurar_mensagens", resultado="nao_encontrada"))
            conexao.execute(
                "DELETE FROM mensagens_login_destinatarios WHERE mensagem_id = %s",
                (id_edicao,),
            )
            id_salvo = id_edicao
        else:
            id_salvo = conexao.execute(
                """INSERT INTO mensagens_login
                   (texto, modo, dias_semana, numero_acesso)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (texto, modo, dias if modo == "semanal" else [], numero_acesso),
            ).fetchone()[0]
        for usuario_id in destinatarios:
            conexao.execute(
                """INSERT INTO mensagens_login_destinatarios (mensagem_id, usuario_id)
                   VALUES (%s, %s)""",
                (id_salvo, usuario_id),
            )

    return redirect(url_for("mensagens_login.configurar_mensagens", resultado="salva"))


@rota_mensagens_login.post("/configuracoes/mensagens/<int:mensagem_id>/alternar")
@exigir_tipos_conta("Suporte")
def alternar_mensagem(mensagem_id):
    garantir_estrutura_mensagens_login()
    with criar_conexao() as conexao:
        conexao.execute(
            """UPDATE mensagens_login SET ativa = NOT ativa WHERE id = %s""",
            (mensagem_id,),
        )
    return redirect(url_for("mensagens_login.configurar_mensagens", resultado="atualizada"))


@rota_mensagens_login.post("/configuracoes/mensagens/<int:mensagem_id>/excluir")
@exigir_tipos_conta("Suporte")
def excluir_mensagem(mensagem_id):
    garantir_estrutura_mensagens_login()
    with criar_conexao() as conexao:
        conexao.execute("DELETE FROM mensagens_login WHERE id = %s", (mensagem_id,))
    return redirect(url_for("mensagens_login.configurar_mensagens", resultado="excluida"))


@rota_mensagens_login.post("/mensagens-login/consultar")
def consultar_mensagem_login():
    garantir_estrutura_mensagens_login()
    dados = request.get_json(silent=True) or {}
    login = str(dados.get("login", "")).strip()[:120]
    resposta_vazia = jsonify(mensagens=[])
    resposta_vazia.headers["Cache-Control"] = "no-store"
    if not login:
        return resposta_vazia

    data_acesso = datetime.now(FUSO_HORARIO).date()
    dia_semana = data_acesso.weekday()
    with criar_conexao() as conexao:
        habilitada = conexao.execute(
            "SELECT habilitada FROM mensagens_login_configuracao WHERE id = 1"
        ).fetchone()[0]
        if not habilitada:
            return resposta_vazia
        usuario = conexao.execute(
            """SELECT id FROM usuarios
               WHERE ativo = TRUE AND LOWER(BTRIM(login)) = LOWER(BTRIM(%s))""",
            (login,),
        ).fetchone()
        if not usuario:
            return resposta_vazia
        usuario_id = usuario[0]
        quantidade = conexao.execute(
            """INSERT INTO mensagens_login_acessos_diarios
                   (usuario_id, data_acesso, quantidade)
               VALUES (%s, %s, 1)
               ON CONFLICT (usuario_id, data_acesso)
               DO UPDATE SET quantidade = mensagens_login_acessos_diarios.quantidade + 1
               RETURNING quantidade""",
            (usuario_id, data_acesso),
        ).fetchone()[0]
        mensagens = conexao.execute(
            """SELECT mensagem.id, mensagem.texto, mensagem.modo
               FROM mensagens_login AS mensagem
               JOIN mensagens_login_destinatarios AS destino
                 ON destino.mensagem_id = mensagem.id
               WHERE mensagem.ativa = TRUE AND destino.usuario_id = %s
                 AND (
                     (mensagem.modo = 'unica' AND NOT EXISTS (
                         SELECT 1 FROM mensagens_login_exibicoes AS exibicao
                         WHERE exibicao.mensagem_id = mensagem.id
                           AND exibicao.usuario_id = %s
                     ))
                     OR
                     (mensagem.modo = 'semanal'
                      AND mensagem.numero_acesso = %s
                      AND %s = ANY(mensagem.dias_semana))
                 )
               ORDER BY mensagem.id""",
            (usuario_id, usuario_id, quantidade, dia_semana),
        ).fetchall()

        retorno = []
        for mensagem_id, texto, modo in mensagens:
            if modo == "unica":
                exibicao = conexao.execute(
                    """INSERT INTO mensagens_login_exibicoes (mensagem_id, usuario_id)
                       VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING mensagem_id""",
                    (mensagem_id, usuario_id),
                ).fetchone()
                if not exibicao:
                    continue
            retorno.append(texto)

    resposta = jsonify(mensagens=retorno)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta
