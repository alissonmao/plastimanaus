# ERP Plasti Manaus

ERP da fábrica Plasti Manaus em **Django 5.2 + PostgreSQL**. É uma cópia do projeto "ERP" feito no Lovable,
com as mesmas tabelas, IDs e regras de cálculo.

## Módulos

| Tela | Rota | Origem dos dados |
|---|---|---|
| Entradas e Saídas base Omie | `/fluxo-caixa/` | Planilha do Omie (importar) |
| Vendas base Plasti Manaus | `/vendas-plasti/` | Pedidos + metas por vendedor (admin) |
| Faturamento base Omie | `/vendas/` | Planilha com aba "Base de Dados" (importar) |
| Chão de Fábrica – Produção | `/` | Apontamentos |
| Apontamentos | `/apontamentos/` | Digitação ou planilha (aba "Input") |
| Relatórios | `/relatorios/` | Apontamentos agrupados por setor, máquina, turno… |
| Cadastros | `/cadastros/<nome>/` | Máquinas, famílias, setores, turnos, produtos, cores, tipos de sacola, medidas, clientes, OPs |

Regras portadas do Lovable (em `erp/calculos.py`):
- perdas = apara + alça + borra; kg/milheiro = lar × comp × esp ÷ 1000 (só Corte);
- horas trabalhadas = kg ÷ capacidade kg/h; utilização = horas trabalhadas ÷ horas do turno;
- R$/kg só para as linhas Sacola e Bobina;
- fluxo de caixa usa data de pagamento (ou emissão, se não pago) e ignora antes de 01/2026;
- meta diária = meta do mês ÷ dias úteis (sem fins de semana e feriados nacionais).

## Rodar localmente

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # ajuste DJANGO_DEBUG=1 e apague DATABASE_URL para usar SQLite
.venv/bin/python manage.py migrate
.venv/bin/python manage.py importar_supabase   # copia os dados do Lovable
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

## Servidor (Ubuntu/Debian, precisa de Python 3.10 ou mais novo)

Primeira instalação, como root:

```bash
git clone https://github.com/alissonmao/plastimanaus.git /opt/plastimanaus
bash /opt/plastimanaus/deploy/instalar.sh
```

O script instala PostgreSQL e Nginx, gera `.env` com senha e chave aleatórias e sobe o serviço
`plastimanaus` (gunicorn na porta 8001 atrás do Nginx). Para atualizar depois de um `git push`:

```bash
bash /opt/plastimanaus/deploy/atualizar.sh
```

Para colocar um domínio, coloque o nome em `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` no `.env`
e em `server_name` no Nginx. Depois ative o HTTPS (por exemplo com `certbot --nginx`) e remova `DJANGO_HTTPS=0`.
