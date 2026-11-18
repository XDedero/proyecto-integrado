from django.contrib import admin
from .models import Cliente, Proyecto, PerfilUsuario, GastoMaterial, PagoManoObra, HitoCalendario
from .forms import ClienteForm, ProyectoForm


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    form = ClienteForm
    list_display = ("nombre", "rut", "telefono", "email")
    search_fields = ("nombre", "rut", "email")


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    form = ProyectoForm
    list_display = ("nombre", "cliente", "fecha_inicio", "fecha_termino_estimada", "activo")
    list_select_related = ("cliente",)
    search_fields = ("nombre", "cliente__nombre", "direccion")

admin.site.register(PerfilUsuario)
admin.site.register(GastoMaterial)
admin.site.register(PagoManoObra)
admin.site.register(HitoCalendario)
