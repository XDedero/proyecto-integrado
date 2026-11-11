"""Consulta RLS y permisos de la Data API en una transacción PostgreSQL de solo lectura."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Proyecto.settings")

import django

django.setup()

from django.db import connection, transaction


def main():
    if connection.vendor != "postgresql":
        raise SystemExit("Esta comprobación requiere PostgreSQL; no se modificó la base local.")
    tablas = ["auth_user", "auth_group", "auth_permission", "auth_user_groups", "auth_user_user_permissions", "auth_group_permissions", "django_admin_log", "django_content_type", "django_session", "django_migrations", "construApp_proyecto", "construApp_perfilusuario", "construApp_gastomaterial", "construApp_pagomanoobra", "construApp_hitocalendario"]
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT current_setting('transaction_read_only')")
        solo_lectura = cursor.fetchone()[0]
        cursor.execute("""
            SELECT c.relname, c.relrowsecurity, r.rolname,
                has_table_privilege(r.rolname, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
                has_any_column_privilege(r.rolname, c.oid, 'SELECT,INSERT,UPDATE,REFERENCES')
            FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
            CROSS JOIN pg_roles r
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
                AND r.rolname IN ('anon', 'authenticated')
            ORDER BY c.relname, r.rolname
        """, [tablas])
        resultados = [{"table": tabla, "rls": rls, "role": rol, "table_privileges": privilegios, "column_privileges": columnas} for tabla, rls, rol, privilegios, columnas in cursor.fetchall()]
    correcto = len(resultados) == len(tablas) * 2 and all(fila["rls"] and not fila["table_privileges"] and not fila["column_privileges"] for fila in resultados)
    print(json.dumps({"transaction_read_only": solo_lectura, "expected_tables": len(tablas), "passed": correcto, "results": resultados}, indent=2))
    if not correcto:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
