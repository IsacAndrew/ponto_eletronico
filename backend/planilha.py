from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from io import BytesIO
from statistics import median
from zoneinfo import ZoneInfo

from flask import Blueprint, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .banco_dados import criar_conexao
from .estrutura_registros import garantir_indices_registros
from .jornada import garantir_estrutura_jornada
from .estrutura_usuarios import garantir_estrutura_usuarios
from .atestados import garantir_estrutura_atestados
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_planilha = Blueprint("planilha", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
MESES_ABREVIADOS = (
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
)


def buscar_usuarios_exportacao():
    garantir_estrutura_usuarios()
    garantir_estrutura_jornada()
    with criar_conexao() as conexao:
        return conexao.execute(
            """
            SELECT id, nome_completo, tipo_conta, ativo, rg, funcao,
                   quantidade_batidas, dias_trabalho_semana
            FROM usuarios
            ORDER BY nome_completo
            """
        ).fetchall()


def obter_periodo(formulario):
    try:
        mes = int(formulario.get("mes", ""))
        ano = int(formulario.get("ano", ""))
        if mes not in range(1, 13) or ano not in range(2000, 2101):
            raise ValueError
        inicio = date(ano, mes, 1)
        return inicio, date(ano, mes, monthrange(ano, mes)[1]), None
    except (TypeError, ValueError):
        return None, None, "Selecione um mês e ano válidos."


def buscar_registros(inicio, fim, ids_usuarios=None):
    garantir_indices_registros()
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

    consulta_quantidades = """
        SELECT usuario_id, dia_semana, quantidade_batidas
        FROM quantidades_batidas_semanais
    """
    parametros_quantidades = []
    if ids_usuarios is not None:
        consulta_quantidades += " WHERE usuario_id = ANY(%s)"
        parametros_quantidades.append(ids_usuarios)
    with criar_conexao() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta_quantidades, parametros_quantidades)
            quantidades_semanais = cursor.fetchall()

    for id_usuario, dia, quantidade in quantidades_semanais:
        jornada_existente = jornadas.setdefault(id_usuario, {}).get(dia)
        if jornada_existente:
            entrada, intervalo, retorno, saida, _ = jornada_existente
            jornadas[id_usuario][dia] = (entrada, intervalo, retorno, saida, quantidade)
        elif quantidade:
            jornadas[id_usuario][dia] = (None, None, None, None, quantidade)
        else:
            jornadas.setdefault(id_usuario, {})[dia] = (None, None, None, None, 0)
    return jornadas


def buscar_atestados(inicio, fim, ids_usuarios):
    garantir_estrutura_atestados()
    if not ids_usuarios:
        return {}
    with criar_conexao() as conexao:
        registros = conexao.execute(
            """SELECT usuario_id, data_atestado, dia_inteiro, hora_inicio, hora_fim
               FROM atestados
               WHERE usuario_id = ANY(%s) AND data_atestado BETWEEN %s AND %s
               ORDER BY data_atestado""",
            (ids_usuarios, inicio, fim),
        ).fetchall()
    atestados = defaultdict(lambda: defaultdict(list))
    for usuario_id, dia, dia_inteiro, hora_inicio, hora_fim in registros:
        atestados[usuario_id][dia].append((dia_inteiro, hora_inicio, hora_fim))
    return atestados


DIAS_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
TIPOS_POR_POSICAO = {
    "Entrada": 0,
    "Intervalo": 1,
    "Retorno intervalo": 2,
    "Saída": 3,
}
MINIMO_AMOSTRAS_HORARIO = 3
SEMANAS_PARA_ESTIMATIVA = 8


def nome_aba_unico(nome, titulos_existentes):
    base = "".join("_" if caractere in "[]:*?/\\" else caractere for caractere in nome)
    base = base.strip("'") or "Folha de Frequência"
    titulo = base[:31]
    contador = 2
    titulos_normalizados = {titulo_existente.casefold() for titulo_existente in titulos_existentes}
    while titulo.casefold() in titulos_normalizados:
        sufixo = f" ({contador})"
        titulo = f"{base[:31 - len(sufixo)]}{sufixo}"
        contador += 1
    return titulo


def formatar_duracao(minutos):
    horas, restante = divmod(max(0, int(minutos)), 60)
    return f"{horas}h{restante:02d}"


def valor_duracao_excel(minutos):
    if minutos < 0:
        horas, restante = divmod(abs(int(minutos)), 60)
        return f"-{horas:02d}:{restante:02d}"
    return timedelta(minutes=int(minutos))


def minutos_entre(inicio, fim):
    if not inicio or not fim:
        return 0
    return max(0, int((fim.hour * 60 + fim.minute) - (inicio.hour * 60 + inicio.minute)))


def agrupar_batidas(registros):
    por_usuario_dia = defaultdict(dict)
    for registro in registros:
        id_usuario, _, _, data_ponto, tipo_batida, registrado_em = registro
        if id_usuario is None:
            continue
        por_usuario_dia[id_usuario].setdefault(data_ponto, {})[tipo_batida] = (
            registrado_em.astimezone(FUSO_HORARIO).time().replace(second=0, microsecond=0)
        )
    return por_usuario_dia


def estimar_jornadas(jornadas, batidas, usuarios, inicio_mes):
    limite = inicio_mes - timedelta(weeks=SEMANAS_PARA_ESTIMATIVA)
    amostras = defaultdict(list)
    for id_usuario, dias in batidas.items():
        for data_ponto, registros_dia in dias.items():
            if not limite <= data_ponto < inicio_mes:
                continue
            for tipo, horario in registros_dia.items():
                amostras[(id_usuario, data_ponto.weekday(), tipo)].append(horario)

    jornadas_estimadas = {}
    for usuario in usuarios:
        id_usuario = usuario[0]
        jornadas_estimadas[id_usuario] = {}
        for dia_semana in range(7):
            jornada_manual = jornadas.get(id_usuario, {}).get(dia_semana)
            if jornada_manual:
                entrada, intervalo, retorno, saida, quantidade = jornada_manual
            elif not jornadas.get(id_usuario) and dia_semana < usuario[7]:
                quantidade = usuario[6]
                entrada = intervalo = retorno = saida = None
            else:
                continue
            if quantidade == 0:
                continue
            horarios_manuais = {
                "Entrada": entrada,
                "Intervalo": intervalo,
                "Retorno intervalo": retorno,
                "Saída": saida,
            }
            tipos_esperados = (
                ("Entrada", "Saída") if quantidade == 2 else tuple(TIPOS_POR_POSICAO)
            )
            horarios_estimados = {}
            for tipo in tipos_esperados:
                exemplos = amostras[(id_usuario, dia_semana, tipo)]
                if len(exemplos) >= MINIMO_AMOSTRAS_HORARIO:
                    minutos_medianos = int(median(
                        horario.hour * 60 + horario.minute for horario in exemplos
                    ))
                    arredondados = int((minutos_medianos + 15) // 30) * 30
                    horarios_estimados[tipo] = time(
                        (arredondados // 60) % 24, arredondados % 60
                    )
                else:
                    horarios_estimados[tipo] = horarios_manuais[tipo]

            horarios_em_ordem = [horarios_estimados[tipo] for tipo in tipos_esperados]
            if any(horario is None for horario in horarios_em_ordem):
                horarios_estimados = horarios_manuais
            elif any(
                (proximo.hour, proximo.minute) <= (anterior.hour, anterior.minute)
                for anterior, proximo in zip(horarios_em_ordem, horarios_em_ordem[1:])
            ):
                horarios_estimados = horarios_manuais

            jornadas_estimadas[id_usuario][dia_semana] = {
                "quantidade": quantidade,
                "horarios": horarios_estimados,
            }
    return jornadas_estimadas


def horas_previstas_jornada(jornada):
    horarios = jornada["horarios"]
    if jornada["quantidade"] == 2:
        if not horarios.get("Entrada") or not horarios.get("Saída"):
            return None
        return minutos_entre(horarios.get("Entrada"), horarios.get("Saída"))
    if any(not horarios.get(tipo) for tipo in TIPOS_POR_POSICAO):
        return None
    return (
        minutos_entre(horarios.get("Entrada"), horarios.get("Intervalo"))
        + minutos_entre(horarios.get("Retorno intervalo"), horarios.get("Saída"))
    )


def minutos_abonados_na_jornada(jornada, atestados):
    periodos = [
        (inicio, fim)
        for dia_inteiro, inicio, fim in atestados
        if not dia_inteiro and inicio and fim
    ]
    if not periodos:
        return 0

    horarios = jornada["horarios"] if jornada else {}
    if jornada and jornada["quantidade"] == 2:
        intervalos_trabalho = [(horarios.get("Entrada"), horarios.get("Saída"))]
    elif jornada and jornada["quantidade"] == 4:
        intervalos_trabalho = [
            (horarios.get("Entrada"), horarios.get("Intervalo")),
            (horarios.get("Retorno intervalo"), horarios.get("Saída")),
        ]
    else:
        return sum(
            fim.hour * 60 + fim.minute - (inicio.hour * 60 + inicio.minute)
            for inicio, fim in periodos
        )

    minutos_cobertos = 0
    for inicio_trabalho, fim_trabalho in intervalos_trabalho:
        if not inicio_trabalho or not fim_trabalho:
            continue
        inicio_trabalho = inicio_trabalho.hour * 60 + inicio_trabalho.minute
        fim_trabalho = fim_trabalho.hour * 60 + fim_trabalho.minute
        for inicio_atestado, fim_atestado in periodos:
            inicio_atestado = inicio_atestado.hour * 60 + inicio_atestado.minute
            fim_atestado = fim_atestado.hour * 60 + fim_atestado.minute
            minutos_cobertos += max(
                0,
                min(fim_trabalho, fim_atestado) - max(inicio_trabalho, inicio_atestado),
            )
    return minutos_cobertos


def horas_realizadas(batidas, quantidade):
    if quantidade == 2:
        return minutos_entre(batidas.get("Entrada"), batidas.get("Saída"))
    return (
        minutos_entre(batidas.get("Entrada"), batidas.get("Intervalo"))
        + minutos_entre(batidas.get("Retorno intervalo"), batidas.get("Saída"))
    )


def aplicar_estilo(celula, *, fundo=None, cor="243447", negrito=False,
                   tamanho=9, alinhamento="center", borda=None):
    celula.font = Font(name="Aptos", size=tamanho, bold=negrito, color=cor)
    if fundo:
        celula.fill = PatternFill("solid", fgColor=fundo)
    celula.alignment = Alignment(
        horizontal=alinhamento, vertical="center", wrap_text=True, shrink_to_fit=True
    )
    if borda:
        celula.border = borda


def configurar_folha(planilha, usuario, jornadas_estimadas, batidas_usuario,
                     atestados_usuario, inicio_mes):
    id_usuario, nome, _, ativo, rg, funcao, _, _ = usuario
    azul = "31425E"
    azul_claro = "EAF0F5"
    verde_claro = "E8F1EC"
    cinza = "D6DEE5"
    linha_fina = Side(style="thin", color=cinza)
    borda = Border(left=linha_fina, right=linha_fina, top=linha_fina, bottom=linha_fina)

    for intervalo in ("A1:H1", "A2:H2", "B4:E4", "G4:H4", "B5:H5",
                      "B6:H6", "A8:B8", "A9:B9", "C8:D8", "C9:D9", "E8:F8",
                      "E9:F9", "G8:H8", "G9:H9", "A44:H44",
                      "A45:C45", "D45:E45", "F45:G45",
                      "A54:B54", "D54:E54", "G54:H54",
                      "A55:B55", "D55:E55", "G55:H55"):
        planilha.merge_cells(intervalo)

    planilha["A1"] = "RELATÓRIO MENSAL DE FREQUÊNCIA"
    planilha["A2"] = f"{MESES[inicio_mes.month - 1].upper()} DE {inicio_mes.year}"
    planilha["A4"], planilha["B4"] = "NOME COMPLETO", nome
    planilha["F4"], planilha["G4"] = "RG", rg or "Não informado"
    planilha["A5"], planilha["B5"] = "FUNÇÃO", funcao or "Não informada"
    planilha["A6"] = "JORNADA SEMANAL ESTIMADA"

    dias_previstos = []
    total_semanal = 0
    for dia_semana, jornada in sorted(jornadas_estimadas.get(id_usuario, {}).items()):
        horarios = jornada["horarios"]
        quantidade = jornada["quantidade"]
        total_dia = horas_previstas_jornada(jornada)
        if total_dia is not None:
            total_semanal += total_dia
        if quantidade == 2:
            texto_horarios = (
                f"{horarios['Entrada'].strftime('%H:%M')}–{horarios['Saída'].strftime('%H:%M')}"
                if horarios.get("Entrada") and horarios.get("Saída") else "horário não estimado"
            )
        else:
            chaves = ("Entrada", "Intervalo", "Retorno intervalo", "Saída")
            texto_horarios = " · ".join(
                horarios[chave].strftime("%H:%M") if horarios.get(chave) else "—"
                for chave in chaves
            )
        dias_previstos.append(
            f"{DIAS_SEMANA[dia_semana]} {texto_horarios} "
            f"({formatar_duracao(total_dia) if total_dia is not None else '—'})"
        )
    planilha["B6"] = "   |   ".join(dias_previstos) or "Jornada não configurada"

    colunas_resumo = {
        "A8": "HORAS REALIZADAS NO MÊS",
        "C8": "HORAS PREVISTAS NO MÊS",
        "E8": "SALDO DO MÊS",
        "G8": "JORNADA SEMANAL",
    }
    for celula, texto in colunas_resumo.items():
        planilha[celula] = texto
    planilha["A9"] = 0
    planilha["C9"] = 0
    planilha["E9"] = 0
    planilha["G9"] = timedelta(minutes=total_semanal)
    planilha["A11"] = "DIA"
    for coluna, titulo in enumerate(("1ª ENTRADA", "2ª INTERVALO", "3ª RETORNO", "4ª SAÍDA",
                                     "PREVISTAS", "REALIZADAS", "OCORRÊNCIA"), start=2):
        planilha.cell(11, coluna, titulo)

    hoje = datetime.now(FUSO_HORARIO).date()
    total_dias_mes = monthrange(inicio_mes.year, inicio_mes.month)[1]
    fim_mes = date(inicio_mes.year, inicio_mes.month, total_dias_mes)
    soma_realizadas = 0
    soma_previstas = 0
    totais_semanais = defaultdict(
        lambda: {"previstas": 0, "realizadas": 0, "previsao_parcial": False}
    )
    previsao_mensal_parcial = False
    for numero_dia in range(1, 32):
        linha = 11 + numero_dia
        if numero_dia > total_dias_mes:
            planilha.row_dimensions[linha].hidden = True
            continue
        dia = date(inicio_mes.year, inicio_mes.month, numero_dia)
        jornada = jornadas_estimadas.get(id_usuario, {}).get(dia.weekday())
        batidas_dia = batidas_usuario.get(dia, {})
        atestados_dia = atestados_usuario.get(dia, [])
        planilha.cell(linha, 1, f"{DIAS_SEMANA[dia.weekday()]} · {dia:%d/%m/%Y}")

        for tipo, coluna in (("Entrada", 2), ("Intervalo", 3),
                             ("Retorno intervalo", 4), ("Saída", 5)):
            valor = batidas_dia.get(tipo)
            planilha.cell(linha, coluna, valor if valor else "—")
            if valor:
                planilha.cell(linha, coluna).number_format = "hh:mm"

        prevista = horas_previstas_jornada(jornada) if jornada else 0
        abonacao_integral = any(atestado[0] for atestado in atestados_dia)
        minutos_abonados = minutos_abonados_na_jornada(jornada, atestados_dia)
        if abonacao_integral:
            prevista = 0
        elif prevista is not None and minutos_abonados:
            prevista = max(0, prevista - minutos_abonados)
        conta_para_previsao = bool(jornada and prevista is not None and dia <= hoje)
        if conta_para_previsao:
            soma_previstas += prevista
        inicio_semana = dia - timedelta(days=dia.weekday())
        if conta_para_previsao:
            totais_semanais[inicio_semana]["previstas"] += prevista
        elif jornada and prevista is None and dia <= hoje:
            previsao_mensal_parcial = True
            totais_semanais[inicio_semana]["previsao_parcial"] = True
        planilha.cell(
            linha, 6,
            timedelta(minutes=prevista) if jornada and prevista is not None else "—",
        )

        quantidade = jornada["quantidade"] if jornada else 0
        realizada = horas_realizadas(batidas_dia, quantidade) if jornada else 0
        tem_batida = bool(batidas_dia)
        if tem_batida:
            soma_realizadas += realizada
            totais_semanais[inicio_semana]["realizadas"] += realizada
        if abonacao_integral:
            ocorrencia = "Abonado"
        elif tem_batida:
            esperados = ("Entrada", "Saída") if quantidade == 2 else (
                ("Entrada", "Intervalo", "Retorno intervalo", "Saída") if quantidade == 4 else ()
            )
            registro_incompleto = not (esperados and all(tipo in batidas_dia for tipo in esperados))
            if minutos_abonados:
                ocorrencia = "Incompleto · abono" if registro_incompleto else "Abono parcial"
            else:
                ocorrencia = "Incompleto" if registro_incompleto else "—"
        elif minutos_abonados and jornada:
            ocorrencia = "Ausente parcial"
        elif jornada and dia <= hoje and ativo:
            ocorrencia = "Ausente"
        else:
            ocorrencia = "—"
        planilha.cell(linha, 7, timedelta(minutes=realizada) if tem_batida else "—")
        planilha.cell(linha, 8, ocorrencia)

        cor_linha = "FFFFFF" if numero_dia % 2 else "F5F7F9"
        if ocorrencia.startswith("Ausente"):
            cor_linha = "FCEEEE"
        elif ocorrencia.startswith("Abono") or ocorrencia == "Abonado":
            cor_linha = "EAF4EC"
        elif ocorrencia == "Incompleto":
            cor_linha = "FFF6E5"
        for coluna in range(1, 9):
            aplicar_estilo(planilha.cell(linha, coluna), fundo=cor_linha, tamanho=8, borda=borda)
            if coluna in (6, 7):
                planilha.cell(linha, coluna).number_format = '[h]:mm'

    planilha["A9"] = timedelta(minutes=soma_realizadas)
    planilha["C9"] = timedelta(minutes=soma_previstas)
    planilha["E9"] = (
        "Parcial" if previsao_mensal_parcial
        else valor_duracao_excel(soma_realizadas - soma_previstas)
    )
    for celula in ("A9", "C9", "E9", "G9"):
        planilha[celula].number_format = '[h]:mm;[Red]-[h]:mm'

    planilha["A44"] = "RESUMO SEMANAL"
    planilha["A45"] = "SEMANA"
    planilha["D45"] = "HORAS PREVISTAS"
    planilha["F45"] = "HORAS REALIZADAS"
    planilha["H45"] = "SALDO"
    semanas_do_mes = []
    for dia_numero in range(1, total_dias_mes + 1):
        dia = date(inicio_mes.year, inicio_mes.month, dia_numero)
        inicio_semana = dia - timedelta(days=dia.weekday())
        if inicio_semana not in semanas_do_mes:
            semanas_do_mes.append(inicio_semana)
    for indice in range(6):
        linha = 46 + indice
        if indice >= len(semanas_do_mes):
            planilha.row_dimensions[linha].hidden = True
            continue
        inicio_semana = semanas_do_mes[indice]
        fim_semana = inicio_semana + timedelta(days=6)
        inicio_intervalo = max(inicio_semana, inicio_mes)
        fim_intervalo = min(fim_semana, fim_mes)
        totais = totais_semanais[inicio_semana]
        realizados_semana = totais["realizadas"]
        previstas_semana = totais["previstas"]
        planilha.cell(linha, 1, f"{inicio_intervalo:%d/%m} a {fim_intervalo:%d/%m}")
        planilha.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=3)
        total_previsto_semana = (
            "Parcial" if totais["previsao_parcial"]
            else timedelta(minutes=previstas_semana) if previstas_semana else "—"
        )
        planilha.cell(linha, 4, total_previsto_semana)
        planilha.merge_cells(start_row=linha, start_column=4, end_row=linha, end_column=5)
        planilha.cell(linha, 6, timedelta(minutes=realizados_semana))
        planilha.merge_cells(start_row=linha, start_column=6, end_row=linha, end_column=7)
        planilha.cell(
            linha, 8,
            "Parcial" if totais["previsao_parcial"]
            else valor_duracao_excel(realizados_semana - previstas_semana),
        )
        for coluna in range(1, 9):
            aplicar_estilo(planilha.cell(linha, coluna), fundo="F5F7F9", tamanho=8, borda=borda)
        for coluna in (4, 6):
            planilha.cell(linha, coluna).number_format = "[h]:mm"

    planilha["A54"] = "Sandra Rio Tinto"
    planilha["A55"] = "DIREÇÃO"
    planilha["D54"] = "Beatriz Santo Silva"
    planilha["D55"] = "COORDENAÇÃO"
    planilha["G54"] = "Funcionário(a)"
    planilha["G55"] = "ASSINATURA"

    aplicar_estilo(planilha["A1"], fundo=azul, cor="FFFFFF", negrito=True, tamanho=15)
    aplicar_estilo(planilha["A2"], fundo=azul_claro, cor=azul, negrito=True, tamanho=10)
    for linha in (4, 5):
        aplicar_estilo(planilha.cell(linha, 1), fundo=azul_claro, cor=azul, negrito=True, tamanho=8, alinhamento="left")
    aplicar_estilo(planilha["F4"], fundo=azul_claro, cor=azul, negrito=True, tamanho=8, alinhamento="left")
    aplicar_estilo(planilha["A6"], fundo=azul_claro, cor=azul, negrito=True, tamanho=8, alinhamento="left")
    for intervalo in ("B4", "G4", "B5", "B6"):
        aplicar_estilo(planilha[intervalo], fundo="FFFFFF", tamanho=8, alinhamento="left", borda=borda)
    for celula in ("A8", "C8", "E8", "G8"):
        aplicar_estilo(planilha[celula], fundo=azul, cor="FFFFFF", negrito=True, tamanho=7)
    for celula in ("A9", "C9", "E9", "G9"):
        aplicar_estilo(planilha[celula], fundo=verde_claro, cor=azul, negrito=True, tamanho=13)
    for coluna in range(1, 9):
        aplicar_estilo(planilha.cell(11, coluna), fundo=azul, cor="FFFFFF", negrito=True, tamanho=7, borda=borda)
    aplicar_estilo(planilha["A44"], fundo=azul, cor="FFFFFF", negrito=True, tamanho=8, alinhamento="left")
    for coluna in range(1, 9):
        aplicar_estilo(planilha.cell(45, coluna), fundo=azul_claro, cor=azul, negrito=True, tamanho=7, borda=borda)
    for assinatura, cargo in (("A54", "A55"), ("D54", "D55"), ("G54", "G55")):
        aplicar_estilo(planilha[assinatura], cor=azul, negrito=True, tamanho=8)
        aplicar_estilo(planilha[cargo], cor="65717D", negrito=True, tamanho=7)
    for colunas in ((1, 2), (4, 5), (7, 8)):
        for coluna in colunas:
            planilha.cell(53, coluna).border = Border(
                bottom=Side(style="thin", color=azul)
            )

    larguras = (18, 10, 10, 10, 10, 10, 10, 14)
    for indice, largura in enumerate(larguras, start=1):
        planilha.column_dimensions[chr(64 + indice)].width = largura
    alturas = {1: 30, 2: 20, 4: 21, 5: 21, 6: 36, 8: 22, 9: 30, 10: 8, 11: 24,
               43: 7, 44: 18, 45: 18, 52: 6, 53: 18, 54: 20, 55: 16}
    for linha, altura in alturas.items():
        planilha.row_dimensions[linha].height = altura
    for linha in range(12, 43):
        planilha.row_dimensions[linha].height = 13

    planilha.sheet_view.showGridLines = False
    planilha.print_area = "A1:H55"
    planilha.page_setup.orientation = "portrait"
    planilha.page_setup.paperSize = planilha.PAPERSIZE_A4
    planilha.page_setup.fitToWidth = 1
    planilha.page_setup.fitToHeight = 1
    planilha.print_options.horizontalCentered = True
    planilha.page_margins.left = 0.25
    planilha.page_margins.right = 0.25
    planilha.page_margins.top = 0.3
    planilha.page_margins.bottom = 0.3
    planilha.sheet_properties.pageSetUpPr.fitToPage = True


def criar_planilha(registros, jornadas, atestados, usuarios, inicio):
    workbook = Workbook()
    workbook.properties.creator = "Sistema de Ponto Eletrônico"
    workbook.properties.title = "Relatório mensal de frequência"
    primeira = workbook.active
    primeira.title = nome_aba_unico(usuarios[0][1], set())
    titulos_existentes = {primeira.title}
    batidas = agrupar_batidas(registros)
    estimativas = estimar_jornadas(jornadas, batidas, usuarios, inicio)
    configurar_folha(
        primeira, usuarios[0], estimativas, batidas.get(usuarios[0][0], {}),
        atestados.get(usuarios[0][0], {}), inicio,
    )

    for usuario in usuarios[1:]:
        planilha = workbook.create_sheet(nome_aba_unico(usuario[1], titulos_existentes))
        titulos_existentes.add(planilha.title)
        configurar_folha(
            planilha, usuario, estimativas, batidas.get(usuario[0], {}),
            atestados.get(usuario[0], {}), inicio,
        )

    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return arquivo


def criar_planilha_controle_acesso():
    garantir_estrutura_usuarios()
    with criar_conexao() as conexao:
        usuarios = conexao.execute(
            """
            SELECT nome_completo, ultimo_acesso
            FROM usuarios
            ORDER BY nome_completo
            """
        ).fetchall()

    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Controle de acesso"
    planilha.append(("Nome do usuário", "Último acesso", "Já acessou o sistema?"))

    cor_cabecalho = "31425E"
    preenchimento_cabecalho = PatternFill("solid", fgColor=cor_cabecalho)
    borda_linha = Border(bottom=Side(style="thin", color="DCE4E1"))
    for celula in planilha[1]:
        celula.fill = preenchimento_cabecalho
        celula.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        celula.alignment = Alignment(vertical="center")

    for nome, ultimo_acesso in usuarios:
        acessou = ultimo_acesso is not None
        if acessou:
            ultimo_acesso = ultimo_acesso.astimezone(FUSO_HORARIO).replace(tzinfo=None)
        else:
            ultimo_acesso = "Nunca acessou"
        planilha.append((nome, ultimo_acesso, "Sim" if acessou else "Não"))
        linha = planilha.max_row
        for celula in planilha[linha]:
            celula.border = borda_linha
            celula.alignment = Alignment(vertical="center")
        if acessou:
            planilha.cell(linha, 2).number_format = "dd/mm/yyyy hh:mm"

    planilha.column_dimensions["A"].width = 42
    planilha.column_dimensions["B"].width = 24
    planilha.column_dimensions["C"].width = 28
    planilha.row_dimensions[1].height = 25
    planilha.freeze_panes = "A2"
    planilha.auto_filter.ref = f"A1:C{planilha.max_row}"
    planilha.sheet_view.showGridLines = False
    planilha.print_title_rows = "1:1"
    planilha.page_setup.orientation = "landscape"
    planilha.page_setup.fitToWidth = 1
    planilha.page_setup.fitToHeight = 0
    planilha.sheet_properties.pageSetUpPr.fitToPage = True

    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return arquivo


def dados_formulario(formulario):
    hoje = datetime.now(FUSO_HORARIO).date()
    try:
        mes = int(formulario.get("mes", hoje.month))
        if mes not in range(1, 13):
            mes = hoje.month
    except (TypeError, ValueError):
        mes = hoje.month

    try:
        ano = int(formulario.get("ano", hoje.year))
        if ano not in range(2000, 2101):
            ano = hoje.year
    except (TypeError, ValueError):
        ano = hoje.year

    return {
        "mes": str(mes),
        "ano": str(ano),
        "escopos": formulario.getlist("escopo"),
    }


def filtrar_colaboradores(colaboradores, escopos):
    if escopos == ["todos"]:
        return colaboradores, "Todos os usuários"
    if not escopos or "todos" in escopos:
        return None, ""

    try:
        ids_selecionados = {int(valor.split(":", 1)[1]) for valor in escopos
                            if valor.startswith("usuario:")}
    except (IndexError, ValueError):
        return None, ""
    if not ids_selecionados or len(ids_selecionados) != len(escopos):
        return None, ""

    selecionados = [usuario for usuario in colaboradores if usuario[0] in ids_selecionados]
    if len(selecionados) != len(ids_selecionados):
        return None, ""
    nomes = ", ".join(usuario[1] for usuario in selecionados)
    return selecionados, nomes


@rota_planilha.route("/planilha", methods=["GET", "POST"])
@exigir_tipos_conta("Suporte", "Administração")
def exibir_planilha():
    campos = dados_formulario(request.form if request.method == "POST" else request.args)
    erro = None
    if request.method == "POST":
        inicio, fim, erro = obter_periodo(request.form)
        escopos = campos["escopos"]
        if not escopos:
            erro = "Selecione ao menos um usuário ou todos os usuários."
        if not erro:
            colaboradores = buscar_usuarios_exportacao()
            selecionados, _ = filtrar_colaboradores(colaboradores, escopos)
            if not selecionados:
                erro = "Nenhum usuário corresponde à seleção."
            else:
                ids_usuarios = [usuario[0] for usuario in selecionados]
                inicio_estimativa = inicio - timedelta(weeks=SEMANAS_PARA_ESTIMATIVA)
                registros = buscar_registros(inicio_estimativa, fim, ids_usuarios)
                jornadas = buscar_jornadas(ids_usuarios)
                atestados = buscar_atestados(inicio, fim, ids_usuarios)
                arquivo = criar_planilha(registros, jornadas, atestados, selecionados, inicio)
                nome_arquivo = f"frequencia_{inicio.year}_{inicio.month:02d}.xlsx"
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
        meses_abreviados=MESES_ABREVIADOS,
    )


@rota_planilha.get("/planilha/controle-acesso")
@exigir_tipos_conta("Suporte")
def baixar_controle_acesso():
    arquivo = criar_planilha_controle_acesso()
    return send_file(
        arquivo,
        as_attachment=True,
        download_name="controle_de_acesso.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
