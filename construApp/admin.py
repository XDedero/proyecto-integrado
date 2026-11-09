from django.contrib import admin
from .models import Proyecto, PerfilUsuario, GastoMaterial, PagoManoObra, HitoCalendario

admin.site.register(Proyecto)
admin.site.register(PerfilUsuario)
admin.site.register(GastoMaterial)
admin.site.register(PagoManoObra)
admin.site.register(HitoCalendario)
