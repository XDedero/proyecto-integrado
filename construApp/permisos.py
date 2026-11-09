from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import PerfilUsuario, Proyecto


def obtener_rol_usuario(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return None
    if usuario.is_superuser:
        return "ADMIN"
    try:
        rol = usuario.perfil.rol
    except PerfilUsuario.DoesNotExist:
        # Compatibilidad con administradores creados antes de los perfiles.
        return "ADMIN" if usuario.is_staff else "EMPLEADO"
    return rol if rol in dict(PerfilUsuario.ROLES) else "EMPLEADO"


def proyectos_visibles(usuario):
    rol = obtener_rol_usuario(usuario)
    if rol in ("ADMIN", "VISUALIZADOR"):
        return Proyecto.objects.all()
    if rol == "EMPLEADO":
        return Proyecto.objects.filter(trabajadores_asignados__usuario=usuario)
    return Proyecto.objects.none()


def solo_administrador(vista):
    @login_required(login_url="login")
    @wraps(vista)
    def protegida(request, *args, **kwargs):
        if obtener_rol_usuario(request.user) != "ADMIN":
            raise PermissionDenied("Solo el administrador puede realizar esta acción.")
        return vista(request, *args, **kwargs)

    return protegida
