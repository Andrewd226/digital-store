# Создание структуры проекта c нуля

### Инициализировать uv в существующей директории (создаёт pyproject.toml, .python-version, .venv)
```bash
# On macOS and Linux.
curl -LsSf https://astral.sh/uv/install.sh | sh

uv self update
uv init --python 3.14
```

### Создать Django-проект (точка = в текущей директории)
```bash
uv run django-admin startproject digital_store .
```

### Форкнуть Oscar-приложения — копирует модели, миграции и структуру
```bash
uv run python manage.py oscar_fork_app catalogue .
uv run python manage.py oscar_fork_app partner .
```

### Создать собственные приложения (не форки Oscar)
```bash
uv run python manage.py startapp core
uv run python manage.py startapp suppliers
uv run python manage.py startapp currencies
```

### Создать директории
```bash
mkdir -p static staticfiles media templates
```

### Файл .env.example
```bash
ENV_FOR_DYNACONF=development.local

DB_HOST=localhost
DB_PORT=5432
DB_NAME=digital_store
DB_USER=usersvc_digital_store
DB_PASSWORD=

ALLOWED_HOSTS=['localhost', '127.0.0.1']

SALT_KEY=
SECRET_KEY=
```

### Файл .env
```bash
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(50))"  # → SECRET_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"  # → SALT_KEY
```

### Настройка PostgreSQL
```bash
sudo -u postgres psql
```

```SQL
CREATE USER usersvc_digital_store WITH PASSWORD '<securepassword>';
CREATE DATABASE digital_store OWNER usersvc_digital_store;
GRANT ALL PRIVILEGES ON DATABASE digital_store TO usersvc_digital_store;

CREATE USER test_usersvc_digital_store WITH PASSWORD 'test_password';
CREATE DATABASE test_digital_store OWNER test_usersvc_digital_store;
GRANT ALL PRIVILEGES ON DATABASE test_digital_store TO test_usersvc_digital_store;
```

# Клонирование репозитория
```bash
git clone https://github.com/Andrewd226/digital-store.git
cd digital-store
```

### Установка пакетов
```bash
uv sync --all-groups
```


# Первичные миграции
```bash
uv run python manage.py makemigrations core
uv run python manage.py makemigrations suppliers currencies
uv run python manage.py makemigrations catalogue
uv run python manage.py migrate
```

### Проверка
```bash
uv run python manage.py migrate --check
uv run python manage.py check
uv run python manage.py runserver
```


# Работа с Ruff

```bash
### Проверка кода (линтер)
uv run ruff check .

### Проверка с автоисправлением
uv run ruff check --fix .

### Форматирование кода
uv run ruff format .

### Проверка форматирования без изменений (для CI)
uv run ruff format --check .

### Проверить конкретный файл
uv run ruff check suppliers/models.py
```

# Тесты

```bash
### Первый запуск (создаст схему таблиц)
uv run pytest tests/ -v --create-db

### Последующие запуски (БД не пересоздаётся)
uv run pytest tests/ -v

### Проверка импортов без запуска тестов
uv run pytest tests/ --collect-only

### Запуск с подробным выводом ошибок
uv run pytest tests/ -v --tb=short

### Конкретный тест
uv run pytest tests/currencies/test_dao.py::TestExchangeRateDAOSaveRates::test_creates_new_rates -v
```

# Команды сервиса
```bash
uv run python manage.py createsuperuser

# Базовый запуск (с параметрами по умолчанию)
uv run python manage.py start

# С кастомными параметрами
uv run python manage.py start --bind 127.0.0.1:8000 --workers 4 --threads 2

# Проверка помощи
uv run python manage.py help start

# Создать/обновить начальные данные валют и источника курсов CoinCap
uv run python manage.py init_currencies

uv run python manage.py shell -c "from currencies.tasks import sync_all_currency_rates; sync_all_currency_rates()"
```

# Работа с БД PostgreSql
### Установка и запуск CloudBeaver
```bash
mkdir -p /opt/cloudbeaver/data
docker run -d --name cloudbeaver \
    -p 127.0.0.1:8978:8978 \
    -v /opt/cloudbeaver/data:/opt/cloudbeaver/workspace \
    --add-host=host.docker.internal:host-gateway \
    --restart unless-stopped \
    dbeaver/cloudbeaver:latest

ufw deny 8978  # Deny to CloudBeaver from internet
ufw allow from 172.17.0.0/16 to any port 5432 proto tcp # allow from Docker net to Postgresql
ufw allow from 172.17.0.0/16 to any port 6432 proto tcp # allow from Docker net to Pgbouncer
ufw reload

# Просмотр всех доступных контейнеров
docker ps -a

# Просмотр логов
docker logs -f cloudbeaver

# Остановка контейнера
docker stop cloudbeaver

# Запуск контейнера
docker start cloudbeaver

# Перезапуск контейнера
docker restart cloudbeaver

# Подключение к контейнеру
docker exec -it cloudbeaver bash

# Обновление до последней версии
docker pull dbeaver/cloudbeaver:latest
docker stop cloudbeaver
docker rm cloudbeaver
# (Запуск команды из пункта 1 заново)
```

### Подключение к БД
```bash
# На локальном компьютере выполнить:
ssh -L 8978:127.0.0.1:8978 user@your_server_ip

# Затем в браузере открыть:
http://localhost:8978
```
