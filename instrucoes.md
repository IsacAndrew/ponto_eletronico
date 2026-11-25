# Instruções para IAs — Ponto Eletrônico

Este documento apresenta o contexto do projeto para qualquer pessoa ou IA que vá analisar ou alterar o sistema. Ele complementa o `README.md`; o código atual e o banco de produção são a fonte de verdade quando houver divergência.

## 1. Contexto e objetivo

Aplicação web de ponto eletrônico de uma escola. O sistema está em produção e possui usuários e registros reais. Faça mudanças com cuidado para preservar os dados e o funcionamento diário.

O projeto prioriza código direto, organizado e fácil de manter. A interface e as mensagens são em português brasileiro. O sistema deve funcionar em computador e celular, usar datas no padrão brasileiro (`DD/MM/AAAA`) e considerar o fuso `America/Sao_Paulo`.

## 2. Tecnologias e organização

- Python com Flask e templates Jinja.
- PostgreSQL acessado com Psycopg 3 e pool de conexões.
- HTML, CSS e JavaScript sem framework de frontend.
- OpenPyXL para arquivos Excel; `qrcode` para o QR Code; Gunicorn em produção.
- `requirements.txt` registra as dependências.

Estrutura principal:

- `backend/`: aplicação Flask, rotas, regras de negócio, acesso e estrutura do banco.
- `templates/`: páginas HTML/Jinja.
- `static/css/` e `static/js/`: estilos e scripts da interface.
- `backend/modelos/`: modelos usados na geração de planilhas.
- `scripts/`: tarefas operacionais, como backup.
- `README.md`: apresentação do projeto.

As rotas são divididas em módulos dentro de `backend/` e registradas em `backend/app.py`. Antes de criar outro módulo, procure se a funcionalidade já tem um local apropriado. Evite duplicar regras, adicionar dependências sem necessidade ou deixar arquivos, funções e estilos sem uso.

## 3. Execução e configuração

Na raiz do projeto, com dependências instaladas e `.env` configurado, a execução local é:

```bash
python -m backend.app
```

O deploy atual no Render usa:

```text
Build: pip install -r requirements.txt
Start: gunicorn backend.app:app --bind 0.0.0.0:$PORT
```

As variáveis de ambiente necessárias estão documentadas em `.env.example`. Entre elas estão `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` e `FLASK_SECRET_KEY`; há também configurações opcionais para cookies, limite de armazenamento e backup. A aplicação exige `FLASK_SECRET_KEY` para iniciar.

**Nunca leia em voz alta, copie para documentação, registre em logs ou envie ao Git valores de `.env`, senhas, tokens, strings de conexão ou segredos de backup.** Use `.env.example` apenas como referência de nomes e formato, mantendo valores secretos vazios.

## 4. Perfis de acesso

Os nomes são definidos em `backend/permissoes.py`:

- **Suporte**: conta especial do responsável pelo sistema; tem os recursos administrativos e as funções exclusivas de suporte, como DB, QR Code e gestão de registros.
- **Administração**: gerencia usuários e recursos administrativos liberados para esse perfil.
- **Professor** e **Colaborador**: usam o fluxo de ponto, configurações pessoais e as opções correspondentes no menu.

As permissões devem ser verificadas no backend, usando os decoradores existentes. Esconder um botão na interface não substitui uma verificação de acesso na rota. O modo de visualização de outro perfil é um recurso de suporte e não deve conceder poderes adicionais a uma conta comum.

## 5. Regras funcionais atuais

### Registro de ponto

- Os tipos de batida são Entrada, Intervalo, Retorno intervalo e Saída.
- A jornada semanal permite **0, 2 ou 4 batidas** por dia da semana. Em jornadas de duas batidas, a primeira é Entrada e a segunda é Saída. Em jornadas de quatro, são usadas as quatro posições acima. Não há jornada de três batidas.
- O backend controla a sequência, impede mais de quatro batidas no dia e exige pelo menos cinco minutos entre batidas. Preserve as proteções transacionais e contra concorrência ao alterar esse fluxo.
- A preferência semanal pode ser ajustada pelo próprio usuário no fluxo de confirmação de uma batida adicional. Deve continuar compartilhando a mesma estrutura de jornada usada pelas telas administrativas.
- Há registro da origem da batida (`site` ou `qr`). O fluxo do QR Code não pede geolocalização; o fluxo pelo site aplica a validação do marco zero, exceto para usuário autorizado a registrar fora da unidade.
- Se houver uma batida incompleta no dia anterior, o sistema pode alertar no próximo registro. Não altere nem invente batidas históricas para completar jornadas.

### QR Code

- A geração e a renovação do QR Code são restritas ao Suporte.
- O QR leva a uma rota própria de ponto presencial. O usuário pode autenticar-se no primeiro acesso e vincular o dispositivo; acessos seguintes podem usar o vínculo salvo no cookie e no banco.
- Preserve validação do token, expiração e possibilidade de revogar vínculos. Não trate o endereço do QR como substituto da autenticação de uma conta.

### Usuários e histórico

- Os dados de usuário incluem nome completo, login, e-mail de recuperação, telefone, tipo de conta e campos adicionais como RG, função e jornada.
- O telefone e o RG são formatados pela aplicação. Valide dados no backend, mesmo quando já houver validação visual no navegador.
- A exclusão de um acesso não deve apagar registros de ponto históricos; as relações e rotinas do banco definem como preservar a identificação histórica.
- A tela **Histórico** mostra o dia atual por padrão e permite escolher um único dia para consultar outras batidas. Datas visíveis devem seguir o padrão brasileiro.

### Planilha mensal

- A exportação atual é mensal, com seleção de mês e ano, e pode gerar folhas individuais por usuário.
- Ela inclui dados cadastrais (como nome, RG e função), batidas efetivamente registradas, ausências/pendências, estimativas de carga horária e abonos aplicáveis, além dos espaços de assinatura da Direção, Coordenação e Funcionário.
- As batidas originais não devem ser alteradas por cálculos ou estimativas. Horários habituais estimados são referência de carga prevista; não são novos registros de ponto.
- Mantenha a impressão em A4 e revise a planilha em um leitor de Excel/LibreOffice quando alterações afetarem layout, fórmulas ou impressão.

### Atestados

- A funcionalidade fica em Configurações e é acessível a Administração e Suporte.
- Aceita PDF e imagens JPEG, PNG ou WebP, com limite de 5 MB por anexo. O arquivo é armazenado como `BYTEA` na tabela `atestados`.
- A administração associa o documento a uma pessoa e a uma data, cobrindo o dia todo ou um intervalo de horas. Coberturas conflitantes para a mesma pessoa/data são rejeitadas.
- Abono altera o cálculo de horas previstas, não as batidas reais. A planilha mensal deve refletir essa cobertura.
- O acesso aos arquivos passa por uma rota autenticada. A tabela habilita RLS com política de bloqueio para acesso direto pela API; o backend conecta ao PostgreSQL com suas próprias credenciais.
- Anexos ocupam espaço do banco. Considere isso ao avaliar crescimento e backups; não exponha documentos em URLs públicas ou logs.

### Banco

- A área DB e operações de limpeza total são altamente destrutivas. Não execute limpeza, exclusão de tabelas, reset de produção ou alteração de dados reais sem pedido explícito e inequívoco do responsável.
- O script `scripts/backup_database.py` cria um dump do schema `public` com `pg_dump` e o criptografa com GPG. Ele depende das variáveis `DB_*`, `BACKUP_PASSPHRASE` e, opcionalmente, `BACKUP_OUTPUT_DIR`. Um backup só é confiável depois de verificar que foi gerado e que pode ser restaurado; proteja a senha de criptografia separadamente.

## 6. Banco de dados e alterações de schema

O banco PostgreSQL/Supabase contém dados de produção. As estruturas são mantidas nos módulos de `backend/estrutura_*.py` e em `backend/estrutura_banco.sql`; alguns módulos garantem alterações de forma automática durante a execução.

Antes de mudar schema:

1. Inspecione a estrutura atual e os caminhos que leem/escrevem as tabelas.
2. Preserve dados existentes e torne a mudança compatível com instalações que já possuem registros.
3. Prefira operações idempotentes e restrições (`CHECK`, `UNIQUE`, chaves estrangeiras) quando couberem.
4. Considere concorrência e transações para registros de ponto e ações simultâneas.
5. Não presuma que ativar RLS afeta conexões diretas do backend da mesma forma que a chave pública usada pelo cliente Supabase.
6. Não execute migração ou operação destrutiva em produção sem autorização expressa e plano de recuperação.

## 7. Orientações para futuras alterações

- Leia os arquivos envolvidos e o fluxo completo antes de editar; confirme o comportamento no código atual em vez de confiar em decisões antigas da conversa.
- Preserve a simplicidade do projeto e a organização por funcionalidade. Não introduza frameworks ou abstrações grandes para mudanças pequenas.
- Faça a validação e autorização no servidor; trate entradas inválidas e falhas de banco sem revelar detalhes internos à pessoa usuária.
- Mantenha layout responsivo para celular e desktop, sem rolagem horizontal acidental e com rolagem vertical funcional quando o conteúdo precisar.
- Use datas brasileiras na interface e converta timestamps considerando `America/Sao_Paulo`.
- Não mude regras de ponto, permissões, jornada, geolocalização, dados reais ou conteúdo dos anexos fora do escopo pedido.
- Ao terminar, revise alterações e referências sem uso. Preserve mudanças locais já existentes: confira `git status` antes de editar ou preparar arquivos e não descarte alterações alheias à tarefa.
- Não faça `git push`, deploy, exclusão de dados ou backup que exponha informação sem que a ação esteja solicitada. Nunca declare que algo foi publicado sem confirmação do comando/serviço.
- Rode apenas verificações apropriadas ao escopo e informe claramente o que foi ou não verificado.
- Se o comportamento do sistema mudar, atualize esta documentação para ela continuar fiel ao código.

## 8. Limites deste documento

Este arquivo resume o contexto e as regras observadas no código, mas não substitui inspeção dos módulos, templates, SQL e configuração do ambiente. Discussões sobre funcionalidades futuras não significam que elas estejam implementadas. Confirme cada recurso no código antes de alterá-lo ou descrevê-lo como existente.
