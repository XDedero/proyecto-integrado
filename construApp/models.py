from datetime import date
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum


class Proyecto(models.Model):
    """Representa una obra de la Constructora LC y su presupuesto inicial (HU-04, HU-07)."""

    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del proyecto")
    presupuesto_inicial = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Presupuesto inicial (CLP)",
    )
    fecha_inicio = models.DateField(verbose_name="Fecha de inicio")
    activo = models.BooleanField(default=True, verbose_name="Proyecto activo")

    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"{self.nombre} (${self.presupuesto_inicial:,} CLP)"

    @property
    def total_materiales(self):
        resultado = self.gastos_materiales.aggregate(total=Sum("monto"))["total"]
        return resultado or 0

    @property
    def total_mano_obra(self):
        resultado = self.pagos_mano_obra.aggregate(total=Sum("monto"))["total"]
        return resultado or 0

    @property
    def gasto_total(self):
        return self.total_materiales + self.total_mano_obra

    @property
    def saldo_disponible(self):
        return self.presupuesto_inicial - self.gasto_total


class PerfilUsuario(models.Model):
    """Extiende el usuario de Django para diferenciar Admin, Visualizador (Contador) y Empleado."""

    ROLES = [
        ("ADMIN", "Administrador (Control Total)"),
        ("VISUALIZADOR", "Visualizador / Contador (Solo Lectura)"),
        ("EMPLEADO", "Empleado / Trabajador de Obra"),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(max_length=20, choices=ROLES, default="EMPLEADO")
    especialidad = models.CharField(
        max_length=80,
        blank=True,
        default="Maestro de Obra",
        verbose_name="Cargo o Especialidad",
    )
    obra_asignada = models.ForeignKey(
        Proyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trabajadores_asignados",
        verbose_name="Obra asignada actualmente",
    )

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self):
        return f"{self.usuario.username} ({self.get_rol_display()})"


class GastoMaterial(models.Model):
    """Registra compras de materiales y facturas de proveedores por obra (HU-05)."""

    CATEGORIAS = [
        ("MADERA", "Madera y Tableros"),
        ("FIERRO", "Fierro y Estructuras"),
        ("CEMENTO", "Cemento, Áridos y Hormigón"),
        ("TERMINACIONES", "Pintura y Terminaciones"),
        ("HERRAMIENTAS", "Herramientas e Insumos"),
        ("OTROS", "Otros Materiales"),
    ]

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="gastos_materiales",
        verbose_name="Proyecto asociado",
    )
    fecha = models.DateField(verbose_name="Fecha del gasto")
    proveedor = models.CharField(max_length=100, verbose_name="Proveedor")
    categoria = models.CharField(max_length=30, choices=CATEGORIAS, verbose_name="Categoría")
    monto = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Monto en pesos (CLP)",
    )

    class Meta:
        verbose_name = "Gasto de Material"
        verbose_name_plural = "Gastos de Materiales"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.proveedor} - ${self.monto:,} ({self.proyecto.nombre})"


class PagoManoObra(models.Model):
    """Registra pagos de jornales, tratos y sueldos por proyecto y empleado (HU-06)."""

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="pagos_mano_obra",
        verbose_name="Proyecto asociado",
    )
    empleado = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_recibidos",
        verbose_name="Cuenta del trabajador (opcional)",
    )
    trabajador = models.CharField(max_length=100, verbose_name="Nombre del trabajador")
    concepto = models.CharField(
        max_length=120,
        default="Jornal / Avance de Obra",
        verbose_name="Concepto o labor realizada",
    )
    monto = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Monto pagado (CLP)",
    )
    fecha = models.DateField(verbose_name="Fecha de pago")

    class Meta:
        verbose_name = "Pago de Mano de Obra"
        verbose_name_plural = "Pagos de Mano de Obra"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.trabajador} - ${self.monto:,} ({self.proyecto.nombre})"


class HitoCalendario(models.Model):
    """Registra fechas importantes de cada obra y calcula su alerta de color (HU-08, HU-09)."""

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="hitos",
        verbose_name="Proyecto asociado",
    )
    nombre = models.CharField(max_length=120, verbose_name="Nombre del hito")
    fecha = models.DateField(verbose_name="Fecha límite")
    completado = models.BooleanField(default=False, verbose_name="Completado")

    class Meta:
        verbose_name = "Hito de Calendario"
        verbose_name_plural = "Hitos de Calendario"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.nombre} ({self.fecha}) - {self.proyecto.nombre}"

    @property
    def dias_restantes(self):
        return (self.fecha - date.today()).days

    @property
    def color_alerta(self):
        dias = self.dias_restantes
        if dias < 3:
            return "rojo"
        if dias < 7:
            return "amarillo"
        return "verde"
