import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, g, jsonify, redirect, request, session, url_for
from psycopg.errors import UniqueViolation

from .banco_dados import criar_conexao
from .formatacao import formatar_rg
from .estrutura_registros import garantir_indices_registros
from .estrutura_usuarios import garantir_estrutura_usuarios
from .localizacao import garantir_tabela_marco_zero, obter_marco_zero
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_configuracoes = Blueprint("configuracoes", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")


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
        SELECT COALESCE(registro.usuario_nome, usuario.nome_completo, 'Acesso removido'),
               registro.data_ponto,
               MAX(registro.id) FILTER (WHERE registro.tipo_batida = 'Entrada'),
               MAX(registro.id) FILTER (WHERE registro.tipo_batida = 'Intervalo'),
               MAX(registro.id) FILTER (WHERE registro.tipo_batida = 'Retorno intervalo'),
               MAX(registro.id) FILTER (WHERE registro.tipo_batida = 'Saída'),
               MAX(TO_CHAR(registro.registrado_em AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI'))
                   FILTER (WHERE registro.tipo_batida = 'Entrada'),
               MAX(TO_CHAR(registro.registrado_em AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI'))
                   FILTER (WHERE registro.tipo_batida = 'Intervalo'),
               MAX(TO_CHAR(registro.registrado_em AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI'))
                   FILTER (WHERE registro.tipo_batida = 'Retorno intervalo'),
               MAX(TO_CHAR(registro.registrado_em AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI'))
                   FILTER (WHERE registro.tipo_batida = 'Saída')
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
    consulta += """
        GROUP BY registro.usuario_id,
                 COALESCE(registro.usuario_nome, usuario.nome_completo, 'Acesso removido'),
                 registro.data_ponto
        ORDER BY registro.data_ponto DESC, 1
        LIMIT 500
    """
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
    try:
        rg = formatar_rg(request.form.get("rg", ""))
    except ValueError:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="rg_invalido"))
    usuario_id = session["usuario_id"]
    if len(nome.split()) < 2 or len(nome) > 200:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="nome_invalido"))
    if not login or len(login) > 120:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="login_invalido"))
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="email_invalido"))
    if not re.fullmatch(r"\(\d{2}\) \d{5}-\d{4}", telefone):
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="telefone_invalido"))

    try:
        with criar_conexao() as conexao:
            conflito = conexao.execute(
                """
                SELECT id FROM usuarios
                WHERE id <> %s
                  AND (
                      LOWER(BTRIM(login)) = LOWER(BTRIM(%s))
                      OR LOWER(BTRIM(email)) = LOWER(BTRIM(%s))
                  )
                LIMIT 1
                """,
                (usuario_id, login, email),
            ).fetchone()
            if conflito:
                return redirect(url_for("configuracoes.exibir_configuracoes", perfil="duplicado"))
            conexao.execute(
                """UPDATE usuarios SET nome_completo = %s, login = %s, email = %s, telefone = %s, rg = %s
                   WHERE id = %s""",
                (nome, login, email, telefone, rg, usuario_id),
            )
    except UniqueViolation:
        return redirect(url_for("configuracoes.exibir_configuracoes", perfil="duplicado"))
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
    hoje = datetime.now(FUSO_HORARIO).date()
    data_filtro_exibicao = hoje.strftime("%d/%m/%Y")
    if filtros["data"]:
        try:
            try:
                data_filtro = date.fromisoformat(filtros["data"])
            except ValueError:
                data_filtro = datetime.strptime(filtros["data"], "%d/%m/%Y").date()
            filtros["data"] = data_filtro.isoformat()
            data_filtro_exibicao = data_filtro.strftime("%d/%m/%Y")
        except ValueError:
            filtros["data"] = hoje.isoformat()
            data_filtro_exibicao = hoje.strftime("%d/%m/%Y")
            erro = "Informe uma data válida."
    else:
        filtros["data"] = hoje.isoformat()
    registros = buscar_registros_ponto(filtros)
    return renderizar_pagina(
        "registros_ponto.html",
        "configuracoes",
        filtros_registros=filtros,
        data_filtro_exibicao=data_filtro_exibicao,
        registros_ponto=registros,
        resultado_registros=request.args.get("resultado"),
        erro_registros=erro,
    )


@rota_configuracoes.post("/configuracoes/registros-ponto/editar")
@exigir_tipos_conta("Suporte")
def editar_registro_ponto():
    filtros = obter_filtros_registros(request.form)
    campos_batida = {
        "entrada": "Entrada",
        "intervalo": "Intervalo",
        "retorno_intervalo": "Retorno intervalo",
        "saida": "Saída",
    }
    ids = {
        tipo: request.form.get(f"id_{campo}", "").strip()
        for campo, tipo in campos_batida.items()
    }
    if any(valor and not valor.isdecimal() for valor in ids.values()):
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="nao_encontrado")
        )
    ids = {tipo: int(valor) if valor else None for tipo, valor in ids.items()}
    ids_existentes = [valor for valor in ids.values() if valor]
    if not ids_existentes:
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="nao_encontrado")
        )
    horarios = {}
    for campo, tipo in campos_batida.items():
        if not ids[tipo]:
            continue
        horario_texto = request.form.get(campo, "").strip()
        if not horario_texto:
            horarios[tipo] = None
            continue
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", horario_texto):
            return redirect(
                url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="horario_invalido")
            )
        try:
            horarios[tipo] = datetime.strptime(horario_texto, "%H:%M").time()
        except ValueError:
            return redirect(
                url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="horario_invalido")
            )
    try:
        with criar_conexao() as conexao:
            registros = conexao.execute(
                """SELECT id, usuario_id, data_ponto, tipo_batida
                   FROM registros_ponto WHERE id = ANY(%s) FOR UPDATE""",
                (ids_existentes,),
            ).fetchall()
            por_id = {registro[0]: registro for registro in registros}
            if len(por_id) != len(ids_existentes) or any(
                registro[3] != tipo
                for tipo, registro_id in ids.items()
                if registro_id and (registro := por_id.get(registro_id)) is not None
            ):
                resultado = "nao_encontrado"
            elif any(registro_id not in por_id for registro_id in ids_existentes):
                resultado = "nao_encontrado"
            elif len({(registro[1], registro[2]) for registro in registros}) != 1:
                resultado = "nao_encontrado"
            else:
                data_ponto = registros[0][2]
                for tipo, registro_id in ids.items():
                    if not registro_id:
                        continue
                    horario = horarios[tipo]
                    if horario is None:
                        conexao.execute(
                            "DELETE FROM registros_ponto WHERE id = %s",
                            (registro_id,),
                        )
                        continue
                    registrado_em = datetime.combine(data_ponto, horario, FUSO_HORARIO)
                    conexao.execute(
                        "UPDATE registros_ponto SET registrado_em = %s WHERE id = %s",
                        (registrado_em, registro_id),
                    )
                resultado = "salvo"
    except UniqueViolation:
        resultado = "duplicado"
    return redirect(
        url_for("configuracoes.exibir_registros_ponto", **filtros, resultado=resultado)
    )


@rota_configuracoes.post("/configuracoes/registros-ponto/excluir")
@exigir_tipos_conta("Suporte")
def excluir_registro_ponto():
    filtros = obter_filtros_registros(request.form)
    ids_texto = [
        request.form.get(f"id_{campo}", "").strip()
        for campo in ("entrada", "intervalo", "retorno_intervalo", "saida")
    ]
    if any(registro_id and not registro_id.isdecimal() for registro_id in ids_texto):
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="nao_encontrado")
        )
    ids = [int(registro_id) for registro_id in ids_texto if registro_id]
    if not ids:
        return redirect(
            url_for("configuracoes.exibir_registros_ponto", **filtros, resultado="nao_encontrado")
        )
    with criar_conexao() as conexao:
        registros = conexao.execute(
            """SELECT id, usuario_id, data_ponto, tipo_batida
               FROM registros_ponto WHERE id = ANY(%s) FOR UPDATE""",
            (ids,),
        ).fetchall()
        por_id = {registro[0]: registro for registro in registros}
        esperado = {
            int(registro_id): tipo
            for campo, tipo in (
                ("entrada", "Entrada"),
                ("intervalo", "Intervalo"),
                ("retorno_intervalo", "Retorno intervalo"),
                ("saida", "Saída"),
            )
            if (registro_id := request.form.get(f"id_{campo}", "").strip())
            and registro_id.isdecimal()
        }
        if (
            len(por_id) != len(ids)
            or len({(registro[1], registro[2]) for registro in registros}) != 1
            or any(por_id.get(registro_id, (None, None, None, None))[3] != tipo
                   for registro_id, tipo in esperado.items())
        ):
            resultado = "nao_encontrado"
        else:
            exclusao = conexao.execute(
                "DELETE FROM registros_ponto WHERE id = ANY(%s)", (ids,)
            )
            resultado = "excluido" if exclusao.rowcount == len(ids) else "nao_encontrado"
    return redirect(
        url_for("configuracoes.exibir_registros_ponto", **filtros, resultado=resultado)
    )
