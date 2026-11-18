import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def obter_variavel_obrigatoria(nome):
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise RuntimeError(f"A variável {nome} não foi configurada.")
    return valor


def criar_backup():
    configuracao = {
        "host": obter_variavel_obrigatoria("DB_HOST"),
        "port": obter_variavel_obrigatoria("DB_PORT"),
        "dbname": obter_variavel_obrigatoria("DB_NAME"),
        "user": obter_variavel_obrigatoria("DB_USER"),
        "password": obter_variavel_obrigatoria("DB_PASSWORD"),
    }
    senha_criptografia = obter_variavel_obrigatoria("BACKUP_PASSPHRASE")
    diretorio_saida = Path(os.getenv("BACKUP_OUTPUT_DIR", "backups")).resolve()
    diretorio_saida.mkdir(parents=True, exist_ok=True)

    horario = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    arquivo_final = diretorio_saida / f"ponto_eletronico_{horario}.dump.gpg"
    ambiente_pg_dump = os.environ.copy()
    ambiente_pg_dump.update(
        PGPASSWORD=configuracao["password"],
        PGSSLMODE="require",
    )

    with tempfile.TemporaryDirectory(prefix="ponto-backup-") as diretorio_temporario:
        arquivo_dump = Path(diretorio_temporario) / "banco.dump"
        comando_pg_dump = [
            "pg_dump",
            "--host", configuracao["host"],
            "--port", configuracao["port"],
            "--username", configuracao["user"],
            "--dbname", configuracao["dbname"],
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--schema=public",
            "--file", str(arquivo_dump),
        ]
        resultado_dump = subprocess.run(
            comando_pg_dump,
            env=ambiente_pg_dump,
            capture_output=True,
            text=True,
            check=False,
        )
        if resultado_dump.returncode:
            detalhe = resultado_dump.stderr.strip() or "pg_dump encerrou com erro."
            raise RuntimeError(f"Falha ao exportar o banco: {detalhe}")

        resultado_criptografia = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--quiet",
                "--pinentry-mode", "loopback",
                "--passphrase-fd", "0",
                "--symmetric",
                "--cipher-algo", "AES256",
                "--output", str(arquivo_final),
                str(arquivo_dump),
            ],
            input=f"{senha_criptografia}\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if resultado_criptografia.returncode:
            arquivo_final.unlink(missing_ok=True)
            detalhe = resultado_criptografia.stderr.strip() or "gpg encerrou com erro."
            raise RuntimeError(f"Falha ao criptografar o backup: {detalhe}")

    if not arquivo_final.is_file() or arquivo_final.stat().st_size == 0:
        arquivo_final.unlink(missing_ok=True)
        raise RuntimeError("O arquivo de backup criptografado está vazio.")

    print(f"Backup criptografado criado: {arquivo_final.name}")


if __name__ == "__main__":
    criar_backup()
