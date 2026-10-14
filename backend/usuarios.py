import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

from flask import Blueprint, redirect, request, session, url_for
from werkzeug.security import generate_password_hash

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_usuarios = Blueprint("usuarios", __name__)
TIPOS_CONTA = ("Suporte", "Administração", "Professor", "Colaborador")
DIAS_SEMANA = (
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
CAMPOS_FILTRO = {
    "nome": "nome_completo",
    "email": "email",
    "telefone": "telefone",
    "permissao": "tipo_conta",
}


def buscar_usuarios(filtro, busca):
    consulta = """
        SELECT id, nome_completo, login, email, telefone, tipo_conta, ativo, ultimo_acesso
        FROM usuarios
    """
    parametros = []

    if busca:
        if filtro in CAMPOS_FILTRO:
            coluna = CAMPOS_FILTRO[filtro]
            consulta += f" WHERE {coluna} ILIKE %s"
            parametros.append(f"%{busca}%")
        elif filtro == "acesso":
            valor_acesso = busca.casefold().strip()
            if valor_acesso in {"nunca", "nunca acessou", "não", "nao"}:
                consulta += " WHERE ultimo_acesso IS NULL"
            elif valor_acesso in {"acessou", "já acessou", "ja acessou", "sim"}:
                consulta += " WHERE ultimo_acesso IS NOT NULL"
            else:
                consulta += " WHERE FALSE"

    consulta += " ORDER BY nome_completo"

    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta, parametros)
            nomes_colunas = [coluna.name for coluna in cursor.description]
            usuarios = [dict(zip(nomes_colunas, linha)) for linha in cursor.fetchall()]

    for usuario in usuarios:
        ultimo_acesso = usuario["ultimo_acesso"]
        usuario["ultimo_acesso_formatado"] = (
            ultimo_acesso.astimezone(FUSO_HORARIO).strftime("%d/%m/%Y às %H:%M")
            if ultimo_acesso
            else None
        )

    return usuarios


def buscar_usuario(usuario_id):
    with criar_conexao() as conexao:
        usuario = conexao.execute(
            """
            SELECT id, nome_completo, login, email, telefone, tipo_conta, ativo
            FROM usuarios
            WHERE id = %s
            """,
            (usuario_id,),
        ).fetchone()

    if not usuario:
        return None

    return dict(
        zip(
            ("id", "nome_completo", "login", "email", "telefone", "tipo_conta", "ativo"),
            usuario,
        )
    )


def buscar_jornadas(usuario_id):
    with criar_conexao() as conexao:
        registros = conexao.execute(
            """
            SELECT dia_semana, entrada, intervalo, retorno_intervalo, saida
            FROM jornadas_usuarios
            WHERE usuario_id = %s
            ORDER BY dia_semana
            """,
            (usuario_id,),
        ).fetchall()
    return [
        {
            "dia_semana": linha[0],
            "dia_nome": DIAS_SEMANA[linha[0]],
            "entrada": linha[1],
            "intervalo": linha[2],
            "retorno_intervalo": linha[3],
            "saida": linha[4],
        }
        for linha in registros
    ]


def renderizar_lista_usuarios(
    filtro="nome",
    busca="",
    usuario_edicao=None,
    erro_edicao=None,
    usuario_novo=None,
    erro_novo=None,
    confirmar_exclusao=None,
    resultado=None,
    aba_edicao="perfil",
    jornadas=None,
    jornada_edicao=None,
    erro_jornada=None,
):
    filtro = filtro if filtro in {*CAMPOS_FILTRO, "acesso"} else "nome"
    return renderizar_pagina(
        "usuarios.html",
        "usuarios",
        usuarios=buscar_usuarios(filtro, busca),
        filtro_atual=filtro,
        busca=busca,
        usuario_edicao=usuario_edicao,
        erro_edicao=erro_edicao,
        usuario_novo=usuario_novo,
        erro_novo=erro_novo,
        confirmar_exclusao=confirmar_exclusao,
        resultado=resultado,
        tipos_conta=TIPOS_CONTA,
        aba_edicao=aba_edicao,
        jornadas=jornadas or [],
        jornada_edicao=jornada_edicao or {},
        dias_semana=DIAS_SEMANA,
        erro_jornada=erro_jornada,
    )


@rota_usuarios.route("/usuarios")
@exigir_tipos_conta("Suporte", "Administração")
def exibir_usuarios():
    filtro = request.args.get("filtro", "nome")
    busca = request.args.get("busca", "").strip()
    resultado = request.args.get("resultado")
    mensagens = {
        "criado": "Usuário criado. A senha temporária é 102030 e deverá ser trocada no primeiro acesso.",
        "excluido": "Acesso excluído. Os registros de ponto foram preservados.",
        "senha": "Senha redefinida para 102030. O usuário deverá criar uma nova senha no próximo acesso.",
    }
    return renderizar_lista_usuarios(
        filtro,
        busca,
        resultado=mensagens.get(resultado),
    )


def validar_dados_usuario(formulario):
    dados = {
        "nome_completo": formulario.get("nome_completo", "").strip(),
        "login": formulario.get("login", "").strip(),
        "email": formulario.get("email", "").strip(),
        "telefone": formulario.get("telefone", "").strip(),
        "tipo_conta": formulario.get("tipo_conta", ""),
    }

    if len(dados["nome_completo"].split()) < 2:
        return dados, "Informe o nome completo."
    if not dados["login"]:
        return dados, "Informe o login."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", dados["email"]):
        return dados, "Informe um email válido."
    if not re.fullmatch(r"\(\d{2}\) \d{5}-\d{4}", dados["telefone"]):
        return dados, "Use o formato de telefone (xx) xxxxx-xxxx."
    if dados["tipo_conta"] not in TIPOS_CONTA:
        return dados, "Selecione uma permissão válida."
    return dados, None


def buscar_conflito_usuario(usuario_id, login, email):
    with criar_conexao() as conexao:
        if usuario_id is None:
            return conexao.execute(
                "SELECT id FROM usuarios WHERE login = %s OR email = %s LIMIT 1",
                (login, email),
            ).fetchone()
        return conexao.execute(
            "SELECT id FROM usuarios WHERE id <> %s AND (login = %s OR email = %s) LIMIT 1",
            (usuario_id, login, email),
        ).fetchone()


def buscar_outro_suporte(usuario_id):
    with criar_conexao() as conexao:
        if usuario_id is None:
            return conexao.execute(
                "SELECT id FROM usuarios WHERE tipo_conta = 'Suporte' LIMIT 1"
            ).fetchone()
        return conexao.execute(
            "SELECT id FROM usuarios WHERE tipo_conta = 'Suporte' AND id <> %s LIMIT 1",
            (usuario_id,),
        ).fetchone()


@rota_usuarios.route("/usuarios/adicionar", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def adicionar_usuario():
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    usuario_novo = {
        "nome_completo": "",
        "login": "",
        "email": "",
        "telefone": "",
        "tipo_conta": "Professor",
    }

    if request.method == "GET":
        return renderizar_lista_usuarios(filtro, busca, usuario_novo=usuario_novo)

    dados, erro = validar_dados_usuario(request.form)
    usuario_novo.update(dados)
    if erro:
        return renderizar_lista_usuarios(
            filtro, busca, usuario_novo=usuario_novo, erro_novo=erro
        )

    if buscar_conflito_usuario(None, dados["login"], dados["email"]):
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_novo=usuario_novo,
            erro_novo="Esse login ou email já está sendo usado por outro usuário.",
        )

    if dados["tipo_conta"] == "Suporte" and buscar_outro_suporte(None):
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_novo=usuario_novo,
            erro_novo="Já existe uma conta com a permissão Suporte.",
        )

    with criar_conexao() as conexao:
        conexao.execute(
            """
            INSERT INTO usuarios (
                nome_completo, login, email, telefone, tipo_conta, senha_hash,
                ativo, deve_trocar_senha
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)
            """,
            (
                dados["nome_completo"],
                dados["login"],
                dados["email"],
                dados["telefone"],
                dados["tipo_conta"],
                generate_password_hash("102030"),
            ),
        )

    return redirect(
        url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca, resultado="criado")
    )


@rota_usuarios.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def editar_usuario(usuario_id):
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    usuario = buscar_usuario(usuario_id)

    if not usuario:
        return redirect(url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca))

    if request.method == "GET":
        aba_edicao = request.args.get("aba", "perfil")
        jornadas = buscar_jornadas(usuario_id)
        dia = request.args.get("dia", type=int)
        jornada_edicao = next(
            (jornada.copy() for jornada in jornadas if jornada["dia_semana"] == dia),
            {"dia_semana": dia if dia in range(7) else 0},
        )
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_edicao=usuario,
            aba_edicao=aba_edicao,
            jornadas=jornadas,
            jornada_edicao=jornada_edicao,
        )

    if request.method == "POST":
        dados, erro = validar_dados_usuario(request.form)
        ativo = request.form.get("ativo") == "on"
        dados_edicao = {**usuario, **request.form, "ativo": ativo}

        if erro:
            return renderizar_lista_usuarios(
                filtro,
                busca,
                usuario_edicao=dados_edicao,
                erro_edicao=erro,
            )

        if buscar_conflito_usuario(usuario_id, dados["login"], dados["email"]):
            return renderizar_lista_usuarios(
                filtro,
                busca,
                usuario_edicao=dados_edicao,
                erro_edicao="Esse login ou email já está sendo usado por outro usuário.",
            )

        if dados["tipo_conta"] == "Suporte" and buscar_outro_suporte(usuario_id):
            return renderizar_lista_usuarios(
                filtro,
                busca,
                usuario_edicao=dados_edicao,
                erro_edicao="Já existe uma conta com a permissão Suporte.",
            )

        with criar_conexao() as conexao:
            conexao.execute(
                """
                UPDATE usuarios
                SET nome_completo = %s,
                    login = %s,
                    email = %s,
                    telefone = %s,
                    tipo_conta = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    dados["nome_completo"],
                    dados["login"],
                    dados["email"],
                    dados["telefone"],
                    dados["tipo_conta"],
                    ativo,
                    usuario_id,
                ),
            )

    return redirect(url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca))


@rota_usuarios.post("/usuarios/<int:usuario_id>/jornada")
@exigir_tipos_conta("Suporte", "Administração")
def salvar_jornada(usuario_id):
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    usuario = buscar_usuario(usuario_id)
    if not usuario:
        return redirect(url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca))

    try:
        dia = int(request.form.get("dia_semana", ""))
    except ValueError:
        dia = -1
    valores = {
        "dia_semana": dia,
        "entrada": request.form.get("entrada", ""),
        "intervalo": request.form.get("intervalo", ""),
        "retorno_intervalo": request.form.get("retorno_intervalo", ""),
        "saida": request.form.get("saida", ""),
    }
    campos_horario = ("entrada", "intervalo", "retorno_intervalo", "saida")
    horarios = []
    try:
        horarios = [time.fromisoformat(valores[campo]) for campo in campos_horario]
    except ValueError:
        pass
    if (
        dia not in range(7)
        or len(horarios) != 4
        or not all(horarios[indice] < horarios[indice + 1] for indice in range(3))
    ):
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_edicao=usuario,
            aba_edicao="jornada",
            jornadas=buscar_jornadas(usuario_id),
            jornada_edicao=valores,
            erro_jornada="Informe os quatro horários em ordem: entrada, intervalo, retorno e saída.",
        )

    with criar_conexao() as conexao:
        conexao.execute(
            """
            INSERT INTO jornadas_usuarios
                (usuario_id, dia_semana, entrada, intervalo, retorno_intervalo, saida)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (usuario_id, dia_semana) DO UPDATE SET
                entrada = EXCLUDED.entrada,
                intervalo = EXCLUDED.intervalo,
                retorno_intervalo = EXCLUDED.retorno_intervalo,
                saida = EXCLUDED.saida
            """,
            (
                usuario_id,
                dia,
                valores["entrada"],
                valores["intervalo"],
                valores["retorno_intervalo"],
                valores["saida"],
            ),
        )
    return redirect(
        url_for(
            "usuarios.editar_usuario",
            usuario_id=usuario_id,
            filtro=filtro,
            busca=busca,
            aba="jornada",
            dia=dia,
        )
    )


@rota_usuarios.post("/usuarios/<int:usuario_id>/jornada/<int:dia>/excluir")
@exigir_tipos_conta("Suporte", "Administração")
def excluir_jornada(usuario_id, dia):
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    with criar_conexao() as conexao:
        conexao.execute(
            "DELETE FROM jornadas_usuarios WHERE usuario_id = %s AND dia_semana = %s",
            (usuario_id, dia),
        )
    return redirect(
        url_for(
            "usuarios.editar_usuario",
            usuario_id=usuario_id,
            filtro=filtro,
            busca=busca,
            aba="jornada",
        )
    )


@rota_usuarios.route("/usuarios/<int:usuario_id>/redefinir-senha", methods=["POST"])
@exigir_tipos_conta("Suporte", "Administração")
def redefinir_senha(usuario_id):
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    with criar_conexao() as conexao:
        conexao.execute(
            """
            UPDATE usuarios
            SET senha_hash = %s, deve_trocar_senha = TRUE
            WHERE id = %s
            """,
            (generate_password_hash("102030"), usuario_id),
        )

    return redirect(
        url_for(
            "usuarios.exibir_usuarios",
            filtro=filtro,
            busca=busca,
            resultado="senha",
        )
    )


@rota_usuarios.route("/usuarios/<int:usuario_id>/excluir", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def excluir_usuario(usuario_id):
    filtro = request.values.get("filtro", "nome")
    busca = request.values.get("busca", "").strip()
    usuario = buscar_usuario(usuario_id)
    if not usuario:
        return redirect(url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca))

    if request.method == "GET":
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_edicao=usuario,
            confirmar_exclusao=usuario,
        )

    if usuario["tipo_conta"] == "Suporte" or usuario_id == session.get("usuario_id"):
        return renderizar_lista_usuarios(
            filtro,
            busca,
            usuario_edicao=usuario,
            erro_edicao="Essa conta não pode ser excluída.",
        )

    with criar_conexao() as conexao:
        conexao.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))

    return redirect(
        url_for("usuarios.exibir_usuarios", filtro=filtro, busca=busca, resultado="excluido")
    )
