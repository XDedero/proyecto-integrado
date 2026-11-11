"""Regresiones funcionales y de seguridad; solo usan la base temporal de tests."""

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError, IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from .models import GastoMaterial, HitoCalendario, PagoManoObra, Proyecto


class AuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("auditor_admin", password="PruebaAudit!782", is_staff=True)
        cls.empleado = User.objects.create_user("auditor_empleado", password="PruebaAudit!782", first_name="Ana")
        cls.lector = User.objects.create_user("auditor_lector", password="PruebaAudit!782")
        cls.lector.perfil.rol = "VISUALIZADOR"
        cls.lector.perfil.save()
        cls.proyecto = Proyecto.objects.create(nombre="Obra auditada", presupuesto_inicial=10000, fecha_inicio=date.today())
        cls.empleado.perfil.obra_asignada = cls.proyecto
        cls.empleado.perfil.save()
        cls.inactivo = Proyecto.objects.create(nombre="Obra cerrada", presupuesto_inicial=20000, fecha_inicio=date.today(), activo=False)

    def egreso(self, **cambios):
        datos = {"tipo_egreso": "MATERIAL", "proyecto_id": str(self.proyecto.pk), "monto": "100", "fecha": "2026-11-11", "proveedor": "Proveedor", "categoria": "OTROS"}
        datos.update(cambios)
        return datos

    def test_health_confirma_conexion_y_revision_sin_exigir_sesion(self):
        with patch.dict("os.environ", {"RENDER_GIT_COMMIT": "revision-de-prueba"}):
            respuesta = self.client.get(reverse("health"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"status": "ok", "database": "ok", "revision": "revision-de-prueba"})
        self.assertEqual(self.client.head(reverse("health")).status_code, 200)
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)

    def test_health_responde_503_sin_exponer_error_de_base(self):
        with patch("construApp.views.connection.cursor", side_effect=DatabaseError("detalle privado")):
            respuesta = self.client.get(reverse("health"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json(), {"status": "error", "database": "unavailable"})
        self.assertNotContains(respuesta, "detalle privado", status_code=503)

    def hito(self, **cambios):
        datos = {"proyecto_id": str(self.proyecto.pk), "nombre": "Entrega", "fecha": "2026-11-30"}
        datos.update(cambios)
        return datos

    def test_finanzas_rechaza_entradas_invalidas_sin_excepciones(self):
        self.client.force_login(self.admin)
        casos = [{"monto": valor} for valor in ("texto", "", "0", "-1", "1.5", "2147483648", "9" * 100)]
        casos += [{"fecha": valor} for valor in ("", "2026-02-30", "texto")]
        casos += [{"proyecto_id": valor} for valor in ("", "abc", "999999", "1 OR 1=1", str(self.inactivo.pk))]
        casos += [{"proveedor": " "}, {"proveedor": "x" * 101}, {"categoria": "INVALIDA"}, {"tipo_egreso": "INVALIDO"}]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(reverse("finanzas"), self.egreso(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
                self.assertEqual(GastoMaterial.objects.count(), 0)
                self.assertEqual(PagoManoObra.objects.count(), 0)

    def test_calendario_rechaza_entradas_invalidas_sin_excepciones(self):
        self.client.force_login(self.admin)
        casos = [{"fecha": valor} for valor in ("", "2026-02-30", "texto")]
        casos += [{"proyecto_id": valor} for valor in ("", "abc", "999999", "1 OR 1=1", str(self.inactivo.pk))]
        casos += [{"nombre": " "}, {"nombre": "x" * 121}]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(reverse("calendario"), self.hito(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
                self.assertEqual(HitoCalendario.objects.count(), 0)

    def test_pago_rechaza_cuentas_invalidas_y_datos_incompletos(self):
        self.client.force_login(self.admin)
        casos = [{"empleado_id": valor} for valor in ("abc", "999999", str(self.admin.pk), str(self.lector.pk))]
        casos += [{"trabajador": "", "empleado_id": ""}, {"trabajador": "x" * 101}, {"concepto": "x" * 121}]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                datos = self.egreso(tipo_egreso="MANO_OBRA", trabajador="Trabajador", concepto="Jornal")
                datos.update(cambios)
                respuesta = self.client.post(reverse("finanzas"), datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
                self.assertEqual(PagoManoObra.objects.count(), 0)

    def test_registro_gasto_pago_y_hito_actualiza_saldos_y_portal(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse("finanzas"), self.egreso()), reverse("finanzas"))
        datos = self.egreso(tipo_egreso="MANO_OBRA", empleado_id=self.empleado.pk, concepto="Jornal auditado", monto="200")
        self.assertRedirects(self.client.post(reverse("finanzas"), datos), reverse("finanzas"))
        self.assertRedirects(self.client.post(reverse("calendario"), self.hito()), reverse("calendario"))
        self.assertEqual(self.proyecto.total_materiales, 100)
        self.assertEqual(self.proyecto.total_mano_obra, 200)
        self.assertEqual(self.proyecto.saldo_disponible, 9700)
        self.client.force_login(self.empleado)
        respuesta = self.client.get(reverse("portal_empleado"))
        self.assertEqual(respuesta.context["total_ganado"], 200)
        self.assertContains(respuesta, "Jornal auditado")
        self.assertContains(respuesta, "Entrega")

    def test_presupuesto_no_desborda_entero_de_postgresql(self):
        self.client.force_login(self.admin)
        datos = {"nombre": "Fuera de rango", "presupuesto_inicial": "2147483648", "fecha_inicio": "2026-11-11", "activo": "on"}
        respuesta = self.client.post(reverse("proyectos"), datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(Proyecto.objects.filter(nombre="Fuera de rango").exists())

    def test_eliminacion_en_cascada_conserva_cuentas(self):
        GastoMaterial.objects.create(proyecto=self.proyecto, fecha=date.today(), proveedor="Prov", categoria="OTROS", monto=10)
        PagoManoObra.objects.create(proyecto=self.proyecto, empleado=self.empleado, trabajador="Ana", fecha=date.today(), monto=20)
        HitoCalendario.objects.create(proyecto=self.proyecto, nombre="Hito", fecha=date.today())
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse("proyecto_eliminar", args=[self.proyecto.pk])), reverse("proyectos"))
        self.assertEqual(GastoMaterial.objects.count(), 0)
        self.assertEqual(PagoManoObra.objects.count(), 0)
        self.assertEqual(HitoCalendario.objects.count(), 0)
        self.empleado.perfil.refresh_from_db()
        self.assertIsNone(self.empleado.perfil.obra_asignada_id)
        self.assertTrue(User.objects.filter(pk=self.empleado.pk).exists())

    def test_login_redirige_cada_rol_y_logout_invalida_sesion(self):
        for usuario, destino in ((self.admin, "inicio"), (self.lector, "inicio"), (self.empleado, "portal_empleado")):
            with self.subTest(usuario=usuario.username):
                cliente = Client()
                respuesta = cliente.post(reverse("login"), {"username": usuario.username, "password": "PruebaAudit!782"})
                self.assertRedirects(respuesta, reverse(destino))
                self.assertIn("_auth_user_id", cliente.session)
                self.assertRedirects(cliente.post(reverse("logout")), reverse("login"))
                self.assertNotIn("_auth_user_id", cliente.session)

    def test_login_incorrecto_no_revela_si_existe_usuario(self):
        cuerpos = []
        for usuario in (self.admin.username, "inexistente", "' OR 1=1 --"):
            cliente = Client()
            respuesta = cliente.post(reverse("login"), {"username": usuario, "password": "Incorrecta!788"})
            self.assertContains(respuesta, "Credenciales incorrectas.")
            self.assertNotIn("_auth_user_id", cliente.session)
            cuerpos.append(respuesta.status_code)
        self.assertEqual(cuerpos, [200, 200, 200])

    def test_desactivar_cuenta_invalida_sesion_existente(self):
        self.client.force_login(self.empleado)
        self.empleado.is_active = False
        self.empleado.save()
        self.assertEqual(self.client.get(reverse("proyectos")).status_code, 302)

    def test_csrf_todas_las_mutaciones_incluido_login_finanzas_y_calendario(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post(reverse("login"), {}).status_code, 403)
        cliente.force_login(self.admin)
        rutas = [reverse("finanzas"), reverse("calendario"), reverse("proyecto_editar", args=[self.proyecto.pk]), reverse("usuario_editar", args=[self.empleado.pk])]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(cliente.post(ruta, {}).status_code, 403)

    def test_csrf_con_token_valido_permite_gasto_y_rechaza_origen_ajeno(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        cliente.get(reverse("finanzas"))
        token = cliente.cookies["csrftoken"].value
        self.assertEqual(cliente.post(reverse("finanzas"), self.egreso(csrfmiddlewaretoken=token), HTTP_ORIGIN="https://ajeno.invalid").status_code, 403)
        respuesta = cliente.post(reverse("finanzas"), self.egreso(csrfmiddlewaretoken=token))
        self.assertRedirects(respuesta, reverse("finanzas"))

    def test_xss_persistente_se_escapa_en_pantallas_y_avisos(self):
        ataque = '<script>alert("audit")</script>'
        self.proyecto.nombre = ataque
        self.proyecto.save()
        self.client.force_login(self.admin)
        for ruta in (reverse("proyectos"), reverse("proyecto_detalle", args=[self.proyecto.pk]), reverse("proyecto_eliminar", args=[self.proyecto.pk])):
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertNotContains(respuesta, ataque)
                self.assertContains(respuesta, "&lt;script&gt;")
        respuesta = self.client.post(reverse("proyecto_eliminar", args=[self.proyecto.pk]), follow=True)
        self.assertNotContains(respuesta, ataque)

    def test_lector_y_empleado_no_escalan_privilegios_con_campos_extra(self):
        for usuario in (self.lector, self.empleado):
            self.client.force_login(usuario)
            respuesta = self.client.post(reverse("usuario_editar", args=[usuario.pk]), {"rol": "ADMIN", "is_staff": "on", "is_superuser": "on"})
            self.assertEqual(respuesta.status_code, 403)
            usuario.refresh_from_db()
            self.assertFalse(usuario.is_superuser)
            self.assertFalse(usuario.is_staff)

    def test_portal_empleado_no_filtra_hitos_ni_presupuesto_ajenos(self):
        HitoCalendario.objects.create(proyecto=self.inactivo, nombre="Hito confidencial ajeno", fecha=date.today())
        self.client.force_login(self.empleado)
        for nombre in ("inicio", "finanzas", "calendario"):
            self.assertRedirects(self.client.get(reverse(nombre)), reverse("portal_empleado"))
        respuesta = self.client.get(reverse("proyecto_detalle", args=[self.proyecto.pk]))
        self.assertNotContains(respuesta, "Presupuesto inicial (CLP)")
        self.assertNotContains(self.client.get(reverse("portal_empleado")), "Hito confidencial ajeno")

    def test_metodos_http_no_admitidos_no_mutan_datos(self):
        self.client.force_login(self.admin)
        for nombre in ("login", "inicio", "portal_empleado", "finanzas", "calendario", "proyectos"):
            for metodo in (self.client.put, self.client.patch, self.client.delete, self.client.trace):
                with self.subTest(nombre=nombre, metodo=metodo.__name__):
                    self.assertEqual(metodo(reverse(nombre)).status_code, 405)

    def test_cabeceras_anti_clickjacking_y_sniffing(self):
        respuesta = self.client.get(reverse("login"))
        self.assertEqual(respuesta["X-Frame-Options"], "DENY")
        self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(respuesta["Referrer-Policy"], "same-origin")

    def test_paginas_privadas_y_login_no_se_guardan_en_cache(self):
        self.assertIn("no-store", self.client.get(reverse("login"))["Cache-Control"])
        self.client.force_login(self.admin)
        for nombre in ("inicio", "finanzas", "calendario", "proyectos", "registro_usuario"):
            with self.subTest(nombre=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertIn("no-store", respuesta["Cache-Control"])
                self.assertIn("private", respuesta["Cache-Control"])

    def test_errores_de_formulario_se_muestran_y_conservan_datos(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("finanzas"), self.egreso(monto="texto", proveedor="Proveedor conservado"))
        self.assertContains(respuesta, "Revise los datos antes de guardar:")
        self.assertContains(respuesta, 'value="Proveedor conservado"')
        respuesta = self.client.post(reverse("calendario"), self.hito(fecha="incorrecta", nombre="Hito conservado"))
        self.assertContains(respuesta, 'value="Hito conservado"')
        self.assertContains(respuesta, 'role="alert"')

    def test_pago_sin_cuenta_es_valido_y_no_se_asigna_por_nombre(self):
        self.client.force_login(self.admin)
        datos = self.egreso(tipo_egreso="MANO_OBRA", trabajador="Ana", concepto="")
        self.assertRedirects(self.client.post(reverse("finanzas"), datos), reverse("finanzas"))
        pago = PagoManoObra.objects.get()
        self.assertIsNone(pago.empleado_id)
        self.assertEqual(pago.concepto, "Jornal / Avance de Obra")
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("portal_empleado")).context["total_ganado"], 0)

    def test_pago_no_admite_empleado_desactivado(self):
        self.empleado.is_active = False
        self.empleado.save()
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("finanzas"), self.egreso(tipo_egreso="MANO_OBRA", empleado_id=self.empleado.pk))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("empleado_id", respuesta.context["form"].errors)
        self.assertEqual(PagoManoObra.objects.count(), 0)

    def test_fallo_de_integridad_en_egreso_o_hito_no_devuelve_500(self):
        self.client.force_login(self.admin)
        for modelo, ruta, datos in (("GastoMaterial", "finanzas", self.egreso()), ("HitoCalendario", "calendario", self.hito())):
            with self.subTest(modelo=modelo):
                with patch("construApp.views." + modelo + ".objects.create", side_effect=IntegrityError("fallo simulado")):
                    respuesta = self.client.post(reverse(ruta), datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertEqual(GastoMaterial.objects.count(), 0)
        self.assertEqual(HitoCalendario.objects.count(), 0)

    def test_sesion_robada_se_invalida_al_cambiar_password(self):
        cliente_viejo = Client()
        cliente_viejo.force_login(self.empleado)
        self.empleado.set_password("OtraClaveAudit!899")
        self.empleado.save()
        self.assertEqual(cliente_viejo.get(reverse("proyectos")).status_code, 302)

    def test_id_inexistente_no_revela_detalles_del_servidor(self):
        self.client.force_login(self.admin)
        with self.settings(DEBUG=False):
            for nombre in ("proyecto_detalle", "proyecto_editar", "usuario_detalle", "usuario_editar"):
                with self.subTest(nombre=nombre):
                    respuesta = self.client.get(reverse(nombre, args=[9999999]))
                    self.assertEqual(respuesta.status_code, 404)
                    self.assertNotContains(respuesta, "Traceback", status_code=404)

    def test_admin_django_no_accesible_a_roles_de_lectura(self):
        for usuario in (self.lector, self.empleado):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_alertas_calendario_y_totales_sin_gastos(self):
        self.assertEqual(self.proyecto.gasto_total, 0)
        self.assertEqual(self.proyecto.saldo_disponible, 10000)
        for dias, color in ((-1, "rojo"), (0, "rojo"), (2, "rojo"), (3, "amarillo"), (6, "amarillo"), (7, "verde")):
            with self.subTest(dias=dias):
                hito = HitoCalendario(proyecto=self.proyecto, nombre="Plazo", fecha=date.today() + timedelta(days=dias))
                self.assertEqual(hito.color_alerta, color)
