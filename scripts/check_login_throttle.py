"""Prueba acotada de limitación de intentos, exclusivamente en SQLite temporal."""

import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "Proyecto.test_settings"

import django

django.setup()

from django.contrib.auth.models import User
from django.test import Client
from django.test.runner import DiscoverRunner


def main():
    runner = DiscoverRunner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    configuracion = runner.setup_databases()
    try:
        clave_prueba = secrets.token_urlsafe(32)
        clave_incorrecta = secrets.token_urlsafe(32)
        User.objects.create_user("auditoria_intentos", password=clave_prueba)
        cliente = Client(enforce_csrf_checks=True)
        cliente.get("/login/")
        token = cliente.cookies["csrftoken"].value
        codigos = [cliente.post("/login/", {"username": "auditoria_intentos", "password": clave_incorrecta, "csrfmiddlewaretoken": token}).status_code for _ in range(7)]
        correcta = cliente.post("/login/", {"username": "auditoria_intentos", "password": clave_prueba, "csrfmiddlewaretoken": token})
        print(json.dumps({"environment": "isolated_sqlite", "invalid_attempt_statuses": codigos, "correct_password_after_attempts": correcta.status_code, "throttle_observed": 429 in codigos or correcta.status_code == 429}, indent=2))
    finally:
        runner.teardown_databases(configuracion)
        runner.teardown_test_environment()


if __name__ == "__main__":
    main()
