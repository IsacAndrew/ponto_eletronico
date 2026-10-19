# Backup do banco

O workflow `.github/workflows/backup-database.yml` gera um dump diário do schema `public`, criptografa o arquivo com GPG e guarda o artefato no GitHub Actions por 90 dias. O agendamento é às 03:17 no horário de Brasília; também é possível iniciar uma execução manual pela aba **Actions** do repositório.

## Configuração necessária

No GitHub, abra **Settings → Secrets and variables → Actions → New repository secret** e cadastre:

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `BACKUP_PASSPHRASE`

Use nos cinco primeiros os mesmos valores do serviço no Render. Gere uma frase-senha longa, por exemplo com `openssl rand -base64 36`, salve-a em um gerenciador de senhas e cadastre-a como `BACKUP_PASSPHRASE`. Sem essa frase-senha, não será possível descriptografar os arquivos.

O workflow não deve ser considerado operacional até uma execução aparecer como concluída em **Actions** e o artefato ser baixado e testado em um banco de teste separado. Para descriptografar um artefato baixado, use GPG e informe a frase-senha. Para restaurar, use `pg_restore` em um banco de teste vazio antes de depender do arquivo para recuperação.

Os dumps são criptografados antes do envio. O banco original não é alterado pelo processo.
