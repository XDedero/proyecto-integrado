from datetime import date
from importlib import import_module
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .forms import EgresoForm, ProyectoForm
from .models import CategoriaMaterial, Cliente, GastoMaterial, PagoManoObra, Proyecto, TipoObra


class FiltrosFleteOpcionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin_flete", is_staff=True)
        cls.lector = User.objects.create_user("lector_flete")
        cls.lector.perfil.rol = "VISUALIZADOR"
        cls.lector.perfil.save()
        cls.empleado = User.objects.create_user("empleado_flete")
        cls.cliente = Cliente.objects.create(nombre="Cliente de fletes")
        cls.obra = Proyecto.objects.create(nombre="Obra con flete", cliente=cls.cliente, presupuesto_inicial=10000, fecha_inicio=date(2026, 11, 1))
        cls.otra = Proyecto.objects.create(nombre="Obra cerrada", cliente=cls.cliente, presupuesto_inicial=5000, fecha_inicio=date(2026, 11, 1), activo=False)
        cls.vacia = Proyecto.objects.create(nombre="Obra sin gastos", presupuesto_inicial=1000, fecha_inicio=date(2026, 11, 1))
        cls.gasto = GastoMaterial.objects.create(proyecto=cls.obra, nombre="Compra inicial", proveedor="Ferretería", categoria="MADERA", monto=100, con_flete=True, monto_flete=20, fecha=date(2026, 11, 20))
        cls.pago = PagoManoObra.objects.create(proyecto=cls.obra, nombre="Avance inicial", empleado=cls.empleado, trabajador="Ana", monto=200, con_flete=True, monto_flete=30, fecha=date(2026, 11, 20))
        GastoMaterial.objects.create(proyecto=cls.otra, proveedor="Proveedor cerrado", categoria="OTROS", monto=400, fecha=date(2026, 11, 20))
        PagoManoObra.objects.create(proyecto=cls.otra, trabajador="Externo cerrado", monto=500, fecha=date(2026, 11, 20))

    def setUp(self):
        self.client.force_login(self.admin)

    def datos_egreso(self, tipo="MATERIAL", **cambios):
        datos = {"tipo_egreso": tipo, "proyecto_id": self.obra.pk, "nombre": "Compra de cerámicas", "monto": "300", "fecha": "2026-11-20", "proveedor": "Proveedor", "categoria": "OTROS", "trabajador": "Ana", "empleado_id": self.empleado.pk}
        datos.update(cambios)
        return datos

    def datos_obra(self, **cambios):
        datos = {"nombre": "Nueva obra", "cliente": self.cliente.pk, "tipo_obra": "CONSTRUCCION", "direccion": "Calle 123", "presupuesto_inicial": "2000", "fecha_inicio": "2026-11-20", "fecha_termino_estimada": "2026-12-20", "activo": "on"}
        datos.update(cambios)
        return datos

    def test_filtro_aisla_ambas_tablas_y_totales_con_flete_para_admin_y_lector(self):
        for usuario in (self.admin, self.lector):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("finanzas"), {"proyecto": self.obra.pk})
            self.assertEqual(list(respuesta.context["gastos_materiales"]), [self.gasto])
            self.assertEqual(list(respuesta.context["pagos_mano_obra"]), [self.pago])
            self.assertEqual((respuesta.context["total_materiales"], respuesta.context["total_mano_obra"], respuesta.context["total_egresos"]), (120, 230, 350))
            self.assertContains(respuesta, "Compra inicial")
            self.assertContains(respuesta, "Avance inicial")
            self.assertNotContains(respuesta, "Proveedor cerrado")
            self.assertNotContains(respuesta, "Externo cerrado")

    def test_todas_las_obras_incluye_inactivas_y_permite_filtrarlas(self):
        self.assertEqual(self.client.get(reverse("finanzas")).context["total_egresos"], 1250)
        respuesta = self.client.get(reverse("finanzas"), {"proyecto": self.otra.pk})
        self.assertEqual(respuesta.context["total_egresos"], 900)
        self.assertContains(respuesta, "Proveedor cerrado")

    def test_obra_sin_gastos_y_filtro_invalido(self):
        self.assertEqual(self.client.get(reverse("finanzas"), {"proyecto": self.vacia.pk}).context["total_egresos"], 0)
        for valor in ("999999", "texto", "1 OR 1=1"):
            respuesta = self.client.get(reverse("finanzas"), {"proyecto": valor})
            self.assertTrue(respuesta.context["filtro"].errors)
            self.assertEqual(respuesta.context["total_egresos"], 0)
            self.assertFalse(respuesta.context["gastos_materiales"].exists())

    def test_registrar_con_nombre_y_flete_para_material_y_mano_obra(self):
        for tipo, modelo in (("MATERIAL", GastoMaterial), ("MANO_OBRA", PagoManoObra)):
            respuesta = self.client.post(reverse("finanzas"), self.datos_egreso(tipo, con_flete="on", monto_flete="50"))
            self.assertRedirects(respuesta, reverse("finanzas"))
            registro = modelo.objects.latest("pk")
            self.assertEqual((registro.nombre, registro.monto, registro.monto_flete, registro.monto_total), ("Compra de cerámicas", 300, 50, 350))
            self.assertTrue(registro.con_flete)

    def test_guardar_desde_filtro_conserva_seleccion_y_actualiza_total(self):
        ruta = reverse("finanzas") + f"?proyecto={self.obra.pk}"
        self.assertEqual(self.client.get(ruta).context["form"]["proyecto_id"].value(), self.obra.pk)
        self.assertRedirects(self.client.post(ruta, self.datos_egreso()), ruta)
        self.assertEqual(self.client.get(ruta).context["total_egresos"], 650)

    def test_flete_requiere_monto_positivo_valido_y_total_en_rango(self):
        for tipo in ("MATERIAL", "MANO_OBRA"):
            for monto in ("", "0", "-1", "texto", "1.5", "2147483648", "2147483647"):
                with self.subTest(tipo=tipo, monto=monto):
                    form = EgresoForm(self.datos_egreso(tipo, con_flete="on", monto_flete=monto))
                    self.assertFalse(form.is_valid())
                    self.assertIn("monto_flete", form.errors)

    def test_editar_no_duplica_flete_y_desmarcar_lo_quita(self):
        for tipo, registro in (("material", self.gasto), ("mano-obra", self.pago)):
            ruta = reverse("egreso_editar", args=[tipo, registro.pk])
            form = self.client.get(ruta).context["form"]
            self.assertEqual((form["monto"].value(), form["monto_flete"].value(), form["con_flete"].value()), (registro.monto, registro.monto_flete, True))
            datos = self.datos_egreso("MATERIAL" if tipo == "material" else "MANO_OBRA", con_flete="on", monto_flete="50")
            for _ in range(2):
                self.assertRedirects(self.client.post(ruta, datos), reverse("finanzas"))
                registro.refresh_from_db()
                self.assertEqual(registro.monto_total, 350)
            datos.pop("con_flete")
            self.assertRedirects(self.client.post(ruta, datos), reverse("finanzas"))
            registro.refresh_from_db()
            self.assertEqual((registro.con_flete, registro.monto_flete, registro.monto_total), (False, 0, 300))

    def test_saldos_dashboard_historial_y_portal_incluyen_flete(self):
        self.assertEqual((self.obra.total_materiales, self.obra.total_mano_obra, self.obra.saldo_disponible), (120, 230, 9650))
        self.assertEqual(self.client.get(reverse("inicio")).context["gastos_totales"], 350)
        self.assertEqual(self.client.get(reverse("cliente_detalle", args=[self.cliente.pk])).context["gastos"], 1250)
        self.client.force_login(self.empleado)
        respuesta = self.client.get(reverse("portal_empleado"))
        self.assertEqual(respuesta.context["total_ganado"], 230)
        self.assertContains(respuesta, "Avance inicial")

    def test_crear_categoria_reutilizarla_y_conservarla_al_eliminar_gasto(self):
        datos = self.datos_egreso(categoria="__nueva__", nueva_categoria=" Electricidad ")
        self.assertRedirects(self.client.post(reverse("finanzas"), datos), reverse("finanzas"))
        gasto = GastoMaterial.objects.latest("pk")
        self.assertEqual(gasto.categoria, "Electricidad")
        self.assertIn(("Electricidad", "Electricidad"), EgresoForm().fields["categoria"].choices)
        gasto.delete()
        self.assertTrue(CategoriaMaterial.objects.filter(nombre="Electricidad").exists())
        self.assertRedirects(self.client.post(reverse("finanzas"), self.datos_egreso(categoria="Electricidad")), reverse("finanzas"))
        self.assertRedirects(self.client.post(reverse("finanzas"), self.datos_egreso(categoria="__nueva__", nueva_categoria="electricidad")), reverse("finanzas"))
        self.assertEqual(CategoriaMaterial.objects.count(), 1)

    def test_categoria_nueva_duplicada_de_predefinida_reutiliza_opcion(self):
        self.client.post(reverse("finanzas"), self.datos_egreso(categoria="__nueva__", nueva_categoria="madera y tableros"))
        self.assertEqual(GastoMaterial.objects.latest("pk").categoria, "MADERA")
        self.assertEqual(CategoriaMaterial.objects.count(), 0)

    def test_nuevas_opciones_requieren_nombre_y_no_se_crean_si_hay_errores(self):
        for nombre in ("", " ", "x" * 101, "__nueva__"):
            self.assertFalse(EgresoForm(self.datos_egreso(categoria="__nueva__", nueva_categoria=nombre)).is_valid())
            self.assertFalse(ProyectoForm(self.datos_obra(tipo_obra="__nueva__", nuevo_tipo_obra=nombre)).is_valid())
        self.client.post(reverse("finanzas"), self.datos_egreso(categoria="__nueva__", nueva_categoria="Inválida", monto="-1"))
        self.assertEqual(CategoriaMaterial.objects.count(), 0)
        self.assertEqual(TipoObra.objects.count(), 0)

    def test_fallo_al_guardar_revierte_nueva_categoria(self):
        with patch("construApp.forms.GastoMaterial.objects.create", side_effect=IntegrityError):
            respuesta = self.client.post(reverse("finanzas"), self.datos_egreso(categoria="__nueva__", nueva_categoria="No guardar"))
        self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertFalse(CategoriaMaterial.objects.exists())

    def test_crear_y_editar_obra_sin_descripcion_y_con_tipo_nuevo(self):
        datos = self.datos_obra(tipo_obra="__nueva__", nuevo_tipo_obra="Paisajismo")
        self.assertRedirects(self.client.post(reverse("proyectos"), datos), reverse("proyectos"))
        obra = Proyecto.objects.get(nombre="Nueva obra")
        self.assertEqual((obra.descripcion, obra.tipo_obra), ("", "Paisajismo"))
        self.assertFalse(ProyectoForm(instance=obra).fields["descripcion"].required)
        datos.update(tipo_obra="__nueva__", nuevo_tipo_obra="paisajismo")
        self.assertRedirects(self.client.post(reverse("proyecto_editar", args=[obra.pk]), datos), reverse("proyecto_detalle", args=[obra.pk]))
        self.assertEqual(TipoObra.objects.count(), 1)
        self.assertContains(self.client.get(reverse("proyecto_detalle", args=[obra.pk])), "Paisajismo")
        obra.delete()
        self.assertIn(("Paisajismo", "Paisajismo"), ProyectoForm().fields["tipo_obra"].choices)

    def test_lectores_y_empleados_no_pueden_crear_opciones(self):
        for usuario in (self.lector, self.empleado):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse("finanzas"), self.datos_egreso(categoria="__nueva__", nueva_categoria="Prohibida")).status_code, 403)
            self.assertEqual(self.client.post(reverse("proyectos"), self.datos_obra(tipo_obra="__nueva__", nuevo_tipo_obra="Prohibido")).status_code, 403)
        self.assertFalse(CategoriaMaterial.objects.exists())
        self.assertFalse(TipoObra.objects.exists())
        self.assertRedirects(self.client.get(reverse("finanzas"), {"proyecto": self.otra.pk}), reverse("portal_empleado"))

    def test_base_rechaza_estados_de_flete_incoherentes(self):
        for registro in (self.gasto, self.pago):
            for cambios in ({"con_flete": False, "monto_flete": 20}, {"con_flete": True, "monto_flete": 0}):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(registro).objects.filter(pk=registro.pk).update(**cambios)

    def test_nombre_y_categorias_se_muestran_escapados(self):
        ataque = '<script>alert("x")</script>'
        self.client.post(reverse("finanzas"), self.datos_egreso(nombre=ataque, categoria="__nueva__", nueva_categoria=ataque))
        respuesta = self.client.get(reverse("finanzas"))
        self.assertNotContains(respuesta, ataque)
        self.assertContains(respuesta, "&lt;script&gt;")


class MigracionFleteTests(TransactionTestCase):
    def test_actualizacion_conserva_montos_anteriores_sin_flete(self):
        executor = MigrationExecutor(connection)
        anterior = ("construApp", "0005_clientes_y_ficha_obra")
        executor.migrate([anterior])
        try:
            apps = executor.loader.project_state([anterior]).apps
            obra = apps.get_model("construApp", "Proyecto").objects.create(nombre="Obra heredada sin flete", presupuesto_inicial=1000, fecha_inicio=date(2026, 1, 1))
            apps.get_model("construApp", "GastoMaterial").objects.create(proyecto_id=obra.pk, proveedor="Anterior", categoria="MADERA", monto=100, fecha=date(2026, 1, 1))
            apps.get_model("construApp", "PagoManoObra").objects.create(proyecto_id=obra.pk, trabajador="Anterior", monto=200, fecha=date(2026, 1, 1))
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            for registro in (GastoMaterial.objects.get(proyecto_id=obra.pk), PagoManoObra.objects.get(proyecto_id=obra.pk)):
                self.assertFalse(registro.con_flete)
                self.assertEqual(registro.monto_flete, 0)
                self.assertEqual(registro.monto_total, registro.monto)
            self.assertEqual(Proyecto.objects.get(pk=obra.pk).saldo_disponible, 700)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_catalogos_reciben_proteccion_supabase(self):
        migracion = import_module("construApp.migrations.0006_filtros_egresos_flete_y_opciones")
        editor = MagicMock()
        editor.connection.vendor = "postgresql"
        editor.connection.ops.quote_name.side_effect = lambda nombre: '"' + nombre + '"'
        cursor = editor.connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [("anon",), ("authenticated",)]
        apps = MagicMock()
        apps.get_model.side_effect = lambda app, modelo: {"CategoriaMaterial": CategoriaMaterial, "TipoObra": TipoObra}[modelo]
        migracion.proteger_catalogos(apps, editor)
        sentencias = [llamada.args[0] for llamada in cursor.execute.call_args_list]
        for modelo in (CategoriaMaterial, TipoObra):
            tabla = modelo._meta.db_table
            self.assertIn(f'ALTER TABLE "{tabla}" ENABLE ROW LEVEL SECURITY', sentencias)
            self.assertIn(f'REVOKE ALL PRIVILEGES ON TABLE "{tabla}" FROM PUBLIC, "anon", "authenticated"', sentencias)
