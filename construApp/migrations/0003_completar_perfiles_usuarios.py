from django.conf import settings
from django.db import migrations


def completar_perfiles(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    Usuario = apps.get_model(app_label, model_name)
    Perfil = apps.get_model("construApp", "PerfilUsuario")
    alias = schema_editor.connection.alias
    for usuario in Usuario.objects.using(alias).filter(perfil__isnull=True).iterator():
        Perfil.objects.using(alias).get_or_create(
            usuario_id=usuario.pk,
            defaults={"rol": "ADMIN" if usuario.is_superuser or usuario.is_staff else "EMPLEADO"},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("construApp", "0002_alter_gastomaterial_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(completar_perfiles, migrations.RunPython.noop)]
