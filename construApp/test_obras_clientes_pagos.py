from datetime import date
from importlib import import_module
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .models import Cliente, GastoMaterial, PagoManoObra, Proyecto


class ObrasClientesPagosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        cls.admin = User.objects.create_user("gestor", is_staff=True)
        cls.lector = User.objects.create_user("lector")
        cls.lector.perfil.rol = "VISUALIZADOR"
        cls.lector.perfil.save()
        cls.empleado = User.objects.create_user("ana", first_name="Ana")
        cls.otro_empleado = User.objects.create_user("pedro", first_name="Pedro")
        cls.cliente = Cliente.objects.create(nombre="Cliente habitual", rut="12345678-5", email="cliente@example.com")
        cls.otro_cliente = Cliente.objects.create(nombre="Otro cliente")
        cls.obra = Proyecto.objects.create(nombre="Casa", cliente=cls.cliente, presupuesto_inicial=10000, fecha_inicio=date(2026, 11, 1))
        cls.otra_obra = Proyecto.objects.create(nombre="Ampliación", cliente=cls.cliente, presupuesto_inicial=20000, fecha_inicio=date(2026, 11, 2), activo=False)
        cls.obra_ajena = Proyecto.objects.create(nombre="Local de otro cliente", cliente=cls.otro_cliente, presupuesto_inicial=30000, fecha_inicio=date(2026, 11, 3))
        cls.gasto = GastoMaterial.objects.create(proyecto=cls.obra, proveedor="Ferretería", categoria="OTROS", monto=100, fecha=date(2026, 11, 10))
        cls.pago = PagoManoObra.objects.create(proyecto=cls.obra, empleado=cls.empleado, trabajador="Ana", concepto="Jornal", monto=200, fecha=date(2026, 11, 10))

    def setUp(self):
        self.client.force_login(self.admin)

    def datos_obra(self, **cambios):
        datos = {
            "nombre": "Nueva obra completa", "cliente": self.cliente.pk, "tipo_obra": "REMODELACION",
            "direccion": "Avenida Central 123", "comuna": "Santiago", "region": "Metropolitana",
            "descripcion": "Remodelación de cocina", "responsable": "Luis Cáceres", "presupuesto_inicial": "50000",
            "fecha_inicio": "2026-11-18", "fecha_termino_estimada": "2026-12-18", "activo": "on",
            "observaciones": "Entregar con terminaciones incluidas",
        }
        datos.update(cambios)
        return datos

    def datos_egreso(self, tipo="material", **cambios):
        datos = {"proyecto_id": self.obra.pk, "monto": "350", "fecha": "2026-11-18"}
        if tipo == "material":
            datos.update(tipo_egreso="MATERIAL", proveedor="Nuevo proveedor", categoria="MADERA")
        else:
            datos.update(tipo_egreso="MANO_OBRA", empleado_id=self.otro_empleado.pk, trabajador="Pedro", concepto="Terminaciones")
        datos.update(cambios)
        return datos

    def ruta_egreso(self, accion, tipo="material"):
        return reverse("egreso_" + accion, args=[tipo, self.gasto.pk if tipo == "material" else self.pago.pk])

    def test_registrar_obra_completa_y_ver_ficha(self):
        respuesta = self.client.post(reverse("proyectos"), self.datos_obra())
        self.assertRedirects(respuesta, reverse("proyectos"))
        obra = Proyecto.objects.get(nombre="Nueva obra completa")
        self.assertEqual(obra.cliente, self.cliente)
        self.assertEqual(obra.fecha_termino_estimada, date(2026, 12, 18))
        ficha = self.client.get(reverse("proyecto_detalle", args=[obra.pk]))
        for dato in ("Cliente habitual", "Avenida Central 123", "Remodelación de cocina", "Santiago", "Metropolitana", "Luis Cáceres", "18/12/2026", "Entregar con terminaciones incluidas"):
            self.assertContains(ficha, dato)

    def test_datos_minimos_y_fechas_de_obra_se_validan(self):
        casos = [{campo: ""} for campo in ("cliente", "direccion", "fecha_termino_estimada")]
        casos += [{"cliente": "999999"}, {"fecha_termino_estimada": "2026-11-17"}, {"fecha_termino_estimada": "2026-02-30"}, {"tipo_obra": "INVALIDO"}]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(reverse("proyectos"), self.datos_obra(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(Proyecto.objects.count(), 3)

    def test_modelo_y_base_rechazan_termino_anterior_al_inicio(self):
        self.obra.fecha_termino_estimada = date(2026, 10, 31)
        with self.assertRaises(ValidationError):
            self.obra.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.obra.save()

    def test_completar_obra_anterior_y_cambiar_cliente_actualiza_historial(self):
        respuesta = self.client.post(reverse("proyecto_editar", args=[self.obra.pk]), self.datos_obra(nombre="Casa", cliente=self.otro_cliente.pk))
        self.assertRedirects(respuesta, reverse("proyecto_detalle", args=[self.obra.pk]))
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.cliente, self.otro_cliente)
        self.assertEqual(self.obra.direccion, "Avenida Central 123")
        self.assertEqual(self.cliente.proyectos.count(), 1)
        self.assertEqual(self.otro_cliente.proyectos.count(), 2)

    def test_registrar_y_editar_cliente_conserva_obras(self):
        datos = {"nombre": "Cliente nuevo", "rut": "11.111.111-1", "telefono": "+56 9 12345678", "email": "nuevo@example.com", "direccion": "Dirección de contacto", "notas": "Contacto por teléfono"}
        respuesta = self.client.post(reverse("clientes"), datos)
        cliente = Cliente.objects.get(nombre="Cliente nuevo")
        self.assertRedirects(respuesta, reverse("cliente_detalle", args=[cliente.pk]))
        self.assertEqual(cliente.rut, "11111111-1")
        datos.update(nombre="Cliente habitual actualizado", rut=self.cliente.rut)
        self.assertRedirects(self.client.post(reverse("cliente_editar", args=[self.cliente.pk]), datos), reverse("cliente_detalle", args=[self.cliente.pk]))
        self.assertEqual(self.cliente.proyectos.count(), 2)
        self.assertContains(self.client.get(reverse("proyecto_detalle", args=[self.obra.pk])), "Cliente habitual actualizado")

    def test_clientes_homonimos_sin_rut_y_rut_duplicado(self):
        for _ in range(2):
            self.assertEqual(self.client.post(reverse("clientes"), {"nombre": "Homónimo"}).status_code, 302)
        self.assertEqual(Cliente.objects.filter(nombre="Homónimo", rut__isnull=True).count(), 2)
        for rut in ("12.345.678-5", "123456785", "12345678-5"):
            respuesta = self.client.post(reverse("clientes"), {"nombre": "Duplicado", "rut": rut})
            self.assertIn("rut", respuesta.context["form"].errors)
        self.assertFalse(Cliente.objects.filter(nombre="Duplicado").exists())
        respuesta = self.client.post(reverse("clientes"), {"nombre": " ", "email": "incorrecto"})
        self.assertIn("nombre", respuesta.context["form"].errors)
        self.assertIn("email", respuesta.context["form"].errors)

    def test_historial_incluye_todas_las_obras_y_totales_sin_duplicarlos(self):
        GastoMaterial.objects.create(proyecto=self.otra_obra, proveedor="Proveedor", categoria="OTROS", monto=400, fecha=date.today())
        listado = self.client.get(reverse("clientes"))
        cliente = next(c for c in listado.context["clientes"] if c.pk == self.cliente.pk)
        self.assertEqual(cliente.cantidad_proyectos, 2)
        self.assertEqual(cliente.presupuesto_acumulado, 30000)
        respuesta = self.client.get(reverse("cliente_detalle", args=[self.cliente.pk]))
        self.assertEqual(respuesta.context["resumen"], {"presupuesto": 30000, "cantidad": 2, "activas": 1})
        self.assertEqual(respuesta.context["gastos"], 700)
        self.assertEqual(respuesta.context["saldo"], 29300)
        self.assertContains(respuesta, "Ampliación")
        self.assertContains(respuesta, "Casa")
        self.assertNotContains(respuesta, "Local de otro cliente")

    def test_cliente_sin_obras_y_busqueda(self):
        cliente = Cliente.objects.create(nombre="Sin obras")
        respuesta = self.client.get(reverse("cliente_detalle", args=[cliente.pk]))
        self.assertEqual(respuesta.context["resumen"]["cantidad"], 0)
        self.assertEqual(respuesta.context["saldo"], 0)
        self.assertContains(respuesta, "aún no tiene obras")
        for busqueda in ("habitual", "12345678", "cliente@example.com"):
            with self.subTest(busqueda=busqueda):
                respuesta = self.client.get(reverse("clientes"), {"q": busqueda})
                self.assertEqual([c.pk for c in respuesta.context["clientes"]], [self.cliente.pk])

    def test_nueva_obra_desde_cliente_trae_seleccion(self):
        respuesta = self.client.get(reverse("proyectos"), {"cliente": self.cliente.pk})
        self.assertEqual(str(respuesta.context["form"]["cliente"].value()), str(self.cliente.pk))

    def test_no_eliminar_cliente_con_obras_y_eliminar_obra_conserva_cliente(self):
        with self.assertRaises(ProtectedError):
            self.cliente.delete()
        self.client.post(reverse("proyecto_eliminar", args=[self.obra.pk]))
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())
        self.assertEqual(self.cliente.proyectos.count(), 1)

    def test_formularios_de_edicion_precargan_datos(self):
        for tipo, registro in (("material", self.gasto), ("mano-obra", self.pago)):
            with self.subTest(tipo=tipo):
                respuesta = self.client.get(self.ruta_egreso("editar", tipo))
                form = respuesta.context["form"]
                self.assertEqual(form["monto"].value(), registro.monto)
                self.assertEqual(form["fecha"].value(), registro.fecha)
                self.assertEqual(form["proyecto_id"].value(), registro.proyecto_id)
                self.assertTrue(form.fields["tipo_egreso"].disabled)
                self.assertContains(respuesta, "Guardar cambios")

    def test_editar_material_cambia_datos_y_recalcula_ambas_obras(self):
        respuesta = self.client.post(self.ruta_egreso("editar"), self.datos_egreso(proyecto_id=self.obra_ajena.pk))
        self.assertRedirects(respuesta, reverse("finanzas"))
        self.gasto.refresh_from_db()
        self.assertEqual((self.gasto.proveedor, self.gasto.categoria, self.gasto.fecha, self.gasto.monto), ("Nuevo proveedor", "MADERA", date(2026, 11, 18), 350))
        self.assertEqual(self.obra.total_materiales, 0)
        self.assertEqual(self.obra_ajena.total_materiales, 350)
        self.assertEqual(self.obra.saldo_disponible, 9800)
        self.assertEqual(GastoMaterial.objects.count(), 1)

    def test_editar_pago_actualiza_cuenta_y_portales(self):
        respuesta = self.client.post(self.ruta_egreso("editar", "mano-obra"), self.datos_egreso("mano-obra"))
        self.assertRedirects(respuesta, reverse("finanzas"))
        self.pago.refresh_from_db()
        self.assertEqual((self.pago.empleado_id, self.pago.trabajador, self.pago.concepto, self.pago.monto), (self.otro_empleado.pk, "Pedro", "Terminaciones", 350))
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("portal_empleado")).context["total_ganado"], 0)
        self.client.force_login(self.otro_empleado)
        respuesta = self.client.get(reverse("portal_empleado"))
        self.assertEqual(respuesta.context["total_ganado"], 350)
        self.assertContains(respuesta, "Terminaciones")
        self.assertEqual(self.obra.saldo_disponible, 9550)

    def test_editar_pago_permite_quitar_vinculo_con_cuenta(self):
        respuesta = self.client.post(self.ruta_egreso("editar", "mano-obra"), self.datos_egreso("mano-obra", empleado_id="", trabajador="Externo"))
        self.assertRedirects(respuesta, reverse("finanzas"))
        self.pago.refresh_from_db()
        self.assertIsNone(self.pago.empleado_id)
        self.assertEqual(self.pago.trabajador, "Externo")

    def test_correccion_conserva_obra_y_empleado_inactivos(self):
        self.pago.proyecto = self.otra_obra
        self.pago.save()
        self.empleado.is_active = False
        self.empleado.save()
        respuesta = self.client.post(self.ruta_egreso("editar", "mano-obra"), self.datos_egreso("mano-obra", proyecto_id=self.otra_obra.pk, empleado_id=self.empleado.pk))
        self.assertRedirects(respuesta, reverse("finanzas"))
        self.pago.refresh_from_db()
        self.assertEqual((self.pago.proyecto_id, self.pago.empleado_id), (self.otra_obra.pk, self.empleado.pk))

    def test_errores_al_editar_no_modifican_registros(self):
        for tipo, registro in (("material", self.gasto), ("mano-obra", self.pago)):
            casos = [{"monto": valor} for valor in ("0", "-1", "texto", "2147483648")]
            casos += [{"fecha": "2026-02-30"}, {"proyecto_id": self.otra_obra.pk}, {"proyecto_id": "999999"}]
            casos += [{"proveedor": "", "categoria": ""}] if tipo == "material" else [{"empleado_id": "", "trabajador": ""}, {"empleado_id": self.admin.pk}]
            for cambios in casos:
                with self.subTest(tipo=tipo, cambios=cambios):
                    respuesta = self.client.post(self.ruta_egreso("editar", tipo), self.datos_egreso(tipo, **cambios))
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertTrue(respuesta.context["form"].errors)
                    registro.refresh_from_db()
                    self.assertEqual(registro.monto, 100 if tipo == "material" else 200)
                    self.assertEqual(registro.proyecto_id, self.obra.pk)

    def test_tipo_manipulado_no_convierte_un_registro_en_otro(self):
        respuesta = self.client.post(self.ruta_egreso("editar"), self.datos_egreso(tipo_egreso="MANO_OBRA"))
        self.assertRedirects(respuesta, reverse("finanzas"))
        self.assertEqual(GastoMaterial.objects.count(), 1)
        self.assertEqual(PagoManoObra.objects.count(), 1)
        self.pago.refresh_from_db()
        self.assertEqual(self.pago.monto, 200)

    def test_fallo_de_base_al_editar_muestra_error_y_conserva_datos(self):
        with patch("construApp.forms.GastoMaterial.save", side_effect=DatabaseError("detalle interno")):
            respuesta = self.client.post(self.ruta_egreso("editar"), self.datos_egreso())
        self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertNotContains(respuesta, "detalle interno")
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.monto, 100)

    def test_eliminar_egreso_requiere_confirmacion_y_recalcula_totales(self):
        for tipo, modelo, registro in (("material", GastoMaterial, self.gasto), ("mano-obra", PagoManoObra, self.pago)):
            with self.subTest(tipo=tipo):
                ruta = self.ruta_egreso("eliminar", tipo)
                self.assertContains(self.client.get(ruta), "Confirmar eliminación")
                self.assertTrue(modelo.objects.filter(pk=registro.pk).exists())
                self.assertRedirects(self.client.post(ruta), reverse("finanzas"))
                self.assertFalse(modelo.objects.filter(pk=registro.pk).exists())
                self.assertRedirects(self.client.post(ruta), reverse("finanzas"))
        self.assertEqual(self.obra.saldo_disponible, 10000)
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("portal_empleado")).context["total_ganado"], 0)

    def test_permisos_clientes_y_egresos_en_servidor_y_pantalla(self):
        rutas_escritura = [reverse("clientes"), reverse("cliente_editar", args=[self.cliente.pk])]
        rutas_escritura += [self.ruta_egreso(accion, tipo) for accion in ("editar", "eliminar") for tipo in ("material", "mano-obra")]
        for usuario in (self.lector, self.empleado):
            self.client.force_login(usuario)
            for ruta in rutas_escritura:
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    self.assertEqual(self.client.post(ruta, {}).status_code, 403)
                    if ruta != reverse("clientes"):
                        self.assertEqual(self.client.get(ruta).status_code, 403)
        self.client.force_login(self.lector)
        self.assertContains(self.client.get(reverse("clientes")), "Cliente habitual")
        self.assertNotContains(self.client.get(reverse("clientes")), "Guardar cliente")
        self.assertEqual(self.client.get(reverse("cliente_detalle", args=[self.cliente.pk])).status_code, 200)
        self.assertNotContains(self.client.get(reverse("finanzas")), self.ruta_egreso("editar"))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("finanzas")), self.ruta_egreso("editar"))
        self.client.force_login(self.empleado)
        for ruta in (reverse("clientes"), reverse("cliente_detalle", args=[self.cliente.pk])):
            self.assertEqual(self.client.get(ruta).status_code, 403)
        self.assertNotContains(self.client.get(reverse("portal_empleado")), "Clientes e historial")

    def test_rutas_nuevas_exigen_sesion_csrf_y_metodos_admitidos(self):
        cliente = Client(enforce_csrf_checks=True)
        rutas = [reverse("clientes"), reverse("cliente_editar", args=[self.cliente.pk])]
        rutas += [self.ruta_egreso(accion, tipo) for accion in ("editar", "eliminar") for tipo in ("material", "mano-obra")]
        for ruta in rutas:
            self.assertEqual(cliente.get(ruta).status_code, 302)
        cliente.force_login(self.admin)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(cliente.post(ruta, {}).status_code, 403)
                for metodo in (self.client.put, self.client.patch, self.client.delete):
                    self.assertEqual(metodo(ruta).status_code, 405)
        ruta = self.ruta_egreso("eliminar")
        cliente.get(ruta)
        self.assertRedirects(cliente.post(ruta, {"csrfmiddlewaretoken": cliente.cookies["csrftoken"].value}), reverse("finanzas"))

    def test_ids_y_tipos_inexistentes(self):
        for nombre in ("cliente_detalle", "cliente_editar"):
            self.assertEqual(self.client.get(reverse(nombre, args=[999999])).status_code, 404)
        for accion in ("editar", "eliminar"):
            self.assertEqual(self.client.get(reverse("egreso_" + accion, args=["invalido", self.gasto.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("egreso_editar", args=["material", 999999])).status_code, 404)
        self.assertRedirects(self.client.get(reverse("egreso_eliminar", args=["material", 999999])), reverse("finanzas"))

    def test_contenido_de_clientes_se_escapa(self):
        ataque = '<script>alert("cliente")</script>'
        self.cliente.nombre = ataque
        self.cliente.notas = ataque
        self.cliente.save()
        for ruta in (reverse("clientes"), reverse("cliente_detalle", args=[self.cliente.pk]), reverse("cliente_editar", args=[self.cliente.pk])):
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertNotContains(respuesta, ataque)
                self.assertContains(respuesta, "&lt;script&gt;")


class MigracionClientesTests(TransactionTestCase):
    anterior = ("construApp", "0004_proteger_tablas_supabase")
    nueva = ("construApp", "0005_clientes_y_ficha_obra")

    def test_actualizacion_conserva_obras_y_egresos_anteriores(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.anterior])
        try:
            anteriores = executor.loader.project_state([self.anterior]).apps
            obra = anteriores.get_model("construApp", "Proyecto").objects.create(nombre="Obra heredada", presupuesto_inicial=1000, fecha_inicio=date(2026, 1, 1))
            anteriores.get_model("construApp", "GastoMaterial").objects.create(proyecto_id=obra.pk, proveedor="Proveedor anterior", categoria="OTROS", monto=100, fecha=date(2026, 1, 2))
            anteriores.get_model("construApp", "PagoManoObra").objects.create(proyecto_id=obra.pk, trabajador="Trabajador anterior", monto=200, fecha=date(2026, 1, 2))
            executor = MigrationExecutor(connection)
            executor.migrate([self.nueva])
            actuales = executor.loader.project_state([self.nueva]).apps
            migrada = actuales.get_model("construApp", "Proyecto").objects.get(pk=obra.pk)
            self.assertIsNone(migrada.cliente_id)
            self.assertIsNone(migrada.fecha_termino_estimada)
            self.assertEqual(migrada.direccion, "")
            self.assertEqual(actuales.get_model("construApp", "GastoMaterial").objects.get(proyecto_id=obra.pk).monto, 100)
            self.assertEqual(actuales.get_model("construApp", "PagoManoObra").objects.get(proyecto_id=obra.pk).monto, 200)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_tabla_clientes_recibe_proteccion_de_api_en_postgresql(self):
        migracion = import_module("construApp.migrations.0005_clientes_y_ficha_obra")
        editor = MagicMock()
        editor.connection.vendor = "postgresql"
        editor.connection.ops.quote_name.side_effect = lambda nombre: '"' + nombre + '"'
        cursor = editor.connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [("anon",), ("authenticated",)]
        apps = MagicMock()
        apps.get_model.return_value = Cliente
        migracion.proteger_tabla_clientes(apps, editor)
        sentencias = [llamada.args[0] for llamada in cursor.execute.call_args_list]
        self.assertIn('ALTER TABLE "construApp_cliente" ENABLE ROW LEVEL SECURITY', sentencias)
        self.assertIn('REVOKE ALL PRIVILEGES ON TABLE "construApp_cliente" FROM PUBLIC, "anon", "authenticated"', sentencias)
