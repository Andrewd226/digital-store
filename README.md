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
SECRET_KEY=
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=digital_store
DB_USER=usersvc_digital_store
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

SALT_KEY=
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

# запуск сервиса
```bash
# Базовый запуск (с параметрами по умолчанию)
uv run python manage.py start

# С кастомными параметрами
uv run python manage.py start --bind 127.0.0.1:8000 --workers 4 --threads 2

# Проверка помощи
uv run python manage.py help start
```