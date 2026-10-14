from calendar import monthrange
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Blueprint, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_planilha = Blueprint("planilha", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TIPOS_BATIDA = ("Entrada", "Intervalo", "Retorno intervalo", "Saída")
TIPOS_PERIODO = {"dia", "semana", "mes", "intervalo"}


def buscar_colaboradores():
    with criar_conexao() as conexao:
        return conexao.execute(
            """
            SELECT id, nome_completo, tipo_conta
            FROM usuarios
            WHERE tipo_conta IN ('Administração', 'Professor', 'Colaborador')
            ORDER BY nome_completo
            """
        ).fetchall()


def converter_data(valor):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
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
        inicio = referencia - timedelta(days=referencia.weekday())
        return inicio, inicio + timedelta(days=6), None

    if tipo == "mes":
        try:
            ano, mes = (int(parte) for parte in formulario.get("mes", "").split("-"))
            inicio = date(ano, mes, 1)
        except (TypeError, ValueError):
            return None, None, "Informe um mês válido."
        return inicio, date(ano, mes, monthrange(ano, mes)[1]), None

    inicio = converter_data(formulario.get("data_inicio"))
    fim = converter_data(formulario.get("data_fim"))
    if not inicio or not fim:
        return None, None, "Informe as duas datas do período."
    if inicio > fim:
        return None, None, "A data inicial deve ser anterior à data final."
    return inicio, fim, None


def buscar_registros(inicio, fim, usuario_id=None):
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
    if usuario_id:
        consulta += " AND registro.usuario_id = %s"
        parametros.append(usuario_id)
    consulta += " ORDER BY registro.data_ponto, registro.usuario_nome, registro.registrado_em"
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta, parametros)
            return cursor.fetchall()


def buscar_jornadas(usuario_id=None):
    consulta = """
        SELECT jornada.usuario_id, jornada.dia_semana,
               jornada.entrada, jornada.intervalo,
               jornada.retorno_intervalo, jornada.saida
        FROM jornadas_usuarios AS jornada
        JOIN usuarios AS usuario ON usuario.id = jornada.usuario_id
        WHERE usuario.tipo_conta IN ('Administração', 'Professor', 'Colaborador')
    """
    parametros = []
    if usuario_id:
        consulta += " AND jornada.usuario_id = %s"
        parametros.append(usuario_id)
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta, parametros)
            registros = cursor.fetchall()

    jornadas = {}
    for id_usuario, dia, entrada, intervalo, retorno, saida in registros:
        jornadas.setdefault(id_usuario, {})[dia] = (entrada, intervalo, retorno, saida)
    return jornadas


def duracao_horario(inicio, fim):
    duracao = datetime.combine(date.min, fim) - datetime.combine(date.min, inicio)
    return duracao if duracao >= timedelta() else duracao + timedelta(days=1)


def calcular_totais(registros, jornadas, inicio, fim, usuario_id=None):
    batidas = {}
    ids_com_registros = set()
    for id_usuario, nome, tipo_conta, dia, tipo, registrado_em in registros:
        if id_usuario is None:
            continue
        batidas.setdefault((id_usuario, dia), {})[tipo] = registrado_em
        ids_com_registros.add(id_usuario)

    ids = {id_usuario for id_usuario in jornadas}
    if usuario_id:
        ids = {usuario_id}
    else:
        ids |= ids_com_registros

    horas_trabalhadas = timedelta()
    for eventos in batidas.values():
        if eventos.get("Entrada") and eventos.get("Intervalo"):
            horas_trabalhadas += eventos["Intervalo"] - eventos["Entrada"]
        if eventos.get("Retorno intervalo") and eventos.get("Saída"):
            horas_trabalhadas += eventos["Saída"] - eventos["Retorno intervalo"]

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
            entrada, intervalo, retorno, saida = jornada
            esperado = duracao_horario(entrada, intervalo) + duracao_horario(retorno, saida)
            eventos = batidas.get((id_usuario, dia), {})
            realizado = timedelta()
            if eventos.get("Entrada") and eventos.get("Intervalo"):
                realizado += eventos["Intervalo"] - eventos["Entrada"]
            if eventos.get("Retorno intervalo") and eventos.get("Saída"):
                realizado += eventos["Saída"] - eventos["Retorno intervalo"]
            horas_pendentes += max(esperado - realizado, timedelta())
            dias_com_jornada += 1

    return horas_trabalhadas, horas_pendentes, dias_com_jornada


def formatar_periodo(inicio, fim):
    if inicio == fim:
        return inicio.strftime("%d/%m/%Y")
    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


def criar_planilha(registros, inicio, fim, tipo_batida, nome_colaborador, totais):
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Registros de ponto"
    planilha.sheet_view.showGridLines = False
    planilha.merge_cells("A1:E1")
    planilha["A1"] = "Relatório de ponto eletrônico"
    planilha["A1"].font = Font(name="Aptos Display", size=16, bold=True, color="FFFFFF")
    planilha["A1"].fill = PatternFill("solid", fgColor="24364B")
    planilha["A1"].alignment = Alignment(vertical="center")
    planilha.row_dimensions[1].height = 32
    planilha.merge_cells("A2:E2")
    planilha["A2"] = f"Colaborador: {nome_colaborador}  |  Período: {formatar_periodo(inicio, fim)}  |  Tipo: {tipo_batida}"
    planilha["A2"].font = Font(name="Aptos", size=10, color="425466")

    cabecalhos = ("Data", "Colaborador", "Permissão", "Tipo de ponto", "Horário")
    linha_cabecalho = 4
    for coluna, titulo in enumerate(cabecalhos, start=1):
        celula = planilha.cell(linha_cabecalho, coluna, titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="314B66")
        celula.alignment = Alignment(vertical="center")

    linhas = [registro for registro in registros if tipo_batida == "Todas" or registro[4] == tipo_batida]
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

    horas_trabalhadas, horas_pendentes, dias_com_jornada = totais
    linha_resumo = fim_tabela + 3
    planilha.cell(linha_resumo, 1, "Resumo do período").font = Font(bold=True, color="24364B", size=12)
    planilha.cell(linha_resumo + 1, 1, "Horas trabalhadas")
    planilha.cell(linha_resumo + 1, 2, horas_trabalhadas.total_seconds() / 86400)
    planilha.cell(linha_resumo + 1, 2).number_format = "[h]:mm"
    planilha.cell(linha_resumo + 2, 1, "Horas pendentes")
    planilha.cell(linha_resumo + 2, 2, horas_pendentes.total_seconds() / 86400)
    planilha.cell(linha_resumo + 2, 2).number_format = "[h]:mm"
    planilha.merge_cells(start_row=linha_resumo + 4, start_column=1, end_row=linha_resumo + 4, end_column=5)
    planilha.cell(
        linha_resumo + 4,
        1,
        f"Horas pendentes baseadas nas jornadas cadastradas. Dias com jornada cadastrada no período: {dias_com_jornada}.",
    ).font = Font(size=9, italic=True, color="667788")

    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return arquivo


def dados_formulario(formulario):
    return {
        "periodo": formulario.get("periodo", "dia"),
        "data_referencia": formulario.get("data_referencia", ""),
        "mes": formulario.get("mes", ""),
        "data_inicio": formulario.get("data_inicio", ""),
        "data_fim": formulario.get("data_fim", ""),
        "usuario_id": formulario.get("usuario_id", ""),
        "tipo_batida": formulario.get("tipo_batida", "Todas"),
    }


@rota_planilha.route("/planilha", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def exibir_planilha():
    campos = dados_formulario(request.form if request.method == "POST" else request.args)
    erro = None
    if request.method == "POST":
        inicio, fim, erro = obter_periodo(request.form)
        usuario_id = campos["usuario_id"] or None
        if usuario_id:
            try:
                usuario_id = int(usuario_id)
            except ValueError:
                erro = "Selecione um colaborador válido."
        tipo_batida = campos["tipo_batida"]
        if tipo_batida not in {"Todas", *TIPOS_BATIDA}:
            erro = "Selecione um tipo de ponto válido."
        if not erro:
            colaboradores = buscar_colaboradores()
            colaborador_selecionado = next(
                (colaborador for colaborador in colaboradores if colaborador[0] == usuario_id),
                None,
            ) if usuario_id else None
            if usuario_id and not colaborador_selecionado:
                erro = "O colaborador selecionado não foi encontrado."
            else:
                registros = buscar_registros(inicio, fim, usuario_id)
                jornadas = buscar_jornadas(usuario_id)
                totais = calcular_totais(registros, jornadas, inicio, fim, usuario_id)
                nome = colaborador_selecionado[1] if colaborador_selecionado else "Todos"
                arquivo = criar_planilha(registros, inicio, fim, tipo_batida, nome, totais)
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
        colaboradores=buscar_colaboradores(),
        campos=campos,
        erro_planilha=erro,
    )
