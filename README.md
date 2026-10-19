# Sistema de Ponto Eletrônico

Este sistema foi criado para atender a uma necessidade real do meu trabalho: organizar o registro de ponto e as rotinas relacionadas aos usuários. Ele está em produção e é utilizado por pessoas reais, então parte importante do projeto acontece depois da implementação: acompanhar o uso, entender solicitações, priorizar ajustes e lidar com problemas que aparecem no dia a dia.

## O que o sistema oferece

- Registro de ponto pela aplicação, incluindo opções por localização e QR Code.
- Contas com diferentes perfis de acesso para suporte, administração, professores e colaboradores.
- Gestão de usuários, jornadas de trabalho e registros de ponto.
- Consulta dos registros do dia e geração de planilhas de frequência.
- Chat de suporte para comunicação entre usuários e equipe responsável.
- Páginas de configurações e acompanhamento do banco de dados.

## Minha atuação e uso de IA

O código-fonte do sistema foi desenvolvido com auxílio de inteligência artificial. Não apresento a implementação como código escrito inteiramente por mim. Minha responsabilidade no projeto está em identificar o problema, definir a direção e a organização do sistema, escolher as tecnologias, acompanhar a operação em produção, organizar múltiplas solicitações e conduzir a investigação e correção de bugs com apoio de IA.

Essa experiência me permite aprender como é acompanhar um sistema em uso, conversar com pessoas usuárias e transformar problemas reais em melhorias. Como próximo passo, quero aprofundar meus estudos sobre o código e sobre o PostgreSQL usado pelo sistema, especialmente para melhorar meu entendimento e a organização do banco de dados.

## Tecnologias

- Python e Flask no backend.
- PostgreSQL para persistência dos dados.
- HTML, CSS e JavaScript na interface.
- Psycopg para acesso ao PostgreSQL.
- OpenPyXL para trabalhar com planilhas Excel.
- QRCode para gerar códigos de acesso ao registro de ponto.
- Gunicorn para servir a aplicação em produção.

## Executar localmente

Para iniciar uma instância local, você precisa de Python 3, `pip` e uma base PostgreSQL preparada para o sistema.

```bash
git clone https://github.com/IsacAndrew/ponto_eletronico.git
cd ponto_eletronico
python -m venv .venv
```

Ative o ambiente virtual e instale as dependências:

```bash
# Windows
.venv\Scripts\activate

# Linux ou macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Crie um arquivo `.env` a partir do exemplo e configure a conexão com o PostgreSQL e a chave secreta do Flask:

```bash
# Linux ou macOS
cp .env.example .env
```

No Windows, copie `.env.example` para `.env` manualmente ou use:

```powershell
Copy-Item .env.example .env
```

Preencha no `.env` as variáveis `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` e `FLASK_SECRET_KEY`. A base PostgreSQL também precisa ter a estrutura inicial e uma conta de acesso configuradas. O arquivo `backend/estrutura_banco.sql` contém ajustes de estrutura do sistema, mas não representa sozinho a criação completa de uma base vazia.

Inicie a aplicação localmente:

```bash
python -m backend.app
```

Acesse `http://127.0.0.1:5000` no navegador. O endpoint `/health/database` informa se a aplicação consegue se conectar ao banco.

## Estado do projeto

O sistema está em produção e segue em evolução a partir das necessidades observadas no uso real. A gestão, a organização das demandas e a condução das melhorias fazem parte do meu aprendizado em desenvolvimento e operação de software.
