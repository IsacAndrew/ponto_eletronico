import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, g, jsonify, redirect, request, session, url_for
from psycopg.errors import UniqueViolation

from .banco_dados import criar_conexao
from .estrutura_registros import garantir_indices_registros
from .estrutura_usuarios import garantir_estrutura_usuarios
from .localizacao import garantir_tabela_marco_zero, obter_marco_zero
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_configuracoes = Blueprint("configuracoes", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TIPOS_BATIDA = ("Entrada", "Intervalo", "Retorno intervalo", "Saída")


def obter_filtros_registros(fonte):
    return {
        "nome": fonte.get("nome", "").strip()[:120],
        "data": fonte.get("data", "").strip(),
        "login": fonte.get("login", "").strip()[:120],
        "email": fonte.get("email", "").strip()[:200],
    }


def buscar_registros_ponto(filtros):
    garantir_indices_registros()
    consulta = """
        SELECT registro.id,
               COALESCE(registro.usuario_nome, usuario.nome_completo, 'Acesso removido'),
               COALESCE(usuario.login, ''), COALESCE(usuario.email, ''),
               registro.tipo_batida,
               TO_CHAR(registro.registrado_em AT TIME ZONE 'America/Sao_Paulo',
                       'DD/MM/YYYY HH24:MI')
        FROM registros_ponto AS registro
        LEFT JOIN usuarios AS usuario ON usuario.id = registro.usuario_id
        WHERE TRUE
    """
    parametros = []
    if filtros["nome"]:
        consulta += " AND COALESCE(registro.usuario_nome, usuario.nome_completo, '') ILIKE %s"
        parametros.append(f"%{filtros['nome']}%")
    if filtros["data"]:
        consulta += " AND registro.data_ponto = %s"
        parametros.append(date.fromisoformat(filtros["data"]))
    if filtros["login"]:
        consulta += " AND usuario.login ILIKE %s"
        parametros.append(f"%{filtros['login']}%")
    if filtros["email"]:
        consulta += " AND usuario.email ILIKE %s"
        parametros.append(f"%{filtros['email']}%")
    consulta += " ORDER BY registro.registrado_em DESC, registro.id DESC LIMIT 500"
    with criar_conexao() as conexao:
        return conexao.execute(consulta, parametros).fetchall()


@rota_configuracoes.route("/configuracoes")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def exibir_configuracoes():
    garantir_estrutura_usuarios()
    latitude = longitude = None
    endereco = ""
    raio = 100
    configurado = False
    with criar_conexao() as conexao:
        perfil = conexao.execute(
            "SELECT nome_completo, login, email, telefone, rg FROM usuarios WHERE id = %s",
            (session["usuario_id"],),
        ).fetchone()
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
        perfil=perfil,
        mensagem_perfil=request.args.get("perfil"),
    )


@rota_configuracoes.post("/configuracoes/perfil")
@exigir_tipos_conta("Suporte", "Administração", "Professor", "Colaborador")
def salvar_perfil():
    nome = request.form.get("nome_completo", "").strip()
    login = request.form.get("login", "").strip()
    email = request.form.get("email", "").strip()
    telefone = request.form.get("telefone", "").strip()
    rg = request.form.get("rg", "").strip() or None
    usuario_id = session["usuario_id"]
    if len(nome.split()) < 2 or len(nome) > 200:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="nome_invalido"))
    if not login or len(login) > 120:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="login_invalido"))
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="email_invalido"))
    if not re.fullmatch(r"\(\d{2}\) \d{5}-\d{4}", telefone):
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="telefone_invalido"))
    if len(rg or "") > 30:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="rg_invalido"))

    with criar_conexao() as conexao:
        conflito = conexao.execute(
            "SELECT id FROM usuarios WHERE id <> %s AND (login = %s OR email = %s) LIMIT 1",
            (usuario_id, login, email),
        ).fetchone()
        if conflito:
            return redirect(url_for("configuracoes.exibir_configuracoes", perfil="duplicado"))
        conexao.execute(
            """UPDATE usuarios SET nome_completo = %s, login = %s, email = %s, telefone = %s, rg = %s
               WHERE id = %s""",
            (nome, login, email, telefone, rg, usuario_id),
        )
    session["usuario_nome"] = nome
    return redirect(url_for("configuracoes.exibir_configuracoes", perfil="salvo"))


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


@rota_configuracoes.get("/configuracoes/registros-ponto")
@exigir_tipos_conta("Suporte")
def exibir_registros_ponto():
    filtros = obter_filtros_registros(request.args)
    erro = None
    data_filtro_exibicao = filtros["data"]
    if filtros["data"]:
        try:
            try:
                data_filtro = date.fromisoformat(filtros["data"])
            except ValueError:
                data_filtro = datetime.strptime(filtros["data"], "%d/%m/%Y").date()
            filtros["data"] = data_filtro.isoformat()
            data_filtro_exibicao = data_filtro.strftime("%d/%m/%Y")
        except ValueError:
            filtros["data"] = ""
            data_filtro_exibicao = ""
            erro = "Informe uma data válida."
    registros = buscar_registros_ponto(filtros)
    return renderizar_pagina(
        "registros_ponto.html",
        "configuracoes",
        filtros_registros=filtros,
        data_filtro_exibicao=data_filtro_exibicao,
        registros_ponto=registros,
        resultado_registros=request.args.get("resultado"),
        erro_registros=erro,
        tipos_batida=TIPOS_BATIDA,
    )


@rota_configuracoes.post("/configuracoes/registros-ponto/<int:registro_id>/editar")
@exigir_tipos_conta("Suporte")
def editar_registro_ponto(registro_id):
    filtros = obter_filtros_registros(request.form)
    tipo = request.form.get("tipo_batida", "")
    horario_texto = request.form.get("registrado_em", "")
    try:
        horario = datetime.strptime(horario_texto, "%d/%m/%Y %H:%M").replace(
            tzinfo=FUSO_HORARIO
        )
    except ValueError:
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="horario_invalido")
        )
    if tipo not in TIPOS_BATIDA:
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="tipo_invalido")
        )

    try:
        with criar_conexao() as conexao:
            atualizacao = conexao.execute(
                """
                UPDATE registros_ponto
                SET tipo_batida = %s, registrado_em = %s, data_ponto = %s
                WHERE id = %s
                """,
                (tipo, horario, horario.date(), registro_id),
            )
            resultado = "salvo" if atualizacao.rowcount else "nao_encontrado"
    except UniqueViolation:
        resultado = "duplicado"
    return redirect(
        url_for("configuracoes.exibir_registros_ponto", **filtros, resultado=resultado)
    )


@rota_configuracoes.post("/configuracoes/registros-ponto/<int:registro_id>/excluir")
@exigir_tipos_conta("Suporte")
def excluir_registro_ponto(registro_id):
    filtros = obter_filtros_registros(request.form)
    with criar_conexao() as conexao:
        exclusao = conexao.execute(
            "DELETE FROM registros_ponto WHERE id = %s", (registro_id,)
        )
    resultado = "excluido" if exclusao.rowcount else "nao_encontrado"
    return redirect(
        url_for("configuracoes.exibir_registros_ponto", **filtros, resultado=resultado)
    )
