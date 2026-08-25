# Подготовка production-хоста

Этот документ задаёт требования к ОС production-хоста ML Portal. Он намеренно
не привязан к конкретному пакетному менеджеру: для Astra Linux или ALT Linux
нужно использовать эквивалентные поддерживаемые поставщиком пакеты и настройки
защиты.

Хост запускает контейнеры, но не собирает образы приложения и не копирует
исходный код приложения в `/opt/ml-portal`. GitLab CI передаёт туда небольшой
неизменяемый пакет развёртывания из точного коммита релиза.

## Требования к платформе

- Поддерживаемая и обновляемая ОС с cgroup v2, `systemd`, Docker Engine,
  Docker Compose v2, GitLab Runner Shell executor, `sudo`, `flock`, `realpath`,
  GNU `install`/`stat`, корневыми сертификатами и синхронизацией времени NTP.
- Доступ DNS и firewall с хоста до внутреннего реестра контейнеров, GitLab,
  необходимых LLM/MCP endpoint и endpoint мониторинга.
- Постоянное хранилище с мониторингом свободного места для Docker-образов,
  Docker-томов, моделей и истории релизов. До первого production-релиза
  необходимо проверить процедуру резервного копирования и восстановления
  PostgreSQL, MinIO и Qdrant.
- Firewall хоста открывает только нужные внешние порты (обычно HTTP/HTTPS).
  PostgreSQL, Redis, Qdrant, MinIO console и Docker socket не должны быть
  доступны извне.

## Учётные записи и модель доступа

- `gitlab-runner` — учётная запись защищённого Shell Runner. Если это совместимо
  с установкой Runner, у неё должен быть неинтерактивный shell. Не добавляйте
  её в группы `docker`, `root` или группы с доступом к secrets.
- `ml-portal-deploy` — системная группа без возможности входа, владеющая не секретными
  файлами релизов. У неё нет доступа к Docker socket.
- Только `root` владеет Docker socket, данными доступа к Docker registry и
  production secrets. Участие в группе `docker` практически эквивалентно правам root,
  поэтому оно запрещено для Runner и операторов приложения.
- Администраторы используют отдельные именные SSH-учётные записи с MFA или
  одобренными ключами; удалённый вход root отключён. Доступ к защищённой GitLab
  ветке, окружению и production Runner ограничен release-операторами.

Создайте постоянные пути со следующими владельцами и правами:

| Путь | Владелец/права | Назначение |
| --- | --- | --- |
| `/opt/ml-portal` и `releases/` | `root:ml-portal-deploy`, `0750` | Неизменяемые пакеты развёртывания |
| `/var/lib/ml-portal` | `root:ml-portal-deploy`, `0750` | Блокировка и результат последнего развёртывания |
| `/etc/ml-portal/prod.env` | `root:root`, `0600` | Production secrets, никогда не Git/CI variables |
| `/etc/ml-portal/controller.env` | `root:root`, `0600` | Конфигурация контроллера развёртывания |
| `/etc/ml-portal/nginx`, `/etc/ml-portal/tls` | `root:root`, `0750` | Конфигурация, специфичная для окружения |
| `/srv/ml-portal/models_llm` | `root:root`, только чтение для контейнеров | Тяжёлые модели вне пакетов развёртывания |

Задайте `NGINX_CONF_DIR`, `SSL_CERT_DIR` и `MODELS_ROOT` в `prod.env`, чтобы
production compose не использовал резервные пути внутри checkout релиза.

## Установка контроллера развёртывания

Из защищённого production GitLab repository администратор хоста должен установить
[production-controller.sh](../../scripts/release/production-controller.sh) как
`/usr/local/sbin/ml-portal-deploy`, с владельцем `root:root` и правами `0750`.
Это осознанное и аудируемое изменение хоста: CI никогда не перезаписывает этот
файл.

Создайте `/etc/ml-portal/controller.env` с такими host-local значениями:

```bash
APP_ROOT=/opt/ml-portal
STATE_DIR=/var/lib/ml-portal
PROD_ENV_FILE=/etc/ml-portal/prod.env
CI_BUILDS_ROOT=/path/to/gitlab-runner/builds
DEPLOY_GROUP=ml-portal-deploy
```

`CI_BUILDS_ROOT` — это родительская директория checkout’ов GitLab Runner, а не
директория конкретного проекта. Например, если Runner размещает checkout’ы в
`/home/gitlab-runner/builds/<runner-token>/...`, укажите
`CI_BUILDS_ROOT=/home/gitlab-runner/builds`. Если у Runner задан собственный
`builds_dir`, возьмите это значение из его `config.toml`.

## Пути: где что настраивается

Пути production настраиваются **только на хосте**. Не добавляйте пути `/opt` в
`.gitlab-ci.yml` и не меняйте `scripts/release/deploy.sh` для обычной установки:
root-owned controller сам передаёт их скрипту релиза.

`/etc/ml-portal/controller.env` — единственный источник правды для путей
развёртывания:

```bash
# Версионируемые пакеты развёртывания и ссылки current/previous.
APP_ROOT=/opt/ml-portal

# Блокировка развёртывания и отчёт о последнем развёртывании.
STATE_DIR=/var/lib/ml-portal

# Root-only secrets для Docker Compose.
PROD_ENV_FILE=/etc/ml-portal/prod.env

# Родитель $CI_PROJECT_DIR checkout’ов из Runner config.toml.
CI_BUILDS_ROOT=/home/gitlab-runner/builds

DEPLOY_GROUP=ml-portal-deploy
```

При такой конфигурации controller размещает точный GitLab commit в:

```text
/opt/ml-portal/releases/<CI_COMMIT_SHA>
```

и атомарно управляет следующими ссылками:

```text
/opt/ml-portal/current   -> releases/<active-release>
/opt/ml-portal/previous  -> releases/<rollback-release>
```

Пути bind mounts, специфичные для окружения, задаются в `/etc/ml-portal/prod.env`, а
не в CI. Как минимум укажите пути, которые использует production compose:

```bash
MODELS_ROOT=/srv/ml-portal/models_llm
NGINX_CONF_DIR=/etc/ml-portal/nginx
SSL_CERT_DIR=/etc/ml-portal/tls
```

CI job не требует переменных с путями хоста. Она передаёт controller только
`$CI_PROJECT_DIR` и `$CI_COMMIT_SHA`. В production GitLab repository должны
находиться реальные `docker-compose.prod.yml`, `release.env` и `.gitlab-ci.yml`;
хост получает только итоговый пакет развёртывания, а не исходный код приложения.

Добавьте узкое `sudoers` правило для Runner, используя локальное имя его учётной
записи и точный путь controller:

```text
gitlab-runner ALL=(root) NOPASSWD: /usr/local/sbin/ml-portal-deploy deploy --source * --release *, /usr/local/sbin/ml-portal-deploy rollback, /usr/local/sbin/ml-portal-deploy status
```

Проверьте правило через `visudo`. Защищённые Runner, production branch и
production compose образуют привилегированную границу доверия: Docker Compose
configuration способна запрашивать Docker-возможности, эквивалентные root.

Данные доступа к private registry храните в root Docker configuration через
поддерживаемый Registry login/credential helper. Не передавайте registry
password или `prod.env` через GitLab variables.

## GitLab и первый запуск

1. Зарегистрируйте protected Shell Runner с тегом `production`; ограничьте его
   этим production project и protected branches.
2. Скопируйте `gitlab-ci.example.yml` и `docker-compose.prod.example.yml` в
   production GitLab repository как реальные `.gitlab-ci.yml` и
   `docker-compose.prod.yml`. Настраивайте host-specific mounts только там.
3. Защитите default branch и production environment; включите review и manual
   approval для изменений release manifest.
4. Один раз поднимите stateful services через контролируемую
   администратором maintenance-процедуру. До первого application deploy
   проверьте, что PostgreSQL, Redis, Qdrant и MinIO запущены и healthy.
5. Запустите manual production job. Она размещает точный commit как
   `/opt/ml-portal/releases/<CI_COMMIT_SHA>`, применяет forward migration,
   запускает только application services, выполняет health checks и обновляет
   `current` только при успехе.

Обычный release job никогда не вызывает `docker compose down`, не использует
`--remove-orphans` и не перезапускает stateful services. При application health
failure он возвращает предыдущий application bundle; database migrations всегда
forward-only и должны быть backward-compatible.

## Операции

Controller предоставляет только три privileged операции:

```text
ml-portal-deploy deploy --source <runner-checkout> --release <git-sha>
ml-portal-deploy rollback
ml-portal-deploy status
```

`status` безопасна для диагностики. `rollback` возвращает только предыдущие
application containers и сообщает текущую forward database revision. Храните
release directories до момента, разрешённого политикой backup/retention; не
удаляйте их из CI job.
