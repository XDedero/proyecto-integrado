"""Verificación de interfaz con Playwright y datos ficticios en SQLite temporal.

Requiere Playwright y WebKit instalados. No consulta la base configurada en .env.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ["DJANGO_SETTINGS_MODULE"] = "Proyecto.test_settings"

from django.conf import settings
from playwright.sync_api import expect, sync_playwright


class Silencioso(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def verificar():
    reportes = BASE_DIR / "reports" / "funcionalidades-2026-11-20"
    reportes.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="bd-temporal-", dir=reportes) as temporal:
        assert Path(temporal).resolve().is_relative_to(reportes.resolve())
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path(temporal) / "prueba.sqlite3")}}
        import django

        django.setup()
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from construApp.models import Cliente, GastoMaterial, PagoManoObra, Proyecto

        call_command("migrate", verbosity=0)
        User.objects.create_user("demo_admin", password="ValidacionLocal!2026", first_name="Luis", is_staff=True)
        lector = User.objects.create_user("demo_lector", password="ValidacionLocal!2026")
        lector.perfil.rol = "VISUALIZADOR"
        lector.perfil.save()
        cliente = Cliente.objects.create(nombre="Cliente de demostración", telefono="+56 9 12345678")
        obra = Proyecto.objects.create(nombre="Vivienda de demostración", cliente=cliente, direccion="Calle de prueba 123", comuna="Santiago", descripcion="Construcción de vivienda", fecha_inicio=date(2026, 11, 1), fecha_termino_estimada=date(2027, 2, 28), presupuesto_inicial=10000000)
        Proyecto.objects.create(nombre="Ampliación de demostración", cliente=cliente, fecha_inicio=date(2026, 5, 1), presupuesto_inicial=5000000, activo=False)
        gasto = GastoMaterial.objects.create(proyecto=obra, fecha=date(2026, 11, 18), proveedor="Proveedor de demostración", categoria="MADERA", monto=250000)
        pago = PagoManoObra.objects.create(proyecto=obra, trabajador="Trabajador de demostración", concepto="Jornal", monto=150000, fecha=date(2026, 11, 18))
        servidor = make_server("127.0.0.1", 0, get_wsgi_application(), handler_class=Silencioso)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        url = f"http://127.0.0.1:{servidor.server_port}"
        resultados, errores = [], []
        # Playwright usa un bucle asyncio; las consultas de verificación se hacen
        # en otro hilo con su propia conexión, sin desactivar la protección Django.
        with ThreadPoolExecutor(max_workers=1) as consultas:
            def en_base(funcion):
                def ejecutar():
                    try:
                        return funcion()
                    finally:
                        connections.close_all()
                return consultas.submit(ejecutar).result()

            try:
                with sync_playwright() as pw:
                    ejecutable = Path(pw.webkit.executable_path)
                    if not ejecutable.exists():
                        disponibles = sorted((Path(os.environ["LOCALAPPDATA"]) / "ms-playwright").glob("webkit-*/Playwright.exe"), reverse=True)
                        ejecutable = disponibles[0] if disponibles else ejecutable
                    navegador = pw.webkit.launch(headless=True, executable_path=str(ejecutable))
                    pagina = navegador.new_page(viewport={"width": 1440, "height": 1000})
                    # Misma versión que base.html; permite revisar el diseño cuando
                    # el entorno de verificación no puede acceder al CDN.
                    css_local = BASE_DIR / "reports" / "funcionalidades-2026-11-18" / "bootstrap.min.css"
                    if css_local.exists():
                        pagina.route("https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css", lambda ruta: ruta.fulfill(path=str(css_local), content_type="text/css"))
                    pagina.on("pageerror", lambda error: errores.append(str(error)))
                    pagina.goto(url + "/login/", wait_until="networkidle")
                    pagina.locator("[name=username]").fill("demo_admin")
                    pagina.locator("[name=password]").fill("ValidacionLocal!2026")
                    pagina.locator("button[type=submit]").click()
                    pagina.wait_for_url(url + "/")
                    pagina.goto(url + "/finanzas/", wait_until="networkidle")
                    assert pagina.locator("#bloque_materiales").is_visible()
                    assert pagina.locator("#bloque_mano_obra").is_hidden()
                    pagina.select_option("#tipo_egreso", "MANO_OBRA")
                    assert pagina.locator("#bloque_mano_obra").is_visible()
                    assert pagina.locator("#bloque_materiales").is_hidden()
                    pagina.screenshot(path=str(reportes / "gastos-y-pagos.png"), full_page=True)
                    resultados.append("Formulario alterna entre materiales y mano de obra")
                    pagina.select_option("#id_proyecto", str(obra.pk))
                    pagina.get_by_role("button", name="Filtrar", exact=True).click()
                    pagina.wait_for_url(url + f"/finanzas/?proyecto={obra.pk}")
                    assert pagina.locator("#total_materiales").inner_text() == "$250000 CLP"
                    assert pagina.locator("#total_mano_obra").inner_text() == "$150000 CLP"
                    assert pagina.input_value("#proyecto_id") == str(obra.pk)
                    pagina.fill("#nombre", "Cerámicas cocina")
                    pagina.fill("#proveedor", "Proveedor de cerámicas")
                    pagina.select_option("#categoria", "__nueva__")
                    assert pagina.locator("#nueva_categoria").is_visible()
                    pagina.fill("#nueva_categoria", "Cerámicas y pisos")
                    pagina.fill("#monto", "100000")
                    pagina.fill("#fecha", "2026-11-20")
                    assert pagina.locator("#bloque_flete").is_hidden()
                    pagina.get_by_role("button", name="Flete", exact=True).click()
                    assert pagina.locator("#con_flete").is_checked()
                    pagina.fill("#monto_flete", "15000")
                    assert pagina.locator("#total_egreso").inner_text() == "$115.000 CLP"
                    pagina.get_by_role("button", name="Guardar egreso").click()
                    pagina.wait_for_url(url + f"/finanzas/?proyecto={obra.pk}")
                    expect(pagina.locator("#total_materiales")).to_have_text("$365000 CLP")
                    assert pagina.locator("#total_egresos").inner_text() == "$515000 CLP"
                    assert pagina.get_by_role("cell", name="Cerámicas cocina", exact=True).is_visible()
                    assert pagina.locator("#categoria option").filter(has_text="Cerámicas y pisos").count() == 1
                    nuevo_gasto = en_base(lambda: GastoMaterial.objects.get(nombre="Cerámicas cocina").pk)
                    resultados.append("Filtro por obra muestra materiales, mano de obra y total; crear categoría y gasto con nombre y flete actualiza los totales")
                    pagina.screenshot(path=str(reportes / "filtro-y-flete.png"), full_page=True)
                    pagina.goto(url + f"/finanzas/material/{nuevo_gasto}/editar/", wait_until="networkidle")
                    assert pagina.input_value("#monto") == "100000"
                    assert pagina.input_value("#monto_flete") == "15000"
                    assert pagina.locator("#con_flete").is_checked()
                    pagina.locator("#con_flete").uncheck()
                    assert pagina.locator("#bloque_flete").is_hidden()
                    assert pagina.locator("#total_egreso").inner_text() == "$100.000 CLP"
                    pagina.get_by_role("button", name="Guardar cambios").click()
                    pagina.wait_for_url(url + "/finanzas/")
                    assert en_base(lambda: GastoMaterial.objects.get(pk=nuevo_gasto).monto_total) == 100000
                    resultados.append("Editar conserva base y flete separados; desmarcar flete lo retira del total")
                    pagina.goto(url + f"/finanzas/material/{gasto.pk}/editar/", wait_until="networkidle")
                    assert pagina.input_value("#monto") == "250000"
                    pagina.fill("#monto", "300000")
                    pagina.get_by_role("button", name="Guardar cambios").click()
                    pagina.wait_for_url(url + "/finanzas/")
                    assert en_base(lambda: GastoMaterial.objects.get(pk=gasto.pk).monto) == 300000
                    resultados.append("Editar gasto modifica su monto y conserva el registro")
                    pagina.goto(url + f"/finanzas/mano-obra/{pago.pk}/editar/", wait_until="networkidle")
                    assert pagina.locator("#bloque_mano_obra").is_visible()
                    assert pagina.locator("#bloque_materiales").is_hidden()
                    pagina.fill("#monto", "180000")
                    pagina.fill("#concepto", "Avance de terminaciones")
                    pagina.screenshot(path=str(reportes / "editar-pago.png"), full_page=True)
                    pagina.get_by_role("button", name="Guardar cambios").click()
                    pagina.wait_for_url(url + "/finanzas/")
                    assert en_base(lambda: PagoManoObra.objects.get(pk=pago.pk).monto) == 180000
                    resultados.append("Editar pago modifica monto y concepto")
                    pagina.goto(url + f"/finanzas/mano-obra/{pago.pk}/eliminar/", wait_until="networkidle")
                    assert en_base(lambda: PagoManoObra.objects.filter(pk=pago.pk).exists())
                    pagina.screenshot(path=str(reportes / "confirmar-eliminacion.png"), full_page=True)
                    pagina.get_by_role("button", name="Eliminar definitivamente").click()
                    pagina.wait_for_url(url + "/finanzas/")
                    assert not en_base(lambda: PagoManoObra.objects.filter(pk=pago.pk).exists())
                    resultados.append("Eliminar pago exige confirmación y retira el registro")
                    pagina.goto(url + f"/clientes/{cliente.pk}/", wait_until="networkidle")
                    assert pagina.get_by_role("link", name="Vivienda de demostración").is_visible()
                    assert pagina.get_by_role("link", name="Ampliación de demostración").is_visible()
                    pagina.screenshot(path=str(reportes / "historial-cliente.png"), full_page=True)
                    pagina.get_by_role("link", name="Registrar obra para este cliente").click()
                    assert pagina.input_value("#id_cliente") == str(cliente.pk)
                    for campo, valor in {"nombre": "Remodelación desde navegador", "direccion": "Avenida de prueba 456", "presupuesto_inicial": "2500000", "fecha_inicio": "2026-11-18", "fecha_termino_estimada": "2026-12-18"}.items():
                        pagina.locator("#id_" + campo).fill(valor)
                    assert not pagina.locator("#id_descripcion").get_attribute("required")
                    assert pagina.locator("#id_nuevo_tipo_obra").is_hidden()
                    pagina.select_option("#id_tipo_obra", "__nueva__")
                    pagina.fill("#id_nuevo_tipo_obra", "Paisajismo")
                    pagina.screenshot(path=str(reportes / "registro-obra.png"), full_page=True)
                    pagina.get_by_role("button", name="Guardar proyecto").click()
                    pagina.wait_for_url(url + "/proyectos/")
                    nueva_pk, cliente_pk = en_base(lambda: Proyecto.objects.values_list("pk", "cliente_id").get(nombre="Remodelación desde navegador"))
                    assert cliente_pk == cliente.pk
                    assert en_base(lambda: Proyecto.objects.get(pk=nueva_pk).tipo_obra) == "Paisajismo"
                    assert en_base(lambda: Proyecto.objects.get(pk=nueva_pk).descripcion) == ""
                    resultados.append("Registrar obra sin descripción permite agregar un tipo nuevo y conserva el cliente")
                    pagina.goto(url + f"/proyectos/{nueva_pk}/editar/", wait_until="networkidle")
                    assert pagina.input_value("#id_tipo_obra") == "Paisajismo"
                    pagina.get_by_role("button", name="Guardar cambios").click()
                    pagina.wait_for_url(url + f"/proyectos/{nueva_pk}/")
                    resultados.append("Editar obra sin descripción conserva el nuevo tipo de obra")
                    pagina.goto(url + f"/proyectos/{nueva_pk}/", wait_until="networkidle")
                    assert pagina.get_by_role("link", name="Cliente de demostración").is_visible()
                    pagina.screenshot(path=str(reportes / "ficha-obra.png"), full_page=True)
                    pagina.set_viewport_size({"width": 390, "height": 844})
                    pagina.goto(url + f"/clientes/{cliente.pk}/", wait_until="networkidle")
                    pagina.screenshot(path=str(reportes / "historial-cliente-movil.png"), full_page=True)
                    desbordes = pagina.evaluate("Array.from(document.querySelectorAll('body *')).filter(el => el.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(el).position !== 'absolute').map(el => ({tag:el.tagName,clase:el.className,ancho:el.getBoundingClientRect().width,derecha:el.getBoundingClientRect().right})).slice(0,15)")
                    assert pagina.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), desbordes
                    resultados.append("Historial con varias obras y pantalla móvil sin desborde")
                    pagina.goto(url + f"/finanzas/?proyecto={obra.pk}", wait_until="networkidle")
                    pagina.screenshot(path=str(reportes / "gastos-movil.png"), full_page=True)
                    assert pagina.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    resultados.append("Gastos filtrados y formulario con flete se adaptan a pantalla móvil")
                    pagina.get_by_role("button", name="Cerrar sesión").click()
                    pagina.wait_for_url(url + "/login/")
                    pagina.locator("[name=username]").fill("demo_lector")
                    pagina.locator("[name=password]").fill("ValidacionLocal!2026")
                    pagina.locator("button[type=submit]").click()
                    pagina.wait_for_url(url + "/")
                    pagina.goto(url + f"/finanzas/?proyecto={obra.pk}", wait_until="networkidle")
                    assert pagina.locator("#total_materiales").inner_text() == "$400000 CLP"
                    assert pagina.locator("#tipo_egreso").count() == 0
                    resultados.append("Visualizador puede filtrar gastos sin formulario de escritura ni errores JavaScript")
                    navegador.close()
            finally:
                servidor.shutdown()
                hilo.join(timeout=5)
                servidor.server_close()
                connections.close_all()
        assert not errores, errores
        informe = {"fecha": "2026-11-20", "entorno": "SQLite temporal; datos ficticios", "navegador": "Playwright WebKit; escritorio 1440x1000 y móvil 390x844", "resultado": "OK", "comprobaciones": resultados, "errores_javascript": errores}
        (reportes / "validacion-navegador.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(informe, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    verificar()
