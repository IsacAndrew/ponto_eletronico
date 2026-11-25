# Sistema de Ponto Eletrônico

Aplicação web para registrar e consultar jornadas de trabalho, administrar contas e exportar folhas mensais de frequência. O sistema usa Flask no servidor, PostgreSQL para armazenar os dados e HTML/CSS/JavaScript no navegador.

## Visão geral da arquitetura

```text
Navegador (HTML, CSS e JavaScript)
        │ HTTP / JSON / formulários
        ▼
Flask (rotas, autenticação e regras de negócio)
        │ Psycopg 3 + pool de conexões TLS
        ▼
PostgreSQL
```

O navegador cuida da apresentação e de interações como solicitar a localização do aparelho. As decisões que precisam ser confiáveis autenticação, permissões, sequência das batidas e validação da localização são feitas novamente no servidor. O banco persiste as contas, jornadas, registros e configurações.

## Tecnologias

- **Python 3 e Flask**: aplicação web, rotas HTTP e templates Jinja.
- **PostgreSQL e Psycopg 3**: armazenamento relacional e acesso parametrizado ao banco.
- **HTML, CSS e JavaScript**: interface sem framework de frontend.
- **OpenPyXL**: criação de arquivos Excel para frequência.
- **QRCode**: geração do QR Code de registro presencial.
- **Gunicorn**: servidor usado no deploy.

As dependências estão fixadas em [`requirements.txt`](requirements.txt). A configuração do serviço Render fica em [`render.yaml`](render.yaml).

## Organização do código

| Caminho | Responsabilidade |
| --- | --- |
| `backend/app.py` | Cria a aplicação Flask, configura sessão e cabeçalhos, registra os módulos de rotas e oferece a verificação de saúde do banco. |
| `backend/login.py` | Login, limite de tentativas, troca obrigatória de senha e encerramento da sessão. |
| `backend/inicio.py` | Página inicial e fluxo de registro de ponto pelo site ou pelo QR Code. |
| `backend/ponto_qr.py` | Criação e validação do QR Code, autenticação presencial e vínculo de dispositivos. |
| `backend/permissoes.py` | Decorador que verifica sessão, conta ativa e perfil autorizado para cada rota. |
| `backend/banco_dados.py` | Inicializa e reutiliza o pool de conexões PostgreSQL. |
| `backend/estrutura_*.py`, `backend/jornada.py`, `backend/localizacao.py` | Preparação de estruturas auxiliares, regras de jornada e cálculos de localização. |
| `backend/usuarios.py`, `backend/configuracoes.py`, `backend/ponto_hoje.py` | Gestão de contas, configurações e consultas ao histórico. |
| `backend/planilha.py` | Busca dados, calcula informações auxiliares e gera planilhas Excel. |
| `backend/db.py`, `backend/backup_database.py` | Ferramentas administrativas do banco e rotina de backup. |
| `templates/` | Páginas HTML renderizadas no servidor com Jinja. |
| `scripts/` | JavaScript da interface; por exemplo, envio do ponto e leitura da geolocalização. |
| `static/css/` | Folhas de estilo. |
| `database/estrutura_banco.sql` | Estruturas, colunas, índices e restrições do PostgreSQL. |
| `modelos/xlsc_base.xlsx` | Modelo utilizado na geração de planilhas. |

Os módulos de rotas são registrados em `backend/app.py`. Um *blueprint* Flask agrupa as rotas de uma área, como login ou usuários.

## Como o login é validado

1. O formulário envia login e senha por `POST` para `/` (`backend/login.py`). O servidor consulta apenas contas com `ativo = TRUE`.
2. A senha armazenada é um hash gerado por `werkzeug.security.generate_password_hash`. O servidor compara a senha enviada com esse hash por `check_password_hash`; a senha original não é guardada no banco.
3. As tentativas são limitadas por login: após cinco falhas dentro da janela de cinco minutos, aquele login fica bloqueado por cinco minutos. A identificação usada na tabela de tentativas é um HMAC do login normalizado, e um *advisory lock* do PostgreSQL coordena tentativas simultâneas para a mesma chave. Para localizar a conta, a consulta usa o login enviado após remover espaços das pontas.
4. Se a validação funcionar, as tentativas são apagadas e o campo `ultimo_acesso` da conta é atualizado. O servidor limpa a sessão anterior e grava nela o identificador, nome e perfil do usuário.
5. Contas marcadas com `deve_trocar_senha` seguem para a troca obrigatória antes de usar as outras páginas.

A sessão do Flask fica em um cookie assinado com `FLASK_SECRET_KEY`, tem validade de sete dias e usa os atributos `HttpOnly` e `SameSite=Lax`. A assinatura permite ao servidor detectar alterações no cookie; não é um banco de sessões no servidor. `SESSION_COOKIE_SECURE=true` ativa o atributo `Secure`, indicado para HTTPS. Em cada rota protegida, `exigir_tipos_conta` consulta novamente a conta no banco: uma sessão não basta se a conta foi desativada ou se seu perfil não tem permissão para a operação. O modo de visualização é restrito à conta Suporte e não substitui o perfil real nas verificações.

## Como uma batida é registrada

### Pelo site

1. Em `scripts/inicio.js`, o navegador solicita a localização com a API de geolocalização. Para contas autorizadas a registrar fora da unidade, essa etapa é pulada.
2. O JavaScript envia `latitude`, `longitude` e `precisao` em JSON para `POST /registrar-ponto`.
3. `exigir_tipos_conta` confirma a sessão, que a conta continua ativa e que o perfil pode acessar a rota. A função `_registrar_ponto` (`backend/inicio.py`) bloqueia a linha da conta com `SELECT ... FOR UPDATE`; assim, duas requisições simultâneas do mesmo usuário são processadas em sequência.
4. Para contas sujeitas à validação de local, o servidor verifica formato e limites das coordenadas e compara a distância até o marco zero configurado. A distância é calculada pela fórmula de Haversine. A precisão informada pelo aparelho também é considerada: o servidor rejeita locais fora do raio e pede uma posição mais precisa quando não consegue confirmar que o aparelho está dentro dele.
5. O servidor determina a quantidade permitida para aquele dia da semana (0, 2 ou 4), consulta as batidas já feitas e valida a sequência. Em jornadas de duas batidas, a ordem é **Entrada → Saída**; em jornadas de quatro, é **Entrada → Intervalo → Retorno intervalo → Saída**. Não permite registrar em dia sem batidas configuradas, exceder o limite do dia ou registrar antes de completar cinco minutos desde a batida anterior.
6. Se as validações passarem, o servidor insere uma linha em `registros_ponto` com usuário, nome copiado para preservar o histórico, data local, tipo, instante (`TIMESTAMPTZ`) e origem `site`. Ao sair do contexto de conexão, a transação é confirmada; se ocorrer uma exceção antes disso, o PostgreSQL desfaz a transação.
7. A resposta JSON informa sucesso ou a mensagem de validação. Se houver uma jornada anterior incompleta ainda não verificada, a resposta também pode incluir um aviso; isso não cria nem corrige batidas antigas.

O índice único `(usuario_id, data_ponto, tipo_batida)` no banco é uma proteção adicional contra duplicar o mesmo tipo de batida no dia. O bloqueio da conta e as validações do servidor são importantes para manter a sequência quando há cliques ou requisições concorrentes.

### Pelo QR Code

O QR Code aponta para `/bater-ponto/<token>`. O servidor compara o token com o valor vigente usando comparação segura; gerar outro QR invalida o anterior. Se a pessoa ainda não estiver autenticada, o fluxo solicita login e depois retorna à tela presencial. No primeiro uso em um aparelho, o sistema cria um token aleatório para o dispositivo, guarda somente seu hash em `dispositivos_ponto` e entrega o token em cookie `HttpOnly`; o vínculo expira após um ano e é renovado no uso. A rota `POST /registrar-ponto-qr/<token>` valida novamente o token e usa as mesmas regras de sequência e intervalo mínimo do fluxo principal, mas não solicita geolocalização. A origem gravada é `qr`.

## Dados no PostgreSQL

As tabelas centrais descritas em [`database/estrutura_banco.sql`](database/estrutura_banco.sql) são:

| Tabela | Conteúdo |
| --- | --- |
| `usuarios` | Contas, hash de senha, perfil, estado ativo, preferências de jornada e último acesso. A tabela base de usuários já deve existir antes de aplicar esse arquivo. |
| `registros_ponto` | Uma linha por batida, com data, instante, tipo e origem. A referência ao usuário pode ficar nula para preservar registros históricos quando uma conta é excluída; o nome é copiado para a linha do registro. |
| `jornadas_usuarios` | Horários de jornada associados ao usuário e ao dia da semana. |
| `quantidades_batidas_semanais` | Quantidade de batidas (0, 2 ou 4) por usuário e dia da semana. |
| `configuracoes_sistema` | Marco zero, raio permitido e token vigente do QR Code. |
| `tentativas_login` | Contagem e janela de falhas de autenticação; armazena uma chave HMAC, não o login em texto claro. |
| `dispositivos_ponto` | Hashes dos tokens de aparelhos vinculados para o fluxo do QR Code. |
| `registros_ponto_verificados` | Marca os dias anteriores que já foram conferidos para aviso de batidas incompletas. |

O acesso passa por um pool Psycopg com uma a cinco conexões reutilizáveis, conexão TLS obrigatória (`sslmode=require`) e parâmetros SQL separados dos comandos. Os blocos `with criar_conexao()` devolvem a conexão ao pool e confirmam a transação quando terminam sem erro. O SQL parametrizado evita montar consultas com valores fornecidos diretamente pela pessoa usuária.

O projeto também possui funções `garantir_estrutura_*` que aplicam algumas colunas, índices e tabelas auxiliares de forma idempotente durante a execução. Isso não substitui uma estratégia de migração revisada: mudanças de schema precisam considerar os dados existentes e o banco já em produção.

## Rotas mais relevantes

| Método e caminho | Uso |
| --- | --- |
| `GET /` e `POST /` | Exibe o login e valida as credenciais. |
| `GET /inicio` | Carrega a tela de registro e a última batida do usuário. |
| `POST /registrar-ponto` | Registra batida pelo site, com validação de localização quando aplicável. |
| `GET /bater-ponto/<token>` | Valida o QR e abre o fluxo presencial. |
| `POST /registrar-ponto-qr/<token>` | Registra uma batida originada pelo QR. |
| `GET /historico-batidas` | Consulta batidas de um dia; acesso administrativo. |
| `POST /planilha` | Gera planilha mensal Excel para usuários selecionados. |
| `GET /health/database` | Executa `SELECT 1` e retorna o estado da conexão com o banco. |

## Execução local

É necessário Python compatível com as dependências e acesso a um PostgreSQL com a estrutura esperada. Configure as variáveis no arquivo `.env` usando [`.env.example`](.env.example) como referência. A aplicação exige `FLASK_SECRET_KEY` e as variáveis `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m backend.app
```

No Windows, ative o ambiente virtual com `.venv\Scripts\activate`. Para desenvolvimento local sem HTTPS, `SESSION_COOKIE_SECURE=false` pode ser usado; em produção HTTPS, use `true`.

No Render, o comando de inicialização configurado é:

```bash
gunicorn backend.app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT
```

## Planilhas e backups

A rota `/planilha` consulta registros reais e jornadas para o mês selecionado e monta um `.xlsx` com OpenPyXL. A planilha também pode estimar horários previstos a partir de registros anteriores, mas estimativas são cálculos de apoio e não viram novas linhas em `registros_ponto`.

O backup operacional está descrito em [`docs/BACKUP.md`](docs/BACKUP.md). A rotina `backend/backup_database.py` usa `pg_dump` para exportar o schema `public` e GPG para criptografar o arquivo. A capacidade de restaurar o arquivo deve ser verificada em um banco de teste.

## Perfis de acesso

- **Suporte**: ferramentas de suporte e administração, inclusive gestão do QR Code e área DB.
- **Administração**: usuários, planilhas, histórico e recursos administrativos liberados ao perfil.
- **Professor** e **Colaborador**: registro de ponto, configurações pessoais e páginas correspondentes.

As permissões são aplicadas no backend. Ocultar um item do menu melhora a interface, mas não concede nem substitui autorização para uma rota.

## Documentação adicional

- [`docs/README.md`](docs/README.md): contexto de uso e apresentação do projeto.
- [`docs/BACKUP.md`](docs/BACKUP.md): configuração e recuperação de backups.
- [`instrucoes.md`](instrucoes.md): contexto operacional e orientações para manutenção do sistema.
