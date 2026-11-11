from datetime import date
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from .models import GastoMaterial, HitoCalendario, PagoManoObra, PerfilUsuario, Proyecto
from .permisos import obtener_rol_usuario


class GestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin", password="PruebaGestion!72", is_staff=True)
        cls.visualizador = User.objects.create_user("contador", password="PruebaGestion!72")
        cls.visualizador.perfil.rol = "VISUALIZADOR"
        cls.visualizador.perfil.save()
        cls.empleado = User.objects.create_user("empleado", first_name="Pedro", password="PruebaGestion!72")
        cls.otro_empleado = User.objects.create_user("otro", first_name="Pedro", password="PruebaGestion!72")
        cls.superusuario = User.objects.create_superuser("superadmin", password="PruebaGestion!72")
        cls.proyecto = Proyecto.objects.create(nombre="Obra asignada", presupuesto_inicial=1000000, fecha_inicio=date(2026, 11, 1))
        cls.otro_proyecto = Proyecto.objects.create(nombre="Obra reservada", presupuesto_inicial=2000000, fecha_inicio=date(2026, 11, 2))
        cls.empleado.perfil.obra_asignada = cls.proyecto
        cls.empleado.perfil.save()

    def datos_usuario(self, **cambios):
        datos = {
            "username": "nueva_cuenta", "first_name": "Camila", "last_name": "Pérez",
            "email": "camila@example.com", "is_active": "on", "rol": "EMPLEADO",
            "especialidad": "Carpintería", "obra_asignada": str(self.proyecto.pk),
            "password": "CuentaSegura!79", "password_confirm": "CuentaSegura!79",
        }
        datos.update(cambios)
        return datos

    def datos_proyecto(self, **cambios):
        datos = {"nombre": "Obra nueva", "presupuesto_inicial": "45000000", "fecha_inicio": "2026-11-09", "activo": "on"}
        datos.update(cambios)
        return datos

    def test_usuarios_y_superusuarios_reciben_perfil(self):
        self.assertEqual(self.admin.perfil.rol, "ADMIN")
        self.assertEqual(self.superusuario.perfil.rol, "ADMIN")
        self.assertEqual(self.empleado.perfil.rol, "EMPLEADO")

    def test_superusuario_tiene_prioridad_sobre_perfil(self):
        self.superusuario.perfil.rol = "EMPLEADO"
        self.superusuario.perfil.save()
        self.assertEqual(obtener_rol_usuario(self.superusuario), "ADMIN")

    def test_usuario_sin_perfil_no_recibe_lectura_global(self):
        self.empleado.perfil.delete()
        usuario = User.objects.get(pk=self.empleado.pk)
        self.assertEqual(obtener_rol_usuario(usuario), "EMPLEADO")
        self.assertIsNone(obtener_rol_usuario(AnonymousUser()))

    def test_perfil_prevalece_sobre_bandera_staff(self):
        self.visualizador.is_staff = True
        self.visualizador.save()
        self.client.force_login(self.visualizador)
        self.assertEqual(self.client.get(reverse("registro_usuario")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("proyectos")), "Usuarios y personal")

    def test_rutas_privadas_requieren_sesion(self):
        rutas = [reverse("proyectos"), reverse("registro_usuario"), reverse("proyecto_detalle", args=[self.proyecto.pk]), reverse("usuario_editar", args=[self.empleado.pk])]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 302)

    def test_admin_crea_proyecto(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("proyectos"), self.datos_proyecto())
        self.assertRedirects(respuesta, reverse("proyectos"))
        self.assertTrue(Proyecto.objects.filter(nombre="Obra nueva", activo=True).exists())

    def test_proyectos_invalidos_no_se_guardan(self):
        self.client.force_login(self.admin)
        for cambios in ({"nombre": " "}, {"presupuesto_inicial": "texto"}, {"presupuesto_inicial": "0"}, {"presupuesto_inicial": "-1"}, {"fecha_inicio": "2026-02-30"}, {"nombre": "OBRA ASIGNADA"}):
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(reverse("proyectos"), self.datos_proyecto(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(Proyecto.objects.count(), 2)

    def test_admin_edita_y_desactiva_proyecto(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("proyecto_editar", args=[self.proyecto.pk]), self.datos_proyecto(nombre="Obra actualizada", activo=""))
        self.assertRedirects(respuesta, reverse("proyecto_detalle", args=[self.proyecto.pk]))
        self.proyecto.refresh_from_db()
        self.assertEqual(self.proyecto.nombre, "Obra actualizada")
        self.assertFalse(self.proyecto.activo)

    def test_editar_proyecto_conserva_nombre_sin_falso_duplicado(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("proyecto_editar", args=[self.proyecto.pk]), self.datos_proyecto(nombre=self.proyecto.nombre))
        self.assertEqual(respuesta.status_code, 302)

    def test_eliminar_proyecto_requiere_post_y_desasigna_personal(self):
        self.client.force_login(self.admin)
        gasto = GastoMaterial.objects.create(proyecto=self.proyecto, fecha=date.today(), proveedor="Proveedor", categoria="OTROS", monto=100)
        url = reverse("proyecto_eliminar", args=[self.proyecto.pk])
        self.assertContains(self.client.get(url), "Confirmar eliminación")
        self.assertTrue(Proyecto.objects.filter(pk=self.proyecto.pk).exists())
        self.assertRedirects(self.client.post(url), reverse("proyectos"))
        self.assertFalse(Proyecto.objects.filter(pk=self.proyecto.pk).exists())
        self.assertFalse(GastoMaterial.objects.filter(pk=gasto.pk).exists())
        self.empleado.perfil.refresh_from_db()
        self.assertIsNone(self.empleado.perfil.obra_asignada)

    def test_eliminar_proyecto_inexistente_vuelve_al_listado_con_aviso(self):
        self.client.force_login(self.admin)
        url = reverse("proyecto_eliminar", args=[9999999])
        with self.settings(DEBUG=False):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(metodo=metodo.__name__):
                    respuesta = metodo(url, follow=True)
                    self.assertRedirects(respuesta, reverse("proyectos"))
                    self.assertContains(respuesta, "El proyecto no existe o ya fue eliminado.")
        self.assertEqual(Proyecto.objects.count(), 2)

    def test_repetir_eliminacion_no_devuelve_404_ni_borra_otro_proyecto(self):
        self.client.force_login(self.admin)
        url = reverse("proyecto_eliminar", args=[self.proyecto.pk])
        self.assertRedirects(self.client.post(url), reverse("proyectos"))
        for metodo in (self.client.get, self.client.post):
            with self.subTest(metodo=metodo.__name__):
                self.assertRedirects(metodo(url), reverse("proyectos"))
        self.assertTrue(Proyecto.objects.filter(pk=self.otro_proyecto.pk).exists())

    def test_eliminar_proyecto_inexistente_conserva_control_de_acceso(self):
        url = reverse("proyecto_eliminar", args=[9999999])
        self.assertRedirects(self.client.get(url), reverse("login") + "?next=" + url)
        for usuario in (self.visualizador, self.empleado):
            self.client.force_login(usuario)
            for metodo in (self.client.get, self.client.post):
                with self.subTest(usuario=usuario.username, metodo=metodo.__name__):
                    self.assertEqual(metodo(url).status_code, 403)

    def test_visualizador_ve_proyectos_sin_acciones_de_escritura(self):
        self.client.force_login(self.visualizador)
        respuesta = self.client.get(reverse("proyectos"))
        self.assertContains(respuesta, self.proyecto.nombre)
        self.assertContains(respuesta, self.otro_proyecto.nombre)
        self.assertNotContains(respuesta, "Guardar proyecto")
        self.assertNotContains(respuesta, reverse("proyecto_editar", args=[self.proyecto.pk]))
        self.assertEqual(self.client.get(reverse("proyecto_detalle", args=[self.otro_proyecto.pk])).status_code, 200)

    def test_empleado_solo_ve_proyecto_asignado(self):
        self.client.force_login(self.empleado)
        respuesta = self.client.get(reverse("proyectos"))
        self.assertContains(respuesta, self.proyecto.nombre)
        self.assertNotContains(respuesta, self.otro_proyecto.nombre)
        self.assertNotContains(respuesta, "Presupuesto (CLP)")
        self.assertEqual(self.client.get(reverse("proyecto_detalle", args=[self.proyecto.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("proyecto_detalle", args=[self.otro_proyecto.pk])).status_code, 404)

    def test_empleado_sin_asignacion_no_ve_obras_ni_hitos_ajenos(self):
        HitoCalendario.objects.create(proyecto=self.otro_proyecto, nombre="Hito privado", fecha=date.today())
        self.client.force_login(self.otro_empleado)
        respuesta = self.client.get(reverse("proyectos"))
        self.assertNotContains(respuesta, self.proyecto.nombre)
        self.assertNotContains(respuesta, self.otro_proyecto.nombre)
        self.assertNotContains(self.client.get(reverse("portal_empleado")), "Hito privado")

    def test_roles_lectura_no_pueden_mutar_proyectos_por_url(self):
        rutas = [reverse("proyectos"), reverse("proyecto_editar", args=[self.proyecto.pk]), reverse("proyecto_eliminar", args=[self.proyecto.pk]), reverse("finanzas"), reverse("calendario")]
        for usuario in (self.visualizador, self.empleado):
            self.client.force_login(usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    self.assertEqual(self.client.post(ruta, self.datos_proyecto()).status_code, 403)
            self.assertEqual(self.client.get(reverse("proyecto_editar", args=[self.proyecto.pk])).status_code, 403)
        self.assertEqual(Proyecto.objects.count(), 2)

    def test_admin_crea_usuario_perfil_y_password_con_hash(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("registro_usuario"), self.datos_usuario())
        self.assertRedirects(respuesta, reverse("registro_usuario"))
        usuario = User.objects.get(username="nueva_cuenta")
        self.assertTrue(usuario.check_password("CuentaSegura!79"))
        self.assertNotEqual(usuario.password, "CuentaSegura!79")
        self.assertEqual(usuario.perfil.rol, "EMPLEADO")
        self.assertEqual(usuario.perfil.obra_asignada, self.proyecto)
        self.assertFalse(usuario.is_staff)
        self.assertIsNotNone(authenticate(username=usuario.username, password="CuentaSegura!79"))

    def test_usuario_y_perfil_se_guardan_atomicamente(self):
        self.client.force_login(self.admin)
        with patch("construApp.forms.PerfilUsuario.objects.update_or_create", side_effect=IntegrityError("fallo simulado")):
            respuesta = self.client.post(reverse("registro_usuario"), self.datos_usuario())
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.filter(username="nueva_cuenta").exists())
        self.assertEqual(PerfilUsuario.objects.count(), User.objects.count())

    def test_crear_cada_rol_sin_permitir_superusuario_por_post(self):
        self.client.force_login(self.admin)
        for rol in ("ADMIN", "VISUALIZADOR", "EMPLEADO"):
            with self.subTest(rol=rol):
                datos = self.datos_usuario(username="cuenta_" + rol.lower(), rol=rol, is_superuser="on")
                self.assertEqual(self.client.post(reverse("registro_usuario"), datos).status_code, 302)
                usuario = User.objects.get(username=datos["username"])
                self.assertEqual(usuario.perfil.rol, rol)
                self.assertEqual(usuario.is_staff, rol == "ADMIN")
                self.assertFalse(usuario.is_superuser)
                if rol != "EMPLEADO":
                    self.assertIsNone(usuario.perfil.obra_asignada)

    def test_creacion_usuario_rechaza_datos_invalidos(self):
        self.client.force_login(self.admin)
        for cambios in ({"username": " "}, {"username": "EMPLEADO"}, {"rol": "SUPERADMIN"}, {"email": "correo-invalido"}, {"obra_asignada": "9999999"}, {"password_confirm": "diferente"}, {"password": "12345678", "password_confirm": "12345678"}, {"first_name": ""}):
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(reverse("registro_usuario"), self.datos_usuario(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(User.objects.count(), 5)

    def test_obra_inactiva_no_puede_asignarse_a_usuario_nuevo(self):
        self.proyecto.activo = False
        self.proyecto.save()
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("registro_usuario"), self.datos_usuario())
        self.assertIn("obra_asignada", respuesta.context["form"].errors)
        self.assertFalse(User.objects.filter(username="nueva_cuenta").exists())

    def test_admin_edita_rol_y_conserva_password_si_vacio(self):
        self.client.force_login(self.admin)
        password_anterior = self.empleado.password
        datos = self.datos_usuario(username=self.empleado.username, rol="ADMIN", password="", password_confirm="")
        respuesta = self.client.post(reverse("usuario_editar", args=[self.empleado.pk]), datos)
        self.assertRedirects(respuesta, reverse("usuario_detalle", args=[self.empleado.pk]))
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.is_staff)
        self.assertEqual(self.empleado.password, password_anterior)
        self.assertEqual(self.empleado.perfil.rol, "ADMIN")
        self.assertIsNone(self.empleado.perfil.obra_asignada)

    def test_rebajar_rol_quita_staff_y_escritura(self):
        self.client.force_login(self.superusuario)
        datos = self.datos_usuario(username=self.admin.username, rol="VISUALIZADOR", password="", password_confirm="")
        self.assertEqual(self.client.post(reverse("usuario_editar", args=[self.admin.pk]), datos).status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_staff)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("proyectos"), self.datos_proyecto()).status_code, 403)

    def test_admin_puede_cambiar_asignacion_a_empleado(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(username=self.empleado.username, obra_asignada=str(self.otro_proyecto.pk), password="", password_confirm="")
        self.assertEqual(self.client.post(reverse("usuario_editar", args=[self.empleado.pk]), datos).status_code, 302)
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("proyecto_detalle", args=[self.proyecto.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("proyecto_detalle", args=[self.otro_proyecto.pk])).status_code, 200)

    def test_edicion_permite_conservar_asignacion_de_obra_inactiva(self):
        self.proyecto.activo = False
        self.proyecto.save()
        self.client.force_login(self.admin)
        datos = self.datos_usuario(username=self.empleado.username, password="", password_confirm="")
        self.assertEqual(self.client.post(reverse("usuario_editar", args=[self.empleado.pk]), datos).status_code, 302)
        self.empleado.perfil.refresh_from_db()
        self.assertEqual(self.empleado.perfil.obra_asignada, self.proyecto)

    def test_admin_cambia_contrasena_y_conserva_su_sesion(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(username=self.admin.username, rol="ADMIN", password="OtraClaveSegura!39", password_confirm="OtraClaveSegura!39")
        self.assertEqual(self.client.post(reverse("usuario_editar", args=[self.admin.pk]), datos).status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("OtraClaveSegura!39"))
        self.assertEqual(self.client.get(reverse("registro_usuario")).status_code, 200)

    def test_administrador_no_puede_bloquear_su_propio_acceso(self):
        self.client.force_login(self.admin)
        for cambios in ({"rol": "EMPLEADO"}, {"rol": "ADMIN", "is_active": ""}):
            respuesta = self.client.post(reverse("usuario_editar", args=[self.admin.pk]), self.datos_usuario(username=self.admin.username, **cambios))
            self.assertEqual(respuesta.status_code, 200)
            self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertEqual(self.client.post(reverse("usuario_eliminar", args=[self.admin.pk])).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.perfil.rol, "ADMIN")

    def test_admin_no_puede_modificar_o_eliminar_superusuario(self):
        self.client.force_login(self.admin)
        for nombre in ("usuario_editar", "usuario_eliminar"):
            url = reverse(nombre, args=[self.superusuario.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.datos_usuario()).status_code, 403)

    def test_desactivado_no_puede_iniciar_sesion(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(username=self.empleado.username, is_active="", password="", password_confirm="")
        self.assertEqual(self.client.post(reverse("usuario_editar", args=[self.empleado.pk]), datos).status_code, 302)
        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.is_active)
        self.assertIsNone(authenticate(username=self.empleado.username, password="PruebaGestion!72"))

    def test_edicion_de_cuenta_inactiva_conserva_rol_inicial(self):
        self.visualizador.is_active = False
        self.visualizador.save()
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("usuario_editar", args=[self.visualizador.pk]))
        self.assertEqual(respuesta.context["form"].initial["rol"], "VISUALIZADOR")

    def test_eliminar_usuario_conserva_pagos(self):
        self.client.force_login(self.admin)
        pago = PagoManoObra.objects.create(proyecto=self.proyecto, empleado=self.empleado, trabajador="Pedro", monto=1000, fecha=date.today())
        url = reverse("usuario_eliminar", args=[self.empleado.pk])
        self.assertContains(self.client.get(url), "Confirmar eliminación")
        self.assertTrue(User.objects.filter(pk=self.empleado.pk).exists())
        self.assertRedirects(self.client.post(url), reverse("registro_usuario"))
        self.assertFalse(User.objects.filter(pk=self.empleado.pk).exists())
        self.assertFalse(PerfilUsuario.objects.filter(usuario_id=self.empleado.pk).exists())
        pago.refresh_from_db()
        self.assertIsNone(pago.empleado)
        self.assertEqual(pago.trabajador, "Pedro")

    def test_eliminar_usuario_inexistente_vuelve_al_listado_con_aviso(self):
        self.client.force_login(self.admin)
        url = reverse("usuario_eliminar", args=[9999999])
        with self.settings(DEBUG=False):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(metodo=metodo.__name__):
                    respuesta = metodo(url, follow=True)
                    self.assertRedirects(respuesta, reverse("registro_usuario"))
                    self.assertContains(respuesta, "El usuario no existe o ya fue eliminado.")
        self.assertEqual(User.objects.count(), 5)

    def test_repetir_eliminacion_usuario_conserva_otras_cuentas_y_pagos(self):
        self.client.force_login(self.admin)
        pago = PagoManoObra.objects.create(proyecto=self.proyecto, empleado=self.empleado, trabajador="Pedro", monto=1000, fecha=date.today())
        url = reverse("usuario_eliminar", args=[self.empleado.pk])
        self.assertRedirects(self.client.post(url), reverse("registro_usuario"))
        for metodo in (self.client.get, self.client.post):
            with self.subTest(metodo=metodo.__name__):
                self.assertRedirects(metodo(url), reverse("registro_usuario"))
        self.assertFalse(User.objects.filter(pk=self.empleado.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.otro_empleado.pk).exists())
        pago.refresh_from_db()
        self.assertIsNone(pago.empleado_id)
        self.assertEqual(pago.trabajador, "Pedro")

    def test_eliminar_usuario_inexistente_conserva_permisos_y_csrf(self):
        url = reverse("usuario_eliminar", args=[9999999])
        for metodo in (self.client.get, self.client.post):
            self.assertRedirects(metodo(url), reverse("login") + "?next=" + url)
        for usuario in (self.visualizador, self.empleado):
            self.client.force_login(usuario)
            for metodo in (self.client.get, self.client.post):
                with self.subTest(usuario=usuario.username, metodo=metodo.__name__):
                    self.assertEqual(metodo(url).status_code, 403)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(url).status_code, 403)

    def test_eliminacion_usuario_conserva_bloqueo_de_cuenta_propia_y_superusuario(self):
        self.client.force_login(self.admin)
        for usuario in (self.admin, self.superusuario):
            url = reverse("usuario_eliminar", args=[usuario.pk])
            for metodo in (self.client.get, self.client.post):
                with self.subTest(usuario=usuario.username, metodo=metodo.__name__):
                    self.assertEqual(metodo(url).status_code, 403)
            self.assertTrue(User.objects.filter(pk=usuario.pk).exists())

    def test_solo_admin_accede_al_crud_de_usuarios(self):
        rutas = [reverse("registro_usuario"), reverse("usuario_detalle", args=[self.otro_empleado.pk]), reverse("usuario_editar", args=[self.otro_empleado.pk]), reverse("usuario_eliminar", args=[self.otro_empleado.pk])]
        for usuario in (self.visualizador, self.empleado):
            self.client.force_login(usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 403)
                    self.assertEqual(self.client.post(ruta, self.datos_usuario()).status_code, 403)
        self.assertEqual(User.objects.count(), 5)

    def test_portal_no_muestra_pagos_de_personas_con_mismo_nombre(self):
        propio = PagoManoObra.objects.create(proyecto=self.proyecto, empleado=self.empleado, trabajador="Pedro", concepto="Pago propio", monto=1000, fecha=date.today())
        PagoManoObra.objects.create(proyecto=self.otro_proyecto, empleado=self.otro_empleado, trabajador="Pedro", concepto="Pago ajeno", monto=9000, fecha=date.today())
        PagoManoObra.objects.create(proyecto=self.otro_proyecto, trabajador=self.empleado.username, concepto="Pago sin identidad", monto=5000, fecha=date.today())
        self.client.force_login(self.empleado)
        respuesta = self.client.get(reverse("portal_empleado"))
        self.assertEqual(list(respuesta.context["mis_pagos"]), [propio])
        self.assertEqual(respuesta.context["total_ganado"], 1000)

    def test_pantallas_administrativas_renderizan(self):
        self.client.force_login(self.admin)
        rutas = [reverse("inicio"), reverse("finanzas"), reverse("calendario"), reverse("proyectos"), reverse("registro_usuario"), reverse("proyecto_editar", args=[self.proyecto.pk]), reverse("usuario_detalle", args=[self.empleado.pk]), reverse("usuario_editar", args=[self.empleado.pk])]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_mutaciones_requieren_csrf_y_logout_requiere_post(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(reverse("proyectos"), self.datos_proyecto()).status_code, 403)
        self.assertEqual(cliente.post(reverse("registro_usuario"), self.datos_usuario()).status_code, 403)
        self.assertEqual(cliente.post(reverse("proyecto_eliminar", args=[self.proyecto.pk])).status_code, 403)
        self.assertEqual(cliente.post(reverse("usuario_eliminar", args=[self.empleado.pk])).status_code, 403)
        self.assertEqual(cliente.get(reverse("logout")).status_code, 405)
        self.assertEqual(cliente.post(reverse("logout")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
