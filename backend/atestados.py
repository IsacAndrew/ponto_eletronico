from datetime import date, time
from io import BytesIO
from threading import Lock
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, make_response, redirect, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from .banco_dados import criar_conexao
from .permissoes import exigir_tipos_conta, renderizar_pagina

rota_atestados = Blueprint("atestados", __name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
TAMANHO_MAXIMO_ANEXO = 5 * 1024 * 1024
TIPOS_ARQUIVO = {
    ".pdf": ("application/pdf", lambda dados: dados.startswith(b"%PDF-")),
    ".jpg": ("image/jpeg", lambda dados: dados.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda dados: dados.startswith(b"\xff\xd8\xff")),
    ".png": ("image/png", lambda dados: dados.startswith(b"\x89PNG\r\n\x1a\n")),
    ".webp": ("image/webp", lambda dados: dados.startswith(b"RIFF") and dados[8:12] == b"WEBP"),
}
_estrutura_pronta = False
_trava_estrutura = Lock()


def garantir_estrutura_atestados():
    global _estrutura_pronta
    if _estrutura_pronta:
        return
    with _trava_estrutura:
        if _estrutura_pronta:
            return
        with criar_conexao() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS atestados (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
                    usuario_nome TEXT NOT NULL,
                    data_atestado DATE NOT NULL,
                    dia_inteiro BOOLEAN NOT NULL,
                    hora_inicio TIME,
                    hora_fim TIME,
                    anexo_nome TEXT NOT NULL,
                    anexo_mime TEXT NOT NULL,
                    anexo BYTEA NOT NULL,
                    enviado_por BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
                    enviado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (
                        (dia_inteiro AND hora_inicio IS NULL AND hora_fim IS NULL)
                        OR
                        (NOT dia_inteiro AND hora_inicio IS NOT NULL
                         AND hora_fim IS NOT NULL AND hora_fim > hora_inicio)
                    ),
                    CHECK (octet_length(anexo) BETWEEN 1 AND 5242880)
                )
                """
            )
            conexao.execute(
                """CREATE INDEX IF NOT EXISTS atestados_usuario_data_idx
                   ON atestados (usuario_id, data_atestado)"""
            )
            conexao.execute("ALTER TABLE atestados ENABLE ROW LEVEL SECURITY")
            conexao.execute(
                """DO $$
                   BEGIN
                       IF NOT EXISTS (
                           SELECT 1 FROM pg_policies
                           WHERE schemaname = 'public'
                             AND tablename = 'atestados'
                             AND policyname = 'atestados_bloqueio_api'
                       ) THEN
                           CREATE POLICY atestados_bloqueio_api ON atestados
                           USING (FALSE) WITH CHECK (FALSE);
                       END IF;
                   END $$;"""
            )
        _estrutura_pronta = True


def listar_usuarios():
    with criar_conexao() as conexao:
        return conexao.execute(
            "SELECT id, nome_completo FROM usuarios ORDER BY nome_completo"
        ).fetchall()


def listar_atestados():
    with criar_conexao() as conexao:
        return conexao.execute(
            """SELECT atestado.id, atestado.usuario_nome, atestado.data_atestado,
                      atestado.dia_inteiro, atestado.hora_inicio, atestado.hora_fim,
                      atestado.anexo_nome, usuario.nome_completo
               FROM atestados AS atestado
               LEFT JOIN usuarios AS usuario ON usuario.id = atestado.enviado_por
               ORDER BY atestado.data_atestado DESC, atestado.id DESC
               LIMIT 300"""
        ).fetchall()


def destino(resultado):
    return redirect(url_for("atestados.exibir_atestados", resultado=resultado))


@rota_atestados.get("/atestados")
@exigir_tipos_conta("Suporte", "Administração")
def exibir_atestados():
    garantir_estrutura_atestados()
    resposta = make_response(
        renderizar_pagina(
            "atestados.html",
            "configuracoes",
            usuarios_atestados=listar_usuarios(),
            atestados=listar_atestados(),
            resultado_atestado=request.args.get("resultado"),
        )
    )
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@rota_atestados.post("/atestados/anexar")
@exigir_tipos_conta("Suporte", "Administração")
def anexar_atestado():
    garantir_estrutura_atestados()
    try:
        usuario_id = int(request.form.get("usuario_id", ""))
        data_atestado = date.fromisoformat(request.form.get("data_atestado", ""))
    except (TypeError, ValueError):
        return destino("dados_invalidos")

    cobertura = request.form.get("cobertura")
    dia_inteiro = cobertura == "dia_inteiro"
    if cobertura not in {"dia_inteiro", "horas"}:
        return destino("dados_invalidos")
    hora_inicio = hora_fim = None
    if not dia_inteiro:
        try:
            hora_inicio = time.fromisoformat(request.form.get("hora_inicio", ""))
            hora_fim = time.fromisoformat(request.form.get("hora_fim", ""))
        except (TypeError, ValueError):
            return destino("horas_invalidas")
        if hora_fim <= hora_inicio:
            return destino("horas_invalidas")

    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return destino("arquivo_ausente")
    if request.content_length and request.content_length > TAMANHO_MAXIMO_ANEXO + 262_144:
        return destino("arquivo_grande")
    nome_original = secure_filename(arquivo.filename)
    extensao = "." + nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
    tipo_arquivo = TIPOS_ARQUIVO.get(extensao)
    if not tipo_arquivo:
        return destino("tipo_arquivo")
    conteudo = arquivo.stream.read(TAMANHO_MAXIMO_ANEXO + 1)
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO:
        return destino("arquivo_grande")
    mime, validar_conteudo = tipo_arquivo
    if not validar_conteudo(conteudo):
        return destino("arquivo_invalido")

    with criar_conexao() as conexao:
        usuario = conexao.execute(
            "SELECT nome_completo FROM usuarios WHERE id = %s",
            (usuario_id,),
        ).fetchone()
        if not usuario:
            return destino("usuario_invalido")

        conexao.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"atestado:{usuario_id}:{data_atestado.isoformat()}",),
        )

        if dia_inteiro:
            conflito = conexao.execute(
                "SELECT 1 FROM atestados WHERE usuario_id = %s AND data_atestado = %s LIMIT 1",
                (usuario_id, data_atestado),
            ).fetchone()
        else:
            conflito = conexao.execute(
                """SELECT 1 FROM atestados
                   WHERE usuario_id = %s AND data_atestado = %s
                     AND (dia_inteiro OR (hora_inicio < %s AND hora_fim > %s))
                   LIMIT 1""",
                (usuario_id, data_atestado, hora_fim, hora_inicio),
            ).fetchone()
        if conflito:
            return destino("cobertura_conflitante")

        conexao.execute(
            """INSERT INTO atestados (
                   usuario_id, usuario_nome, data_atestado, dia_inteiro,
                   hora_inicio, hora_fim, anexo_nome, anexo_mime, anexo, enviado_por
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                usuario_id,
                usuario[0],
                data_atestado,
                dia_inteiro,
                hora_inicio,
                hora_fim,
                nome_original[:255],
                mime,
                conteudo,
                session.get("usuario_id"),
            ),
        )
    return destino("salvo")


@rota_atestados.get("/atestados/<int:atestado_id>/arquivo")
@exigir_tipos_conta("Suporte", "Administração")
def baixar_anexo(atestado_id):
    garantir_estrutura_atestados()
    with criar_conexao() as conexao:
        atestado = conexao.execute(
            "SELECT anexo, anexo_mime, anexo_nome FROM atestados WHERE id = %s",
            (atestado_id,),
        ).fetchone()
    if not atestado:
        abort(404)
    resposta = send_file(
        BytesIO(atestado[0]),
        mimetype=atestado[1],
        as_attachment=True,
        download_name=atestado[2],
    )
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@rota_atestados.post("/atestados/<int:atestado_id>/excluir")
@exigir_tipos_conta("Suporte", "Administração")
def excluir_atestado(atestado_id):
    garantir_estrutura_atestados()
    with criar_conexao() as conexao:
        conexao.execute("DELETE FROM atestados WHERE id = %s", (atestado_id,))
    return destino("excluido")
