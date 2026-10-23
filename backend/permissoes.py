from functools import wraps

from flask import abort, g, redirect, render_template, request, session, url_for

from .banco_dados import criar_conexao

MENU_ADMINISTRACAO = [
    ("Início", "inicio.exibir_inicio", "inicio", "casa"),
    ("Usuários", "usuarios.exibir_usuarios", "usuarios", "pessoas"),
    ("Planilha", "planilha.exibir_planilha", "planilha", "planilha"),
    ("Histórico", "ponto_hoje.exibir_historico_batidas", "historico_batidas", "relogio"),
    (
        "Configurações",
        "configuracoes.exibir_configuracoes",
        "configuracoes",
        "engrenagem",
    ),
]

MENU_PROFESSOR = [
    ("Início", "inicio.exibir_inicio", "inicio", "casa"),
    (
        "Grade Curricular",
        "grade_curricular.exibir_grade_curricular",
        "grade_curricular",
        "grade",
    ),
    (
        "Chat com suporte",
        "chat_suporte.exibir_chat_suporte",
        "chat_suporte",
        "conversa",
    ),
    (
        "Configurações",
        "configuracoes.exibir_configuracoes",
        "configuracoes",
        "engrenagem",
    ),
]

MENU_SUPORTE = [
    *MENU_ADMINISTRACAO[:4],
    ("Chats", "chat_suporte.exibir_chat_suporte", "chat_suporte", "conversa"),
    *MENU_ADMINISTRACAO[4:],
    ("DB", "db.exibir_db", "db", "banco"),
]

MENUS_POR_TIPO_CONTA = {
    "Suporte": MENU_SUPORTE,
    "Administração": MENU_ADMINISTRACAO,
    "Professor": MENU_PROFESSOR,
    "Colaborador": MENU_PROFESSOR,
}


def exigir_tipos_conta(*tipos_permitidos):
    def decorar(funcao):
        @wraps(funcao)
        def verificar_acesso(*args, **kwargs):
            usuario_id = session.get("usuario_id")

            if not usuario_id:
                return redirect(url_for("login.exibir_login"))

            with criar_conexao() as conexao:
                usuario = conexao.execute(
                    """
                    SELECT tipo_conta, nome_completo, deve_trocar_senha
                    FROM usuarios
                    WHERE id = %s AND ativo = TRUE
                    """,
                    (usuario_id,),
                ).fetchone()

            if not usuario:
                session.clear()
                return redirect(url_for("login.exibir_login"))

            tipo_conta_real = usuario[0]
            modo_visualizacao = session.get("modo_visualizacao")
            if tipo_conta_real != "Suporte":
                session.pop("modo_visualizacao", None)
                modo_visualizacao = None
            elif modo_visualizacao not in {"Professor", "Administração"}:
                session.pop("modo_visualizacao", None)
                modo_visualizacao = None

            tipo_conta = modo_visualizacao or tipo_conta_real
            session["tipo_conta"] = tipo_conta_real
            session["usuario_nome"] = usuario[1]

            if usuario[2] and request.endpoint != "login.trocar_senha":
                return redirect(url_for("login.trocar_senha"))

            if tipo_conta not in tipos_permitidos:
                abort(403)

            g.tipo_conta = tipo_conta
            g.tipo_conta_real = tipo_conta_real
            g.modo_visualizacao = modo_visualizacao
            return funcao(*args, **kwargs)

        return verificar_acesso

    return decorar


def renderizar_pagina(template, pagina_atual, **contexto):
    itens_menu = [
        {
            "nome": nome,
            "url": url_for(endpoint),
            "atual": identificador == pagina_atual,
            "icone": icone,
        }
        for nome, endpoint, identificador, icone in MENUS_POR_TIPO_CONTA[
            g.tipo_conta
        ]
    ]

    return render_template(
        template,
        itens_menu=itens_menu,
        tipo_conta=g.tipo_conta,
        conta_suporte=(g.tipo_conta_real == "Suporte"),
        modo_visualizacao=g.modo_visualizacao,
        usuario_nome=(session.get("usuario_nome", "Usuário").split() or ["Usuário"])[0],
        **contexto,
    )
