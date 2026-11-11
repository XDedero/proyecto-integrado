from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.html import format_html

from .models import GastoMaterial, PerfilUsuario, Proyecto


class EstiloFormulario:
    def aplicar_estilos(self):
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs["class"] = "form-check-input"
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"


class ProyectoForm(EstiloFormulario, forms.ModelForm):
    presupuesto_inicial = forms.IntegerField(
        label="Presupuesto inicial (CLP)", min_value=1, max_value=2147483647,
    )
    class Meta:
        model = Proyecto
        fields = ["nombre", "presupuesto_inicial", "fecha_inicio", "activo"]
        widgets = {"fecha_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if Proyecto.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe una obra registrada con ese nombre.")
        return nombre


class EgresoForm(EstiloFormulario, forms.Form):
    tipo_egreso = forms.ChoiceField(choices=[("MATERIAL", "Compra de materiales"), ("MANO_OBRA", "Pago de mano de obra")])
    proyecto_id = forms.ModelChoiceField(label="Obra asociada", queryset=Proyecto.objects.none())
    monto = forms.IntegerField(label="Monto en CLP", min_value=1, max_value=2147483647)
    fecha = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    proveedor = forms.CharField(max_length=100, required=False)
    categoria = forms.ChoiceField(label="Categoría", choices=GastoMaterial.CATEGORIAS, required=False)
    empleado_id = forms.ModelChoiceField(label="Empleado registrado", queryset=User.objects.none(), required=False)
    trabajador = forms.CharField(label="Nombre del trabajador", max_length=100, required=False)
    concepto = forms.CharField(label="Concepto", max_length=120, required=False, initial="Jornal / Avance de Obra")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proyecto_id"].queryset = Proyecto.objects.filter(activo=True)
        self.fields["empleado_id"].queryset = User.objects.filter(is_active=True, is_superuser=False, perfil__rol="EMPLEADO")
        self.aplicar_estilos()
        for nombre, campo in self.fields.items():
            campo.widget.attrs["id"] = nombre
        self.fields["tipo_egreso"].widget.attrs["onchange"] = "alternarCampos()"

    def clean(self):
        datos = super().clean()
        if datos.get("tipo_egreso") == "MATERIAL":
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
        return datos


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
