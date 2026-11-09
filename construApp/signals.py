from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilUsuario


@receiver(post_save, sender=User)
def asegurar_perfil_usuario(sender, instance, created, raw=False, using="default", **kwargs):
    if raw:
        return
    PerfilUsuario.objects.using(using).get_or_create(
        usuario=instance,
        defaults={"rol": "ADMIN" if instance.is_superuser or instance.is_staff else "EMPLEADO"},
    )
