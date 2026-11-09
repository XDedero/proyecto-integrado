from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from .models import Proyecto, PerfilUsuario, GastoMaterial, PagoManoObra, HitoCalendario


def obtener_rol_usuario(user):
    """Determina el rol del usuario autenticado: ADMIN, VISUALIZADOR o EMPLEADO."""
    if not user.is_authenticated:
        return None
    if hasattr(user, "perfil"):
        return user.perfil.rol
    if user.is_superuser or user.is_staff:
        return "ADMIN"
    return "VISUALIZADOR"


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

    # Filtrar únicamente los pagos que pertenecen a este trabajador
    nombre_completo = request.user.first_name.strip()
    filtro_pagos = Q(empleado=request.user)
    if nombre_completo:
        filtro_pagos |= Q(trabajador__iexact=nombre_completo)
    filtro_pagos |= Q(trabajador__iexact=request.user.username)

    mis_pagos = PagoManoObra.objects.filter(filtro_pagos).distinct()
    total_ganado = sum(p.monto for p in mis_pagos)

    # Hitos de la obra asignada al trabajador
    if obra_actual:
        hitos = HitoCalendario.objects.filter(proyecto=obra_actual, completado=False)
    else:
        hitos = HitoCalendario.objects.filter(completado=False)[:4]

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
def proyectos_view(request):
    """Registro y listado de obras con presupuesto inicial mayor a 0 (HU-04)."""
    rol = obtener_rol_usuario(request.user)
    if rol == "EMPLEADO":
        return redirect("portal_empleado")
    if rol != "ADMIN":
        messages.error(request, "El rol Visualizador solo tiene permisos de lectura.")
        return redirect("inicio")

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        presupuesto = int(request.POST.get("presupuesto_inicial", 0) or 0)
        fecha_inicio = request.POST.get("fecha_inicio", "")

        if presupuesto <= 0:
            messages.error(request, "El presupuesto inicial debe ser mayor a 0 CLP.")
        elif Proyecto.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, "Ya existe una obra registrada con ese nombre.")
        else:
            Proyecto.objects.create(
                nombre=nombre,
                presupuesto_inicial=presupuesto,
                fecha_inicio=fecha_inicio,
            )
            messages.success(request, f"Obra '{nombre}' adjudicada correctamente.")
            return redirect("proyectos")

    proyectos = Proyecto.objects.all()
    return render(request, "paginas/proyectos.html", {"proyectos": proyectos, "es_admin": True})


@login_required(login_url="login")
def finanzas_view(request):
    """Libro de Finanzas para registrar Materiales (HU-05) y Mano de Obra (HU-06)."""
    rol = obtener_rol_usuario(request.user)
    if rol == "EMPLEADO":
        return redirect("portal_empleado")

    es_admin = (rol == "ADMIN")

    if request.method == "POST":
        if not es_admin:
            messages.error(request, "Acción denegada: el rol Visualizador no puede registrar gastos.")
            return redirect("finanzas")

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


@login_required(login_url="login")
def registro_usuario(request):
    """Permite al Administrador crear cuentas de Administrador, Visualizador o Empleado (HU-02)."""
    rol_actual = obtener_rol_usuario(request.user)
    if rol_actual != "ADMIN":
        messages.error(request, "Solo el Administrador puede gestionar las cuentas de usuario.")
        return redirect("inicio")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        nombre_completo = request.POST.get("first_name", "").strip()
        password = request.POST.get("password", "")
        rol_nuevo = request.POST.get("rol", "EMPLEADO")
        especialidad = request.POST.get("especialidad", "Maestro de Obra").strip()
        obra_id = request.POST.get("obra_id")
        obra_obj = Proyecto.objects.filter(id=obra_id).first() if obra_id else None

        if User.objects.filter(username=username).exists():
            messages.error(request, "El nombre de usuario ya existe. Elija otro identificador.")
        elif len(password) < 6:
            messages.error(request, "La contraseña debe tener al menos 6 caracteres.")
        else:
            nuevo_user = User.objects.create_user(
                username=username,
                password=password,
                first_name=nombre_completo,
            )
            nuevo_user.is_staff = (rol_nuevo == "ADMIN")
            nuevo_user.save()

            PerfilUsuario.objects.create(
                usuario=nuevo_user,
                rol=rol_nuevo,
                especialidad=especialidad,
                obra_asignada=obra_obj,
            )
            messages.success(request, f"Cuenta '{username}' creada con perfil {rol_nuevo}.")
            return redirect("registro_usuario")

    usuarios = User.objects.select_related("perfil", "perfil__obra_asignada").all()
    proyectos = Proyecto.objects.filter(activo=True)
    return render(request, "registration/registro.html", {
        "es_admin": True,
        "usuarios": usuarios,
        "proyectos": proyectos,
    })
