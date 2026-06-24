# api_django_reference

API REST em **Django 5.1 + Django REST Framework** com autenticação **JWT** (SimpleJWT)
e banco de dados **PostgreSQL**. O domínio de usuários vive em `apps/users`.

## Stack

- Django 5.1 / Django REST Framework
- djangorestframework-simplejwt (JWT)
- PostgreSQL (driver psycopg 3)
- python-decouple (config via `.env`)
- django-cors-headers
- **Integrações em Rust** (wheels nativas): `rust-py-audit`, `rust-py-rate-limit`,
  `rust-py-monitor`, `rust-py-scheduler`, `rust-py-cache` — ver
  [Integrações Rust](#integrações-rust)

## Estrutura

```
api_django_reference/
├── config/                 # projeto Django (settings, urls, wsgi, asgi)
│   ├── settings.py
│   ├── settings_test.py    # usa SQLite em memória para os testes
│   └── urls.py
├── apps/
│   ├── core/              # integrações Rust compartilhadas
│   │   ├── services.py    # singletons: cache, audit, rate limiters
│   │   ├── throttle.py    # ponte rate-limit -> DRF (HTTP 429)
│   │   ├── scheduler.py   # jobs recorrentes (cleanup, verify)
│   │   └── apps.py        # inicia o scheduler junto com o servidor
│   └── users/              # app de usuários
│       ├── models.py       # User customizado (login por email, UUID pk)
│       ├── managers.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── tokens.py       # tokens de confirmação de email e reset de senha
│       ├── emails.py
│       ├── admin.py
│       └── tests.py
├── manage.py
├── requirements.txt
└── .env.example
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # ajuste as credenciais do Postgres

# Crie o banco no PostgreSQL (exemplo)
createdb api_django_reference

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Testes

Rodam em SQLite em memória, sem precisar de Postgres:

```bash
python manage.py test apps.users --settings=config.settings_test
```

## Endpoints

Base: `/api/v1/users/`

| Método | Rota                  | Auth | Descrição                                       |
|--------|-----------------------|------|-------------------------------------------------|
| POST   | `register/`           | —    | Cria conta e envia email de confirmação         |
| POST   | `login/`              | —    | Autentica por email/senha, retorna JWT + user   |
| POST   | `login/refresh/`      | —    | Renova o access token a partir do refresh       |
| GET    | `me/`                 | JWT  | Dados do usuário autenticado                     |
| PATCH  | `me/`                 | JWT  | Atualiza dados do usuário autenticado            |
| POST   | `change-password/`    | JWT  | Troca a senha (exige a senha atual)             |
| POST   | `forgot-password/`    | —    | Envia link de reset (resposta sempre genérica)  |
| POST   | `reset-password/`     | —    | Conclui o reset usando `uid` + `token`          |
| POST   | `confirm-email/`      | —    | Confirma o email usando `uid` + `token`         |

### Exemplos

**Register**
```bash
curl -X POST http://localhost:8000/api/v1/users/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"john@example.com","first_name":"John","password":"Str0ng-Pass!23","password_confirm":"Str0ng-Pass!23"}'
```

**Login**
```bash
curl -X POST http://localhost:8000/api/v1/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"john@example.com","password":"Str0ng-Pass!23"}'
# => { "access": "...", "refresh": "...", "user": { ... } }
```

**Me** (use o access token)
```bash
curl http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**Change password**
```bash
curl -X POST http://localhost:8000/api/v1/users/change-password/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"Str0ng-Pass!23","new_password":"Nova-Senha!99","new_password_confirm":"Nova-Senha!99"}'
```

**Forgot password**
```bash
curl -X POST http://localhost:8000/api/v1/users/forgot-password/ \
  -H "Content-Type: application/json" \
  -d '{"email":"john@example.com"}'
```

**Reset password** (uid + token vêm no link do email)
```bash
curl -X POST http://localhost:8000/api/v1/users/reset-password/ \
  -H "Content-Type: application/json" \
  -d '{"uid":"<UID>","token":"<TOKEN>","new_password":"Nova!2024","new_password_confirm":"Nova!2024"}'
```

**Confirm email** (uid + token vêm no link do email)
```bash
curl -X POST http://localhost:8000/api/v1/users/confirm-email/ \
  -H "Content-Type: application/json" \
  -d '{"uid":"<UID>","token":"<TOKEN>"}'
```

## Integrações Rust

Cinco bibliotecas Python implementadas em Rust (alto desempenho, sem overhead de
serviços externos como Redis). Tudo fica centralizado em `apps/core` e é plugado no
ciclo de vida das views/projeto.

| Lib | Papel no projeto | Onde está |
|-----|------------------|-----------|
| `rust-py-monitor` | Métricas de latência/status por request + processo | Middleware global + rota `/metrics/` |
| `rust-py-rate-limit` | Proteção contra brute-force nos endpoints sensíveis | `apps/core/throttle.py`, aplicado em login/register/forgot |
| `rust-py-audit` | Log de auditoria encadeado por hash (à prova de adulteração) | `apps/core/services.py`, eventos em `apps/users/views.py` |
| `rust-py-cache` | Cache in-process do `GET /me` | `apps/core/services.py`, usado em `MeView` |
| `rust-py-scheduler` | Jobs recorrentes de manutenção | `apps/core/scheduler.py`, iniciado em `CoreConfig.ready()` |

Configuração relevante em `settings.py`: `RATE_LIMITS`, `USER_CACHE_TTL`,
`AUDIT_APP_NAME`, `AUDIT_FILE_PATH`, `SCHEDULER_AUTOSTART`.

### 1. rust-py-monitor — métricas Prometheus

O `MonitorMiddleware` mede toda requisição; a rota `/metrics/` expõe no formato
Prometheus (latências p50/p95/p99, total de requests/erros, CPU/memória do processo).

```bash
curl http://localhost:8000/metrics/
```

**Caso de uso:** apontar o Prometheus para `/metrics/` e montar dashboards de
latência/erro no Grafana, ou disparar alertas quando `p95_latency_ms` ou
`error_rate` passarem de um limite — sem instrumentar cada view na mão.

### 2. rust-py-rate-limit — limite por endpoint

Buckets de janela deslizante definidos em `settings.RATE_LIMITS` (limite por
`window_seconds`, por IP). Os endpoints sensíveis chamam `enforce()`, que levanta
`Throttled` do DRF (HTTP 429 + header `Retry-After`).

```python
# apps/users/views.py
from apps.core.throttle import client_ip, enforce

class LoginView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        enforce("login", client_ip(request))   # 429 se estourar o limite
        return super().post(request, *args, **kwargs)
```

Defaults: `login` 10/min, `register` e `forgot_password` 5/hora por IP.

**Caso de uso:** travar ataques de força-bruta de senha no `/login` e abuso do
`/forgot-password` (spam de email) sem precisar de Redis/nginx na frente.

### 3. rust-py-audit — trilha de auditoria encadeada

Cada evento de negócio é gravado num log append-only encadeado por SHA-256
(o hash de cada evento inclui o hash do anterior). Adulterar uma linha quebra a
cadeia, detectável via `audit.verify()`.

Eventos registrados: `USER_REGISTERED`, `USER_LOGIN`, `PROFILE_UPDATED`,
`PASSWORD_CHANGED`, `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET`, `EMAIL_CONFIRMED`.

```python
# apps/core/services.py
audit = AuditLogger(app_name="api_django_reference", file_path="./audit.jsonl")

# apps/users/views.py — ao trocar a senha
audit.log(actor_id=str(user.id), action="PASSWORD_CHANGED",
          resource="user", resource_id=str(user.id), metadata={"ip": ip})
```

```python
# Verificar a integridade da trilha
>>> from apps.core.services import audit
>>> audit.verify()
{'valid': True, 'total_events': 42, 'last_hash': '...'}
```

**Caso de uso:** conformidade/forense — provar "quem fez o quê e quando" de forma
auditável (LGPD/SOC2), com garantia criptográfica de que registros não foram
alterados. O job diário do scheduler revalida a cadeia automaticamente.

### 4. rust-py-cache — cache do `GET /me`

`MeView` serve `/me` a partir do cache (TTL `USER_CACHE_TTL`, 30s) e invalida a
entrada quando o usuário muda (`PATCH /me`, troca/reset de senha, confirmação de email).

```python
# apps/users/views.py
def retrieve(self, request, *args, **kwargs):
    key = user_cache_key(request.user.id)
    cached = cache.get(key)
    if cached is not None:
        return Response(cached)             # hit: não toca no banco
    data = self.get_serializer(request.user).data
    cache.set(key, data, ttl=settings.USER_CACHE_TTL)
    return Response(data)
```

Também há o decorator de memoização para funções puras/custosas:

```python
from apps.core.services import cache

@cache.cached(ttl=300, key=lambda user_id: f"perms:{user_id}")
def compute_permissions(user_id):
    ...
```

**Caso de uso:** o `/me` costuma ser chamado em quase toda navegação do frontend;
cachear por poucos segundos derruba a carga no Postgres mantendo os dados frescos.

### 5. rust-py-scheduler — jobs em background

Um `Scheduler` roda numa thread dedicada (Rust), iniciado em `CoreConfig.ready()`
quando o servidor sobe (`SCHEDULER_AUTOSTART=True`; desligado em testes e comandos
como `migrate`).

```python
# apps/core/scheduler.py
scheduler.every("10m", cleanup_expired, max_retries=2)   # limpa cache + rate-limit
scheduler.cron("0 3 * * *", verify_audit_chain)          # revalida a auditoria às 3h
```

**Caso de uso:** manutenção periódica sem Celery/cron externo — expurgar chaves
expiradas de cache/rate-limit e checar a integridade da trilha de auditoria todo dia.

> O scheduler **não** inicia durante a suíte de testes nem em comandos de gestão; o
> guard fica em `apps/core/apps.py` (evita também o duplo start do autoreload do
> `runserver`).

## Notas

- O envio de email usa o backend de **console** em desenvolvimento (os links de
  confirmação/reset aparecem no terminal do `runserver`). Configure SMTP em produção
  via `EMAIL_BACKEND` e variáveis relacionadas.
- `forgot-password` sempre responde da mesma forma, mesmo para emails inexistentes,
  para não vazar quais contas existem.
- Os tokens de confirmação de email e reset de senha são assinados e expiram, usando o
  framework de tokens do Django (sem armazenar tokens no banco).
