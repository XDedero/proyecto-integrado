from .permisos import obtener_rol_usuario


def permisos_usuario(request):
    rol = obtener_rol_usuario(request.user)
    return {"rol_usuario": rol, "es_admin": rol == "ADMIN"}
