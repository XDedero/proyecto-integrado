from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_http_methods, require_POST
from .forms import ProyectoForm, UsuarioForm
from .models import Proyecto, GastoMaterial, PagoManoObra, HitoCalendario
from .permisos import obtener_rol_usuario, proyectos_visibles, solo_administrador


# ==============================================================================
# 1. AUTENTICACIÓN Y REDIRECCIÓN INTELIGENTE SEGÚN ROL (ADMIN / VIS / EMPLEADO)
# ==============================================================================

def iniciar_sesion(request):
    """Valida credenciales y redirige al Panel o a la página aparte del Empleado (HU-01)."""
    if request.user.is_authenticated:
        if obtener_rol_usuario(request.user) == "EMPLEADO":
            return redirect("portal_empleado")
        return redirect("inicio")

    if request.method == "POST":
        usuario_input = request.POST.get("username", "").strip()
        clave_input = request.POST.get("password", "")

        usuario = authenticate(request, username=usuario_input, password=clave_input)
        if usuario is not None:
            login(request, usuario)
            rol = obtener_rol_usuario(usuario)
            if rol == "EMPLEADO":
                return redirect("portal_empleado")
            return redirect("inicio")
        else:
            messages.error(request, "Credenciales incorrectas. Verifique su usuario y contraseña.")

    return render(request, "registration/login.html")


@require_POST
def cerrar_sesion(request):
    """Cierra la sesión de cualquier perfil y vuelve al login."""
    logout(request)
    return redirect("login")


# ==============================================================================
# 2. PÁGINA INDEPENDIENTE PARA LOS EMPLEADOS (PORTAL DEL TRABAJADOR)
# ==============================================================================

@login_required(login_url="login")
def portal_empleado(request):
    """Página exclusiva donde el trabajador ve su ficha, obra, hitos y sus propios pagos."""
    perfil = getattr(request.user, "perfil", None)
    obra_actual = perfil.obra_asignada if perfil else None
    especialidad = perfil.especialidad if perfil else "Trabajador de Terreno"

    # La identidad se determina por la cuenta, nunca por coincidencias de nombre.
    mis_pagos = PagoManoObra.objects.filter(empleado=request.user).select_related("proyecto")
    total_ganado = sum(p.monto for p in mis_pagos)

    # Hitos de la obra asignada al trabajador
    if obra_actual:
        hitos = HitoCalendario.objects.filter(proyecto=obra_actual, completado=False)
    else:
        hitos = HitoCalendario.objects.none()

    contexto = {
        "perfil": perfil,
        "obra_actual": obra_actual,
        "especialidad": especialidad,
        "mis_pagos": mis_pagos,
        "total_ganado": total_ganado,
        "cantidad_pagos": mis_pagos.count(),
        "hitos": hitos,
    }
    return render(request, "paginas/portal_empleado.html", contexto)


# ==============================================================================
# 3. CENTRO DE COMANDO Y MÓDULOS DE GESTIÓN (ADMIN Y VISUALIZADOR)
# ==============================================================================

@login_required(login_url="login")
def inicio(request):
    """Dashboard principal estilo Bento para Administrador y Visualizador (HU-07 y HU-10)."""
    rol = obtener_rol_usuario(request.user)
    if rol == "EMPLEADO":
        return redirect("portal_empleado")

    proyectos = Proyecto.objects.filter(activo=True)
    presupuesto_total = sum(p.presupuesto_inicial for p in proyectos)
    gastos_totales = sum(p.gasto_total for p in proyectos)
    proximo_hito = HitoCalendario.objects.filter(completado=False).order_by("fecha").first()

    contexto = {
        "rol_usuario": rol,
        "es_admin": (rol == "ADMIN"),
        "proyectos": proyectos,
        "total_proyectos": proyectos.count(),
        "presupuesto_total": presupuesto_total,
        "gastos_totales": gastos_totales,
        "saldo_global": presupuesto_total - gastos_totales,
        "proximo_hito": proximo_hito,
    }
    return render(request, "paginas/inicio.html", contexto)


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def proyectos_view(request):
    """Listado según rol y creación de obras por administradores."""
    rol = obtener_rol_usuario(request.user)
    if request.method == "POST" and rol != "ADMIN":
        raise PermissionDenied("Solo el administrador puede crear proyectos.")
    form = ProyectoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                proyecto = form.save()
        except IntegrityError:
            form.add_error("nombre", "Ya existe una obra registrada con ese nombre.")
        else:
            messages.success(request, f"Obra '{proyecto.nombre}' creada correctamente.")
            return redirect("proyectos")
    return render(request, "paginas/proyectos.html", {
        "proyectos": proyectos_visibles(request.user), "form": form,
    })


@login_required(login_url="login")
@require_http_methods(["GET"])
def proyecto_detalle(request, pk):
    proyecto = get_object_or_404(proyectos_visibles(request.user), pk=pk)
    return render(request, "paginas/proyecto_detalle.html", {
        "proyecto": proyecto,
        "personal": proyecto.trabajadores_asignados.select_related("usuario"),
        "hitos": proyecto.hitos.all(),
    })


@solo_administrador
@require_http_methods(["GET", "POST"])
def proyecto_editar(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    form = ProyectoForm(request.POST if request.method == "POST" else None, instance=proyecto)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("nombre", "Ya existe una obra registrada con ese nombre.")
        else:
            messages.success(request, "Proyecto actualizado correctamente.")
            return redirect("proyecto_detalle", pk=proyecto.pk)
    return render(request, "paginas/proyecto_form.html", {"form": form, "proyecto": proyecto})


@solo_administrador
@require_http_methods(["GET", "POST"])
def proyecto_eliminar(request, pk):
    proyecto = Proyecto.objects.filter(pk=pk).first()
    if proyecto is None:
        messages.info(request, "El proyecto no existe o ya fue eliminado.")
        return redirect("proyectos")
    if request.method == "POST":
        nombre = proyecto.nombre
        with transaction.atomic():
            proyecto.delete()
        messages.success(request, f"Proyecto '{nombre}' eliminado correctamente.")
        return redirect("proyectos")
    return render(request, "paginas/proyecto_eliminar.html", {"proyecto": proyecto})


@login_required(login_url="login")
def finanzas_view(request):
    """Libro de Finanzas para registrar Materiales (HU-05) y Mano de Obra (HU-06)."""
    rol = obtener_rol_usuario(request.user)
    if request.method == "POST" and rol != "ADMIN":
        raise PermissionDenied("Solo el administrador puede registrar gastos y pagos.")
    if rol == "EMPLEADO":
        return redirect("portal_empleado")

    es_admin = (rol == "ADMIN")

    if request.method == "POST":
        tipo_egreso = request.POST.get("tipo_egreso", "MATERIAL")
        proyecto_id = request.POST.get("proyecto_id")
        monto = int(request.POST.get("monto", 0) or 0)
        fecha = request.POST.get("fecha")
        proyecto_obj = Proyecto.objects.filter(id=proyecto_id).first()

        if not proyecto_obj or monto <= 0:
            messages.error(request, "Verifique la obra seleccionada y que el monto sea mayor a 0.")
        elif tipo_egreso == "MATERIAL":
            proveedor = request.POST.get("proveedor", "").strip()
            categoria = request.POST.get("categoria", "OTROS")
            GastoMaterial.objects.create(
                proyecto=proyecto_obj,
                fecha=fecha,
                proveedor=proveedor,
                categoria=categoria,
                monto=monto,
            )
            messages.success(request, f"Factura de '{proveedor}' registrada. Saldo actualizado.")
        else:
            empleado_id = request.POST.get("empleado_id")
            trabajador_nombre = request.POST.get("trabajador", "").strip()
            concepto = request.POST.get("concepto", "Jornal / Avance de Obra").strip()
            empleado_obj = User.objects.filter(id=empleado_id).first() if empleado_id else None

            if empleado_obj and not trabajador_nombre:
                trabajador_nombre = empleado_obj.first_name or empleado_obj.username

            PagoManoObra.objects.create(
                proyecto=proyecto_obj,
                empleado=empleado_obj,
                trabajador=trabajador_nombre,
                concepto=concepto,
                monto=monto,
                fecha=fecha,
            )
            messages.success(request, f"Pago a '{trabajador_nombre}' registrado correctamente.")

        return redirect("finanzas")

    proyectos = Proyecto.objects.filter(activo=True)
    empleados = User.objects.filter(perfil__rol="EMPLEADO")
    gastos_materiales = GastoMaterial.objects.select_related("proyecto").all()
    pagos_mano_obra = PagoManoObra.objects.select_related("proyecto", "empleado").all()

    contexto = {
        "es_admin": es_admin,
        "proyectos": proyectos,
        "empleados": empleados,
        "gastos_materiales": gastos_materiales,
        "pagos_mano_obra": pagos_mano_obra,
    }
    return render(request, "paginas/finanzas.html", contexto)


@login_required(login_url="login")
def calendario_view(request):
    """Gestión de hitos y semáforo automático en rojo, amarillo y verde (HU-08 y HU-09)."""
    rol = obtener_rol_usuario(request.user)
    if request.method == "POST" and rol != "ADMIN":
        raise PermissionDenied("Solo el administrador puede modificar el calendario.")
    if rol == "EMPLEADO":
        return redirect("portal_empleado")

    es_admin = (rol == "ADMIN")

    if request.method == "POST" and es_admin:
        proyecto_id = request.POST.get("proyecto_id")
        nombre = request.POST.get("nombre", "").strip()
        fecha = request.POST.get("fecha")
        proyecto_obj = Proyecto.objects.filter(id=proyecto_id).first()

        if proyecto_obj and nombre and fecha:
            HitoCalendario.objects.create(proyecto=proyecto_obj, nombre=nombre, fecha=fecha)
            messages.success(request, f"Hito '{nombre}' programado en el calendario.")
            return redirect("calendario")

    proyectos = Proyecto.objects.filter(activo=True)
    hitos = HitoCalendario.objects.select_related("proyecto").all()
    return render(request, "paginas/calendario.html", {
        "es_admin": es_admin,
        "proyectos": proyectos,
        "hitos": hitos,
    })


@solo_administrador
@require_http_methods(["GET", "POST"])
def registro_usuario(request):
    """Creación atómica de cuenta y perfil, y listado exclusivo del administrador."""
    form = UsuarioForm(request.POST if request.method == "POST" else None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            nuevo_user = form.save()
        except IntegrityError:
            form.add_error(None, "No se pudo guardar la cuenta. Revise que el usuario no esté duplicado.")
        else:
            messages.success(request, f"Cuenta '{nuevo_user.username}' creada correctamente.")
            return redirect("registro_usuario")
    return render(request, "registration/registro.html", {
        "form": form,
        "usuarios": User.objects.select_related("perfil", "perfil__obra_asignada").order_by("username"),
    })


def usuario_gestionable(request, pk):
    usuario = get_object_or_404(User.objects.select_related("perfil", "perfil__obra_asignada"), pk=pk)
    if usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Solo un superusuario puede gestionar esta cuenta.")
    return usuario


@solo_administrador
@require_http_methods(["GET"])
def usuario_detalle(request, pk):
    usuario = get_object_or_404(User.objects.select_related("perfil", "perfil__obra_asignada"), pk=pk)
    return render(request, "registration/usuario_detalle.html", {
        "cuenta": usuario,
        "rol_cuenta": obtener_rol_usuario(usuario) or getattr(getattr(usuario, "perfil", None), "rol", "EMPLEADO"),
    })


@solo_administrador
@require_http_methods(["GET", "POST"])
def usuario_editar(request, pk):
    usuario = usuario_gestionable(request, pk)
    form = UsuarioForm(request.POST if request.method == "POST" else None, instance=usuario, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            usuario = form.save()
        except IntegrityError:
            form.add_error(None, "No se pudo guardar la cuenta. Revise que el usuario no esté duplicado.")
        else:
            if usuario.pk == request.user.pk:
                update_session_auth_hash(request, usuario)
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("usuario_detalle", pk=usuario.pk)
    return render(request, "registration/usuario_form.html", {"form": form, "cuenta": usuario})


@solo_administrador
@require_http_methods(["GET", "POST"])
def usuario_eliminar(request, pk):
    usuario = usuario_gestionable(request, pk)
    if usuario.pk == request.user.pk:
        raise PermissionDenied("No puede eliminar su propia cuenta de administrador.")
    if request.method == "POST":
        username = usuario.username
        with transaction.atomic():
            usuario.delete()
        messages.success(request, f"Usuario '{username}' eliminado correctamente.")
        return redirect("registro_usuario")
    return render(request, "registration/usuario_eliminar.html", {"cuenta": usuario})
