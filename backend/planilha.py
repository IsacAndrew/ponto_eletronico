from calendar import monthrange
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Blueprint, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

from .banco_dados import criar_conexao
from .jornada import garantir_estrutura_jornada
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_planilha = Blueprint("planilha", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TIPOS_PERIODO = {"dia", "semana", "mes", "ano"}


def buscar_usuarios_exportacao():
    garantir_estrutura_jornada()
    with criar_conexao() as conexao:
        return conexao.execute(
            """
            SELECT id, nome_completo, tipo_conta, quantidade_batidas, dias_trabalho_semana
            FROM usuarios
            ORDER BY nome_completo
            """
        ).fetchall()


def converter_data(valor):
    if not valor:
        return None
    for formato in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, formato).date()
        except (TypeError, ValueError):
            pass
    return None


def obter_periodo(formulario):
    tipo = formulario.get("periodo", "dia")
    if tipo not in TIPOS_PERIODO:
        return None, None, "Selecione um tipo de período válido."

    if tipo in {"dia", "semana"}:
        referencia = converter_data(formulario.get("data_referencia"))
        if not referencia:
            return None, None, "Informe uma data válida para o período."
        if tipo == "dia":
            return referencia, referencia, None
        inicio = referencia - timedelta(days=(referencia.weekday() + 1) % 7)
        return inicio, inicio + timedelta(days=6), None

    if tipo == "mes":
        try:
            valor_mes = formulario.get("mes", "")
            if "/" in valor_mes:
                mes, ano = (int(parte) for parte in valor_mes.split("/"))
            else:
                ano, mes = (int(parte) for parte in valor_mes.split("-"))
            inicio = date(ano, mes, 1)
        except (TypeError, ValueError):
            return None, None, "Informe um mês válido."
        return inicio, date(ano, mes, monthrange(ano, mes)[1]), None

    try:
        ano = int(formulario.get("ano", ""))
        return date(ano, 1, 1), date(ano, 12, 31), None
    except (TypeError, ValueError):
        return None, None, "Informe um ano válido."


def buscar_registros(inicio, fim, ids_usuarios=None):
    consulta = """
        SELECT registro.usuario_id,
               COALESCE(usuario.nome_completo, registro.usuario_nome, 'Usuário removido'),
               COALESCE(usuario.tipo_conta, 'Acesso removido'),
               registro.data_ponto,
               registro.tipo_batida,
               registro.registrado_em
        FROM registros_ponto AS registro
        LEFT JOIN usuarios AS usuario ON usuario.id = registro.usuario_id
        WHERE registro.data_ponto BETWEEN %s AND %s
    """
    parametros = [inicio, fim]
    if ids_usuarios is not None:
        if not ids_usuarios:
            return []
        consulta += " AND registro.usuario_id = ANY(%s)"
        parametros.append(ids_usuarios)
    consulta += " ORDER BY registro.data_ponto, registro.usuario_nome, registro.registrado_em"
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta, parametros)
            return cursor.fetchall()


def buscar_jornadas(ids_usuarios=None):
    garantir_estrutura_jornada()
    consulta = """
        SELECT jornada.usuario_id, jornada.dia_semana,
               jornada.entrada, jornada.intervalo,
               jornada.retorno_intervalo, jornada.saida,
               usuario.quantidade_batidas
        FROM jornadas_usuarios AS jornada
        JOIN usuarios AS usuario ON usuario.id = jornada.usuario_id
        WHERE TRUE
    """
    parametros = []
    if ids_usuarios is not None:
        if not ids_usuarios:
            return {}
        consulta += " AND jornada.usuario_id = ANY(%s)"
        parametros.append(ids_usuarios)
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta, parametros)
            registros = cursor.fetchall()

    jornadas = {}
    for id_usuario, dia, entrada, intervalo, retorno, saida, quantidade in registros:
        jornadas.setdefault(id_usuario, {})[dia] = (
            entrada, intervalo, retorno, saida, quantidade
        )
    return jornadas


def duracao_horario(inicio, fim):
    duracao = datetime.combine(date.min, fim) - datetime.combine(date.min, inicio)
    return duracao if duracao >= timedelta() else duracao + timedelta(days=1)


def calcular_totais(registros, jornadas, inicio, fim, ids_usuarios=None):
    batidas = {}
    ids_com_registros = set()
    for id_usuario, nome, tipo_conta, dia, tipo, registrado_em in registros:
        if id_usuario is None:
            continue
        batidas.setdefault((id_usuario, dia), {})[tipo] = registrado_em
        ids_com_registros.add(id_usuario)

    ids = {id_usuario for id_usuario in jornadas}
    if ids_usuarios is not None:
        ids = set(ids_usuarios)
    else:
        ids |= ids_com_registros

    horas_trabalhadas = timedelta()
    for (id_usuario, _), eventos in batidas.items():
        if "Intervalo" in eventos or "Retorno intervalo" in eventos:
            if eventos.get("Entrada") and eventos.get("Intervalo"):
                horas_trabalhadas += eventos["Intervalo"] - eventos["Entrada"]
            if eventos.get("Retorno intervalo") and eventos.get("Saída"):
                horas_trabalhadas += eventos["Saída"] - eventos["Retorno intervalo"]
        elif eventos.get("Entrada") and eventos.get("Saída"):
            horas_trabalhadas += eventos["Saída"] - eventos["Entrada"]

    horas_pendentes = timedelta()
    dias_com_jornada = 0
    hoje = datetime.now(FUSO_HORARIO).date()
    for id_usuario in ids:
        for numero_dia in range((fim - inicio).days + 1):
            dia = inicio + timedelta(days=numero_dia)
            if dia > hoje:
                continue
            jornada = jornadas.get(id_usuario, {}).get(dia.weekday())
            if not jornada:
                continue
            entrada, intervalo, retorno, saida, quantidade = jornada
            if quantidade == 2:
                esperado = duracao_horario(entrada, saida)
            elif intervalo and retorno:
                esperado = duracao_horario(entrada, intervalo) + duracao_horario(retorno, saida)
            else:
                continue
            eventos = batidas.get((id_usuario, dia), {})
            realizado = timedelta()
            if "Intervalo" in eventos or "Retorno intervalo" in eventos:
                if eventos.get("Entrada") and eventos.get("Intervalo"):
                    realizado += eventos["Intervalo"] - eventos["Entrada"]
                if eventos.get("Retorno intervalo") and eventos.get("Saída"):
                    realizado += eventos["Saída"] - eventos["Retorno intervalo"]
            elif eventos.get("Entrada") and eventos.get("Saída"):
                realizado = eventos["Saída"] - eventos["Entrada"]
            horas_pendentes += max(esperado - realizado, timedelta())
            dias_com_jornada += 1

    return horas_trabalhadas, horas_pendentes, dias_com_jornada


def formatar_periodo(inicio, fim):
    if inicio == fim:
        return inicio.strftime("%d/%m/%Y")
    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


def criar_planilha(registros, inicio, fim, nome_colaborador, totais):
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Registros de ponto"
    planilha.sheet_view.showGridLines = False
    planilha.merge_cells("A1:F1")
    planilha["A1"] = "Relatório de ponto eletrônico"
    planilha["A1"].font = Font(name="Aptos Display", size=16, bold=True, color="FFFFFF")
    planilha["A1"].fill = PatternFill("solid", fgColor="24364B")
    planilha["A1"].alignment = Alignment(vertical="center")
    planilha.row_dimensions[1].height = 32
    planilha.merge_cells("A2:F2")
    planilha["A2"] = f"Colaborador: {nome_colaborador}  |  Período: {formatar_periodo(inicio, fim)}"
    planilha["A2"].font = Font(name="Aptos", size=10, color="425466")

    cabecalhos = ("Data", "Colaborador", "Permissão", "Tipo de ponto", "Horário")
    linha_cabecalho = 4
    for coluna, titulo in enumerate(cabecalhos, start=1):
        celula = planilha.cell(linha_cabecalho, coluna, titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="314B66")
        celula.alignment = Alignment(vertical="center")

    linhas = list(registros)
    for linha, registro in enumerate(linhas, start=linha_cabecalho + 1):
        _, nome, tipo_conta, dia, tipo, horario = registro
        horario_local = horario.astimezone(FUSO_HORARIO) if horario.tzinfo else horario
        valores = (dia, nome, tipo_conta, tipo, horario_local.replace(tzinfo=None))
        for coluna, valor in enumerate(valores, start=1):
            celula = planilha.cell(linha, coluna, valor)
            if linha % 2:
                celula.fill = PatternFill("solid", fgColor="F1F5F4")
        planilha.cell(linha, 1).number_format = "dd/mm/yyyy"
        planilha.cell(linha, 5).number_format = "hh:mm:ss"

    fim_tabela = max(linha_cabecalho, linha_cabecalho + len(linhas))
    if linhas:
        tabela = Table(displayName="RegistrosPonto", ref=f"A{linha_cabecalho}:E{fim_tabela}")
        tabela.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False,
            showLastColumn=False, showRowStripes=True, showColumnStripes=False,
        )
        planilha.add_table(tabela)
    else:
        planilha.auto_filter.ref = f"A{linha_cabecalho}:E{fim_tabela}"
    planilha.freeze_panes = "A5"
    planilha.column_dimensions["A"].width = 14
    planilha.column_dimensions["B"].width = 34
    planilha.column_dimensions["C"].width = 20
    planilha.column_dimensions["D"].width = 22
    planilha.column_dimensions["E"].width = 16
    planilha.column_dimensions["F"].width = 16

    horas_trabalhadas, horas_pendentes, dias_com_jornada = totais
    linha_resumo = fim_tabela + 3
    planilha.cell(linha_resumo, 1, "Resumo do período").font = Font(bold=True, color="24364B", size=12)
    planilha.cell(linha_resumo + 1, 1, "Horas trabalhadas")
    planilha.cell(linha_resumo + 1, 2, horas_trabalhadas.total_seconds() / 86400)
    planilha.cell(linha_resumo + 1, 2).number_format = "[h]:mm"
    planilha.cell(linha_resumo + 2, 1, "Horas pendentes")
    planilha.cell(linha_resumo + 2, 2, horas_pendentes.total_seconds() / 86400)
    planilha.cell(linha_resumo + 2, 2).number_format = "[h]:mm"
    planilha.merge_cells(start_row=linha_resumo + 4, start_column=1, end_row=linha_resumo + 4, end_column=6)
    planilha.cell(
        linha_resumo + 4,
        1,
        f"Horas pendentes baseadas nas jornadas cadastradas. Dias com jornada cadastrada no período: {dias_com_jornada}.",
    ).font = Font(size=9, italic=True, color="667788")

    linha_assinaturas = linha_resumo + 7
    grupos_assinatura = ((1, 2, "Diretora"), (3, 4, "Administração"), (5, 6, "Colaborador"))
    for coluna_inicio, coluna_fim, funcao in grupos_assinatura:
        planilha.merge_cells(
            start_row=linha_assinaturas,
            start_column=coluna_inicio,
            end_row=linha_assinaturas,
            end_column=coluna_fim,
        )
        planilha.merge_cells(
            start_row=linha_assinaturas + 1,
            start_column=coluna_inicio,
            end_row=linha_assinaturas + 1,
            end_column=coluna_fim,
        )
        linha_assinatura = planilha.cell(linha_assinaturas, coluna_inicio, " ")
        linha_assinatura.border = Border(bottom=Side(style="thin", color="52647A"))
        for coluna in range(coluna_inicio + 1, coluna_fim + 1):
            planilha.cell(linha_assinaturas, coluna).border = Border(
                bottom=Side(style="thin", color="52647A")
            )
        planilha.cell(linha_assinaturas + 1, coluna_inicio, funcao).alignment = Alignment(
            horizontal="center", vertical="center"
        )
    planilha.row_dimensions[linha_assinaturas].height = 24
    planilha.row_dimensions[linha_assinaturas + 1].height = 20

    planilha.page_setup.paperSize = planilha.PAPERSIZE_A4
    planilha.page_setup.orientation = "landscape"
    planilha.page_setup.fitToWidth = 1
    planilha.page_setup.fitToHeight = 0
    planilha.sheet_properties.pageSetUpPr.fitToPage = True
    planilha.page_margins.left = 0.3
    planilha.page_margins.right = 0.3
    planilha.page_margins.top = 0.5
    planilha.page_margins.bottom = 0.5
    planilha.print_area = f"A1:F{linha_assinaturas + 1}"

    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return arquivo


def dados_formulario(formulario):
    return {
        "periodo": formulario.get("periodo", "dia"),
        "data_referencia": formulario.get("data_referencia", ""),
        "mes": formulario.get("mes", ""),
        "ano": formulario.get("ano", ""),
        "escopo": formulario.get("escopo", "todos"),
    }


def filtrar_colaboradores(colaboradores, escopo):
    if escopo == "todos":
        return colaboradores, "Todos os usuários"
    if not escopo.startswith("usuario:"):
        return None, ""
    try:
        usuario_id = int(escopo.split(":", 1)[1])
    except ValueError:
        return None, ""
    selecionados = [usuario for usuario in colaboradores if usuario[0] == usuario_id]
    return selecionados, selecionados[0][1] if selecionados else ""


@rota_planilha.route("/planilha", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def exibir_planilha():
    campos = dados_formulario(request.form if request.method == "POST" else request.args)
    erro = None
    if request.method == "POST":
        inicio, fim, erro = obter_periodo(request.form)
        escopo = campos["escopo"]
        if escopo != "todos" and not escopo.startswith("usuario:"):
            erro = "Selecione um usuário válido."
        if not erro:
            colaboradores = buscar_usuarios_exportacao()
            selecionados, nome = filtrar_colaboradores(colaboradores, escopo)
            if not selecionados:
                erro = "Nenhum usuário corresponde à seleção."
            else:
                ids_usuarios = [usuario[0] for usuario in selecionados]
                registros = buscar_registros(inicio, fim, ids_usuarios)
                jornadas = buscar_jornadas(ids_usuarios)
                totais = calcular_totais(registros, jornadas, inicio, fim, ids_usuarios)
                arquivo = criar_planilha(registros, inicio, fim, nome, totais)
                nome_arquivo = f"ponto_{inicio.isoformat()}_{fim.isoformat()}.xlsx"
                return send_file(
                    arquivo,
                    as_attachment=True,
                    download_name=nome_arquivo,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    return renderizar_pagina(
        "planilha.html",
        "planilha",
        colaboradores=buscar_usuarios_exportacao(),
        campos=campos,
        erro_planilha=erro,
    )
