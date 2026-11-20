import re

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.html import format_html

from .models import CategoriaMaterial, Cliente, GastoMaterial, PagoManoObra, PerfilUsuario, Proyecto, TipoObra


NUEVA_OPCION = "__nueva__"


def opciones_personalizadas(base, modelo):
    return list(base) + [(nombre, nombre) for nombre in modelo.objects.values_list("nombre", flat=True)] + [(NUEVA_OPCION, "Agregar nueva…")]


def resolver_opcion(form, campo, nuevo_campo):
    valor = form.cleaned_data.get(campo)
    if valor == NUEVA_OPCION:
        nombre = form.cleaned_data.get(nuevo_campo, "")
        if not nombre:
            if nuevo_campo not in form.errors:
                form.add_error(nuevo_campo, "Escriba el nombre de la nueva opción.")
            return ""
        if nombre == NUEVA_OPCION:
            form.add_error(nuevo_campo, "Elija otro nombre.")
            return ""
        # Reutiliza también las opciones predefinidas si se escribe su etiqueta.
        for clave, etiqueta in form.fields[campo].choices:
            if clave != NUEVA_OPCION and nombre.casefold() in (clave.casefold(), etiqueta.casefold()):
                return clave
        return nombre
    return valor


def guardar_opcion(modelo, valor, base):
    if valor not in dict(base):
        opcion, _ = modelo.objects.get_or_create(nombre__iexact=valor, defaults={"nombre": valor})
        return opcion.nombre
    return valor


class EstiloFormulario:
    def aplicar_estilos(self):
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs["class"] = "form-check-input"
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"


class ClienteForm(EstiloFormulario, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "rut", "telefono", "email", "direccion", "notas"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean_rut(self):
        compacto = re.sub(r"[.\s-]", "", self.cleaned_data.get("rut") or "").upper()
        if compacto and not re.fullmatch(r"[0-9]{1,8}[0-9K]", compacto):
            raise ValidationError("Ingrese el RUT con su dígito verificador, por ejemplo 12345678-5.")
        rut = f"{compacto[:-1]}-{compacto[-1]}" if compacto else None
        if rut and Cliente.objects.filter(rut__iexact=rut).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un cliente con ese RUT. Selecciónelo para reunir sus obras en el mismo historial.")
        return rut


class ProyectoForm(EstiloFormulario, forms.ModelForm):
    tipo_obra = forms.ChoiceField(label="Tipo de obra")
    nuevo_tipo_obra = forms.CharField(label="Nuevo tipo de obra", max_length=100, required=False)
    presupuesto_inicial = forms.IntegerField(
        label="Presupuesto inicial (CLP)", min_value=1, max_value=2147483647,
    )
    class Meta:
        model = Proyecto
        fields = [
            "nombre", "cliente", "tipo_obra", "nuevo_tipo_obra", "descripcion", "direccion", "comuna", "region",
            "responsable", "presupuesto_inicial", "fecha_inicio", "fecha_termino_estimada", "observaciones", "activo",
        ]
        widgets = {
            "fecha_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "fecha_termino_estimada": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los registros anteriores pueden seguir incompletos en la base; al guardar
        # una ficha se exigen los datos mínimos de una obra nueva o actualizada.
        for nombre in ("cliente", "direccion", "fecha_termino_estimada"):
            self.fields[nombre].required = True
        self.fields["tipo_obra"].choices = opciones_personalizadas(Proyecto.TIPOS_OBRA, TipoObra)
        self.fields["descripcion"].help_text = "Opcional. Puede completar el alcance de los trabajos más adelante."
        self.fields["cliente"].help_text = "Seleccione el cliente existente para conservar todas sus obras en un mismo historial."
        self.aplicar_estilos()

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if Proyecto.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe una obra registrada con ese nombre.")
        return nombre

    def clean(self):
        datos = super().clean()
        datos["tipo_obra"] = resolver_opcion(self, "tipo_obra", "nuevo_tipo_obra")
        return datos

    @transaction.atomic
    def save(self, commit=True):
        proyecto = super().save(commit=False)
        if commit:
            proyecto.tipo_obra = guardar_opcion(TipoObra, self.cleaned_data["tipo_obra"], Proyecto.TIPOS_OBRA)
            proyecto.save()
            self.save_m2m()
        return proyecto


class FiltroEgresoForm(EstiloFormulario, forms.Form):
    proyecto = forms.ModelChoiceField(
        label="Filtrar por obra", queryset=Proyecto.objects.all(), required=False, empty_label="Todas las obras",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class EgresoForm(EstiloFormulario, forms.Form):
    tipo_egreso = forms.ChoiceField(choices=[("MATERIAL", "Compra de materiales"), ("MANO_OBRA", "Pago de mano de obra")])
    proyecto_id = forms.ModelChoiceField(label="Obra asociada", queryset=Proyecto.objects.none())
    nombre = forms.CharField(label="Nombre del gasto o pago", max_length=150, required=False)
    monto = forms.IntegerField(label="Monto sin flete (CLP)", min_value=1, max_value=2147483647)
    con_flete = forms.BooleanField(label="Sí, incluye flete", required=False)
    monto_flete = forms.IntegerField(label="Monto del flete (CLP)", min_value=0, max_value=2147483647, required=False)
    fecha = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    proveedor = forms.CharField(max_length=100, required=False)
    categoria = forms.ChoiceField(label="Categoría", choices=GastoMaterial.CATEGORIAS, required=False)
    nueva_categoria = forms.CharField(label="Nueva categoría de material", max_length=100, required=False)
    empleado_id = forms.ModelChoiceField(label="Empleado registrado", queryset=User.objects.none(), required=False)
    trabajador = forms.CharField(label="Nombre del trabajador", max_length=100, required=False)
    concepto = forms.CharField(label="Concepto", max_length=120, required=False, initial="Jornal / Avance de Obra")

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["categoria"].choices = opciones_personalizadas(GastoMaterial.CATEGORIAS, CategoriaMaterial)
        proyecto_actual = instance.proyecto_id if instance else None
        empleado_actual = instance.empleado_id if isinstance(instance, PagoManoObra) else None
        self.fields["proyecto_id"].queryset = Proyecto.objects.filter(Q(activo=True) | Q(pk=proyecto_actual))
        self.fields["empleado_id"].queryset = User.objects.filter(
            Q(is_active=True, is_superuser=False, perfil__rol="EMPLEADO") | Q(pk=empleado_actual)
        )
        if instance:
            self.initial.update({
                "tipo_egreso": "MATERIAL" if isinstance(instance, GastoMaterial) else "MANO_OBRA",
                "proyecto_id": instance.proyecto_id, "monto": instance.monto, "fecha": instance.fecha,
                "nombre": instance.nombre, "con_flete": instance.con_flete, "monto_flete": instance.monto_flete,
            })
            if isinstance(instance, GastoMaterial):
                self.initial.update(proveedor=instance.proveedor, categoria=instance.categoria)
            else:
                self.initial.update(empleado_id=instance.empleado_id, trabajador=instance.trabajador, concepto=instance.concepto)
            # Una corrección no convierte una compra en un pago de otro tipo.
            self.fields["tipo_egreso"].disabled = True
        self.aplicar_estilos()
        for nombre, campo in self.fields.items():
            campo.widget.attrs["id"] = nombre
        self.fields["tipo_egreso"].widget.attrs["onchange"] = "alternarCampos()"

    def clean(self):
        datos = super().clean()
        if datos.get("tipo_egreso") == "MATERIAL":
            datos["categoria"] = resolver_opcion(self, "categoria", "nueva_categoria")
            for campo in ("proveedor", "categoria"):
                if not datos.get(campo) and campo not in self.errors:
                    self.add_error(campo, "Este campo es obligatorio para una compra de materiales.")
        elif datos.get("tipo_egreso") == "MANO_OBRA":
            empleado = datos.get("empleado_id")
            if not datos.get("trabajador"):
                if empleado:
                    datos["trabajador"] = empleado.first_name or empleado.username
                    if len(datos["trabajador"]) > 100:
                        self.add_error("trabajador", "Escriba un nombre de trabajador de hasta 100 caracteres.")
                elif "empleado_id" not in self.errors:
                    self.add_error("trabajador", "Seleccione un empleado o escriba el nombre del trabajador.")
            datos["concepto"] = datos.get("concepto") or "Jornal / Avance de Obra"
        if datos.get("con_flete"):
            if "monto_flete" not in self.errors and not datos.get("monto_flete"):
                self.add_error("monto_flete", "Ingrese un monto de flete mayor que cero.")
        else:
            datos["monto_flete"] = 0
        if (datos.get("monto") or 0) + (datos.get("monto_flete") or 0) > 2147483647:
            self.add_error("monto_flete", "El total con flete no puede superar $2147483647 CLP.")
        return datos

    @transaction.atomic
    def save(self):
        datos = self.cleaned_data
        modelo = GastoMaterial if datos["tipo_egreso"] == "MATERIAL" else PagoManoObra
        valores = {"proyecto": datos["proyecto_id"], "monto": datos["monto"], "fecha": datos["fecha"]}
        valores.update(nombre=datos["nombre"], con_flete=datos["con_flete"], monto_flete=datos["monto_flete"])
        if modelo is GastoMaterial:
            categoria = guardar_opcion(CategoriaMaterial, datos["categoria"], GastoMaterial.CATEGORIAS)
            valores.update(proveedor=datos["proveedor"], categoria=categoria)
        else:
            valores.update(empleado=datos.get("empleado_id"), trabajador=datos["trabajador"], concepto=datos["concepto"])
        if self.instance is None:
            self.instance = modelo.objects.create(**valores)
        else:
            for campo, valor in valores.items():
                setattr(self.instance, campo, valor)
            # UPDATE evita recrear un registro eliminado mientras se editaba.
            self.instance.save(update_fields=list(valores))
        return self.instance


class HitoForm(EstiloFormulario, forms.Form):
    proyecto_id = forms.ModelChoiceField(label="Obra asociada", queryset=Proyecto.objects.none())
    nombre = forms.CharField(label="Descripción del hito", max_length=120)
    fecha = forms.DateField(label="Fecha límite", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proyecto_id"].queryset = Proyecto.objects.filter(activo=True)
        self.aplicar_estilos()


class UsuarioForm(EstiloFormulario, forms.ModelForm):
    rol = forms.ChoiceField(label="Rol y permisos", choices=PerfilUsuario.ROLES, initial="EMPLEADO")
    especialidad = forms.CharField(label="Cargo o especialidad", max_length=80, required=False)
    obra_asignada = forms.ModelChoiceField(
        label="Obra asignada al empleado", queryset=Proyecto.objects.none(), required=False,
        empty_label="Sin obra asignada",
        help_text="Los empleados solo pueden consultar su obra asignada.",
    )
    password = forms.CharField(
        label="Contraseña", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"first_name": "Nombre", "last_name": "Apellidos", "email": "Correo electrónico"}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["first_name"].required = True
        proyecto_actual = None
        if self.instance.pk:
            perfil = getattr(self.instance, "perfil", None)
            if self.instance.is_superuser:
                self.initial["rol"] = "ADMIN"
            elif perfil:
                self.initial["rol"] = perfil.rol
            else:
                self.initial["rol"] = "ADMIN" if self.instance.is_staff else "EMPLEADO"
            if perfil:
                self.initial["especialidad"] = perfil.especialidad
                self.initial["obra_asignada"] = perfil.obra_asignada_id
                proyecto_actual = perfil.obra_asignada_id
            self.fields["password"].help_text = format_html(
                "Deje ambos campos vacíos para conservar la contraseña. {}",
                password_validation.password_validators_help_text_html(),
            )
        else:
            self.fields["password"].required = True
            self.fields["password_confirm"].required = True
        self.fields["obra_asignada"].queryset = Proyecto.objects.filter(
            Q(activo=True) | Q(pk=proyecto_actual)
        )
        self.aplicar_estilos()

    def clean_username(self):
        username = User.normalize_username(self.cleaned_data["username"].strip())
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError("El nombre de usuario ya existe. Elija otro identificador.")
        return username

    def clean(self):
        datos = super().clean()
        password = datos.get("password")
        confirmacion = datos.get("password_confirm")
        if (password or confirmacion) and password != confirmacion:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        if password:
            candidato = User(**{
                campo: datos.get(campo, "")
                for campo in ("username", "first_name", "last_name", "email")
            })
            try:
                password_validation.validate_password(password, candidato)
            except ValidationError as error:
                self.add_error("password", error)
        if self.instance.pk:
            if self.instance.is_superuser:
                if not self.actor.is_superuser:
                    raise ValidationError("Solo un superusuario puede modificar esta cuenta.")
                if datos.get("rol") != "ADMIN":
                    self.add_error("rol", "Un superusuario debe mantener el rol Administrador.")
            if self.instance.pk == self.actor.pk:
                if datos.get("rol") != "ADMIN" or not datos.get("is_active"):
                    raise ValidationError("No puede quitarse sus permisos ni desactivar su propia cuenta.")
        return datos

    @transaction.atomic
    def save(self):
        usuario = super().save(commit=False)
        usuario.is_staff = self.cleaned_data["rol"] == "ADMIN"
        if self.cleaned_data.get("password"):
            usuario.set_password(self.cleaned_data["password"])
        usuario.save()
        PerfilUsuario.objects.update_or_create(
            usuario=usuario,
            defaults={
                "rol": self.cleaned_data["rol"],
                "especialidad": self.cleaned_data["especialidad"],
                "obra_asignada": (
                    self.cleaned_data["obra_asignada"]
                    if self.cleaned_data["rol"] == "EMPLEADO" else None
                ),
            },
        )
        return usuario
