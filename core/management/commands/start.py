"""
core/management/commands/start.py

Django management command для запуска production Gunicorn сервера.
"""

import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Запуск production Gunicorn сервера"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bind",
            type=str,
            default="127.0.0.1:8000",
            help="Адрес и порт для прослушивания (по умолчанию: 127.0.0.1:8000)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Количество workers (по умолчанию: 4)",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=2,
            help="Количество потоков на worker (по умолчанию: 2)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Таймаут запроса в секундах (по умолчанию: 30)",
        )

    def handle(self, *args, **options):
        bind = options["bind"]
        workers = options["workers"]
        threads = options["threads"]
        timeout = options["timeout"]

        cmd = [
            "gunicorn",
            "digital_store.wsgi:application",
            "--bind",
            bind,
            "--workers",
            str(workers),
            "--threads",
            str(threads),
            "--timeout",
            str(timeout),
            "--graceful-timeout",
            "30",
            "--max-requests",
            "1000",
            "--max-requests-jitter",
            "100",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ]

        self.stdout.write(
            self.style.SUCCESS(f"🚀 Запуск Gunicorn на {bind} с {workers} workers...")
        )

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"❌ Ошибка запуска Gunicorn: {e}"))
            sys.exit(1)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⚠️  Остановка сервера..."))
