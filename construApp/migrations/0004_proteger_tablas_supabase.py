from django.db import migrations


def proteger_tablas_django(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        roles_api = [fila[0] for fila in cursor.fetchall()]
        if not roles_api:
            return
        # Estas tablas usan sesiones de Django; no contienen identidades auth.uid().
        # El backend conserva sus privilegios; la Data API no accede a las cuentas.
        tablas_django = {
            "auth_user", "auth_group", "auth_permission", "auth_user_groups",
            "auth_user_user_permissions", "auth_group_permissions",
            "django_admin_log", "django_content_type", "django_session", "django_migrations",
            "construApp_proyecto", "construApp_perfilusuario", "construApp_gastomaterial",
            "construApp_pagomanoobra", "construApp_hitocalendario",
        }
        tablas = set(connection.introspection.table_names(cursor)) & tablas_django
        roles = ", ".join(["PUBLIC"] + [connection.ops.quote_name(rol) for rol in roles_api])
        for tabla in sorted(tablas):
            nombre = connection.ops.quote_name(tabla)
            cursor.execute(f"ALTER TABLE {nombre} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"REVOKE ALL PRIVILEGES ON TABLE {nombre} FROM {roles}")


class Migration(migrations.Migration):
    dependencies = [("construApp", "0003_completar_perfiles_usuarios")]
    # Intencionalmente irreversible: revertir código no debe reabrir datos privados.
    operations = [migrations.RunPython(proteger_tablas_django)]
