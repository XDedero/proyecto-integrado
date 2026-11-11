from django.contrib import admin
from django.urls import path
from construApp import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("admin/", admin.site.urls),

    # Rutas de Autenticación y Gestión de Roles (Admin, Visualizador, Empleado)
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("usuarios/", views.registro_usuario, name="registro_usuario"),
    path("usuarios/<int:pk>/", views.usuario_detalle, name="usuario_detalle"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/eliminar/", views.usuario_eliminar, name="usuario_eliminar"),

    # Página Independiente para los Empleados / Trabajadores de Obra
    path("mi-portal/", views.portal_empleado, name="portal_empleado"),

    # Rutas del Centro de Comando (Administrador y Visualizador)
    path("", views.inicio, name="inicio"),
    path("proyectos/", views.proyectos_view, name="proyectos"),
    path("proyectos/<int:pk>/", views.proyecto_detalle, name="proyecto_detalle"),
    path("proyectos/<int:pk>/editar/", views.proyecto_editar, name="proyecto_editar"),
    path("proyectos/<int:pk>/eliminar/", views.proyecto_eliminar, name="proyecto_eliminar"),
    path("finanzas/", views.finanzas_view, name="finanzas"),
    path("calendario/", views.calendario_view, name="calendario"),
]
