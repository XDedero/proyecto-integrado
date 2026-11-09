from django.contrib import admin
from django.urls import path
from construApp import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Rutas de Autenticación y Gestión de Roles (Admin, Visualizador, Empleado)
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("usuarios/", views.registro_usuario, name="registro_usuario"),

    # Página Independiente para los Empleados / Trabajadores de Obra
    path("mi-portal/", views.portal_empleado, name="portal_empleado"),

    # Rutas del Centro de Comando (Administrador y Visualizador)
    path("", views.inicio, name="inicio"),
    path("proyectos/", views.proyectos_view, name="proyectos"),
    path("finanzas/", views.finanzas_view, name="finanzas"),
    path("calendario/", views.calendario_view, name="calendario"),
]
