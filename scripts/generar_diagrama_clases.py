r"""Genera un draw.io editable desde los modelos y clases reales, sin consultar la base.

Uso: .venv\Scripts\python.exe -B scripts/generar_diagrama_clases.py
"""

import ast
import inspect
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from html import escape

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Proyecto.test_settings")

import django

django.setup()

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import models

from construApp.models import Cliente, GastoMaterial, HitoCalendario, PagoManoObra, PerfilUsuario, Proyecto


class Diagrama:
    def __init__(self, archivo):
        self.archivo = ET.Element("mxfile", host="app.diagrams.net", type="device", version="24.7.17")
        self.destino = archivo
        self.indice = 0

    def pagina(self, nombre, ancho=1800, alto=1500):
        pagina = ET.SubElement(self.archivo, "diagram", name=nombre, id=f"pagina-{len(self.archivo) + 1}")
        modelo = ET.SubElement(pagina, "mxGraphModel", dx="1800", dy="1500", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth=str(ancho), pageHeight=str(alto), math="0", shadow="0")
        self.raiz = ET.SubElement(modelo, "root")
        ET.SubElement(self.raiz, "mxCell", id="0")
        ET.SubElement(self.raiz, "mxCell", id="1", parent="0")
        self.ids = set()

    def caja(self, nombre, titulo, atributos, metodos, x, y, ancho=380, color="#dae8fc", estereotipo="clase"):
        filas = [f"<div style='text-align:center'><i>«{escape(estereotipo)}»</i><br><b>{escape(titulo)}</b></div><hr>"]
        filas += [escape(linea) + "<br>" for linea in atributos]
        if metodos:
            filas += ["<hr>"] + [escape(linea) + "<br>" for linea in metodos]
        # Un ancho de 380 px admite aproximadamente 48 caracteres a 12 px.
        columnas = max(30, int((ancho - 24) / 6.5))
        lineas = sum(max(1, (len(linea) + columnas - 1) // columnas) for linea in atributos + metodos)
        alto = 80 + 19 * lineas + (16 if metodos else 0)
        estilo = f"rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=12;fontSize=12;fontFamily=Helvetica;fontColor=#1f2937;fillColor={color};strokeColor=#4b6584;"
        celda = ET.SubElement(self.raiz, "mxCell", id=nombre, value="".join(filas), style=estilo, vertex="1", parent="1")
        ET.SubElement(celda, "mxGeometry", x=str(x), y=str(y), width=str(ancho), height=str(alto), **{"as": "geometry"})
        self.ids.add(nombre)
        return alto

    def nota(self, nombre, texto, x, y, ancho=400, alto=130):
        celda = ET.SubElement(self.raiz, "mxCell", id=nombre, value=escape(texto).replace("\n", "<br>"), style="shape=note;whiteSpace=wrap;html=1;align=left;spacing=12;fontSize=12;fillColor=#fff2cc;strokeColor=#d6b656;", vertex="1", parent="1")
        ET.SubElement(celda, "mxGeometry", x=str(x), y=str(y), width=str(ancho), height=str(alto), **{"as": "geometry"})
        self.ids.add(nombre)

    def enlace(self, origen, destino, texto="", inicio=None, fin=None, tipo="asociacion", estilo="", puntos=None):
        assert origen in self.ids and destino in self.ids, (origen, destino)
        self.indice += 1
        identificador = f"relacion-{self.indice}"
        flecha = {
            "asociacion": "endArrow=none;",
            "composicion": "startArrow=diamond;startFill=1;endArrow=none;",
            "herencia": "endArrow=block;endFill=0;",
            "dependencia": "endArrow=open;dashed=1;",
        }[tipo]
        celda = ET.SubElement(self.raiz, "mxCell", id=identificador, value=texto, style=f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;{flecha}fontSize=11;labelBackgroundColor=#ffffff;strokeColor=#475569;{estilo}", edge="1", parent="1", source=origen, target=destino)
        geometria = ET.SubElement(celda, "mxGeometry", relative="1", **{"as": "geometry"})
        if puntos:
            ruta = ET.SubElement(geometria, "Array", **{"as": "points"})
            for x, y in puntos:
                ET.SubElement(ruta, "mxPoint", x=str(x), y=str(y))
        for lado, valor, posicion in (("inicio", inicio, "-0.85"), ("fin", fin, "0.85")):
            if valor is not None:
                etiqueta = ET.SubElement(self.raiz, "mxCell", id=f"{identificador}-{lado}", value=valor, style="edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;fontSize=12;labelBackgroundColor=#ffffff;", vertex="1", connectable="0", parent=identificador)
                geometria = ET.SubElement(etiqueta, "mxGeometry", x=posicion, y="-12", relative="1", **{"as": "geometry"})
                ET.SubElement(geometria, "mxPoint", **{"as": "offset"})

    def guardar(self):
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(self.archivo, space="  ")
        ET.ElementTree(self.archivo).write(self.destino, encoding="utf-8", xml_declaration=True)


def atributos_modelo(modelo):
    atributos = []
    for campo in modelo._meta.fields:
        marcas = []
        if campo.primary_key:
            marcas.append("PK")
            if campo.auto_created:
                marcas.append("autogenerado")
        elif campo.unique:
            marcas.append("único")
        if campo.is_relation:
            tipo = campo.related_model.__name__
            marcas.extend(["FK", campo.remote_field.on_delete.__name__])
        else:
            tipo = campo.get_internal_type()
            if campo.max_length:
                tipo += f"({campo.max_length})"
        if campo.null:
            marcas.append("nullable")
        elif getattr(campo, "auto_now_add", False):
            marcas.append("auto_now_add")
        elif campo.blank and not campo.primary_key:
            marcas.append("opcional")
        if campo.choices:
            marcas.append("opciones: " + ", ".join(str(valor) for valor, _ in campo.flatchoices))
        sufijo = " {" + "; ".join(marcas) + "}" if marcas else ""
        atributos.append(f"+ {campo.name}: {tipo}{sufijo}")
    for campo in modelo._meta.many_to_many:
        atributos.append(f"+ {campo.name}: {campo.related_model.__name__}[0..*] {{M:N}}")
    return atributos


def metodos_modelo(modelo):
    metodos = []
    for nombre, valor in vars(modelo).items():
        if nombre.startswith("_") and nombre != "__str__":
            continue
        if isinstance(valor, property):
            metodos.append(f"+ /{nombre} {{propiedad calculada}}")
        elif inspect.isfunction(valor) and valor.__module__ == modelo.__module__:
            metodos.append(f"+ {nombre}{inspect.signature(valor)}")
    if modelo is User:
        metodos = ["+ get_full_name(): str", "+ get_short_name(): str", "+ set_password(raw_password)", "+ check_password(raw_password): bool", "+ has_perm(perm, obj=None): bool"]
    return metodos


def agregar_modelo(diagrama, modelo, x, y, ancho=380):
    return diagrama.caja(modelo.__name__, modelo.__name__, atributos_modelo(modelo), metodos_modelo(modelo), x, y, ancho)


def generar():
    diagrama = Diagrama(BASE_DIR / "docs" / "diagrama-clases.drawio")
    diagrama.pagina("1. Modelo de dominio", 1800, 1550)
    agregar_modelo(diagrama, Cliente, 30, 80, 390)
    agregar_modelo(diagrama, Proyecto, 530, 80, 500)
    agregar_modelo(diagrama, User, 1280, 80, 410)
    agregar_modelo(diagrama, PerfilUsuario, 1280, 620, 410)
    agregar_modelo(diagrama, GastoMaterial, 30, 1010, 420)
    agregar_modelo(diagrama, PagoManoObra, 550, 1010, 460)
    agregar_modelo(diagrama, HitoCalendario, 1250, 1120, 440)
    diagrama.enlace("Cliente", "Proyecto", "cliente / proyectos · PROTECT", "0..1", "0..*", estilo="exitX=1;exitY=0.35;entryX=0;entryY=0.2;")
    diagrama.enlace("User", "PerfilUsuario", "usuario / perfil · CASCADE", "1", "0..1", estilo="exitX=0.6;exitY=1;entryX=0.6;entryY=0;")
    diagrama.enlace("Proyecto", "PerfilUsuario", "obra_asignada / trabajadores_asignados · SET_NULL", "0..1", "0..*", estilo="exitX=1;exitY=0.65;entryX=0;entryY=0.3;")
    diagrama.enlace("Proyecto", "GastoMaterial", "proyecto / gastos_materiales · CASCADE", "1", "0..*", "composicion", "exitX=0.2;exitY=1;entryX=0.5;entryY=0;", [(630, 980), (240, 980)])
    diagrama.enlace("Proyecto", "PagoManoObra", "proyecto / pagos_mano_obra · CASCADE", "1", "0..*", "composicion", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    diagrama.enlace("Proyecto", "HitoCalendario", "proyecto / hitos · CASCADE", "1", "0..*", "composicion", "exitX=1;exitY=0.9;entryX=0;entryY=0.2;")
    diagrama.enlace("User", "PagoManoObra", "empleado / pagos_recibidos · SET_NULL", "0..1", "0..*", estilo="exitX=0;exitY=0.6;entryX=1;entryY=0.3;")
    diagrama.nota("leyenda", "UML · + público · / propiedad calculada\nPK = clave primaria · FK = clave foránea\nCASCADE elimina los registros dependientes.\nSET_NULL conserva el registro sin su vínculo.\nPROTECT impide borrar clientes con obras.\nLos seis modelos de negocio heredan de django.db.models.Model; User hereda de AbstractUser.", 30, 520, 390, 180)
    diagrama.nota("reglas", "Reglas de registro\nCliente, dirección, descripción y término estimado son obligatorios en ProyectoForm.\nLas obras anteriores admiten cliente y término nulos hasta completar su ficha.\nTérmino estimado ≥ inicio (modelo y base).\nPresupuestos y montos ≥ 1 CLP.\nUn cliente reúne todas sus obras, activas e inactivas.\nEl perfil se crea automáticamente al guardar User.\nUser es una cuenta; Cliente no requiere acceso.", 30, 730, 390, 240)

    diagrama.pagina("2. Autenticación y tablas de Django", 2000, 1700)
    auth_modelos = [User, Group, Permission, ContentType, LogEntry, Session, User.groups.through, User.user_permissions.through, Group.permissions.through]
    posiciones = [(40, 80), (740, 80), (1480, 80), (1480, 700), (40, 1150), (740, 1150), (500, 700), (40, 700), (960, 700)]
    for modelo, (x, y) in zip(auth_modelos, posiciones):
        agregar_modelo(diagrama, modelo, x, y, 450)
    rutas_auth = {
        ("User_groups", "user"): ("exitX=1;exitY=0.5;entryX=0.25;entryY=0;", [(600, 300), (600, 650), (612, 650)]),
        ("User_groups", "group"): ("exitX=0.2;exitY=1;entryX=0.75;entryY=0;", [(830, 580), (838, 580)]),
        ("User_user_permissions", "user"): ("exitX=0.3;exitY=1;entryX=0.3;entryY=0;", None),
        ("User_user_permissions", "permission"): ("exitX=0.2;exitY=1;entryX=0.7;entryY=0;", [(1570, 550), (355, 550)]),
        ("Group_permissions", "group"): ("exitX=0.8;exitY=1;entryX=0.25;entryY=0;", [(1100, 600), (1072, 600)]),
        ("Group_permissions", "permission"): ("exitX=0.5;exitY=1;entryX=0.75;entryY=0;", [(1705, 620), (1298, 620)]),
        ("Permission", "content_type"): ("exitX=0.8;exitY=0;entryX=0.8;entryY=1;", None),
        ("LogEntry", "user"): ("exitX=0;exitY=0.7;entryX=0;entryY=0.5;", [(20, 400), (20, 1340)]),
        ("LogEntry", "content_type"): ("exitX=0.8;exitY=1;entryX=0.8;entryY=0;", [(1840, 1060), (400, 1060)]),
    }
    for modelo in auth_modelos:
        for campo in modelo._meta.fields:
            if campo.is_relation and campo.related_model in auth_modelos:
                padre = campo.related_model
                estilo, puntos = rutas_auth[(modelo.__name__, campo.name)]
                texto = campo.name if (modelo is LogEntry and campo.name == "user") else campo.name + " · " + campo.remote_field.on_delete.__name__
                diagrama.enlace(padre.__name__, modelo.__name__, texto, "0..1" if campo.null else "1", "0..*", estilo=estilo, puntos=puntos)
    diagrama.nota("auth-nota", "Las asociaciones M:N de User.groups, User.user_permissions y Group.permissions se detallan mediante sus tablas intermedias reales.\nSession guarda la sesión codificada; no tiene FK a User.\nLogEntry registra acciones del administrador de Django; no es una bitácora de todos los pagos de la aplicación.\nUser en esta página es la misma clase del modelo de dominio.", 1480, 1200, 450, 190)

    diagrama.pagina("3. Formularios y control de la aplicación", 2600, 3000)
    arbol = ast.parse((BASE_DIR / "construApp" / "forms.py").read_text(encoding="utf-8"))
    posiciones_form = {"EstiloFormulario": (40, 70), "ClienteForm": (40, 450), "ProyectoForm": (660, 450), "EgresoForm": (1280, 450), "HitoForm": (40, 1220), "UsuarioForm": (660, 1220)}
    from construApp import forms

    for nodo in arbol.body:
        if not isinstance(nodo, ast.ClassDef):
            continue
        atributos, metodos = [], []
        clase = getattr(forms, nodo.name)
        if hasattr(clase, "base_fields"):
            nombres = list(clase.base_fields)
            meta = getattr(clase, "Meta", None)
            if meta and hasattr(meta, "fields"):
                nombres = list(dict.fromkeys(list(meta.fields) + nombres))
            for nombre in nombres:
                campo = clase.base_fields.get(nombre)
                atributos.append(f"+ {nombre}: {type(campo).__name__}" + (" {requerido}" if campo and campo.required else ""))
        for miembro in nodo.body:
            if isinstance(miembro, (ast.FunctionDef, ast.AsyncFunctionDef)):
                firma = ast.unparse(miembro.args)
                metodos.append(f"+ {miembro.name}({firma})")
        if nodo.name == "ProyectoForm":
            atributos.append("{cliente, dirección, descripción y término requeridos en __init__}")
        x, y = posiciones_form[nodo.name]
        diagrama.caja(nodo.name, nodo.name, atributos, metodos, x, y, 510, "#d5e8d4")
    diagrama.caja("ModelForm", "django.forms.ModelForm", [], ["+ is_valid(): bool", "+ save(commit=True): Model"], 660, 70, 510, "#f5f5f5", "framework")
    diagrama.caja("Form", "django.forms.Form", [], ["+ is_valid(): bool", "+ clean(): dict"], 1280, 70, 510, "#f5f5f5", "framework")
    rutas_herencia = {
        "ClienteForm": ([(142, 270), (295, 270)], [(448, 390), (915, 390)]),
        "ProyectoForm": ([(762, 290), (295, 290)], [(1068, 370), (915, 370)]),
        "EgresoForm": ([(1382, 310), (295, 310)], [(1688, 350), (1535, 350)]),
        "HitoForm": ([(142, 1170), (580, 1170), (580, 330), (295, 330)], [(448, 1190), (620, 1190), (620, 410), (1535, 410)]),
        "UsuarioForm": ([(762, 1140), (600, 1140), (600, 340), (295, 340)], [(1068, 1160), (1230, 1160), (1230, 400), (915, 400)]),
    }
    for nombre, (ruta_estilo, ruta_base) in rutas_herencia.items():
        diagrama.enlace(nombre, "EstiloFormulario", tipo="herencia", estilo="exitX=0.2;exitY=0;entryX=0.5;entryY=1;", puntos=ruta_estilo)
        diagrama.enlace(nombre, "Form" if nombre in ("EgresoForm", "HitoForm") else "ModelForm", tipo="herencia", estilo="exitX=0.8;exitY=0;entryX=0.5;entryY=1;", puntos=ruta_base)
    for archivo, x, y, ancho in (("views", 1900, 70, 620), ("permisos", 1900, 1000, 620), ("signals", 1900, 1270, 620), ("context_processors", 1900, 1530, 620)):
        modulo = ast.parse((BASE_DIR / "construApp" / f"{archivo}.py").read_text(encoding="utf-8"))
        funciones = [f"+ {n.name}({ast.unparse(n.args)})" for n in modulo.body if isinstance(n, ast.FunctionDef)]
        diagrama.caja(archivo, "construApp." + archivo, [], funciones, x, y, ancho, "#ffe6cc", "módulo de funciones")
    for archivo, posiciones in (("middleware", [(1280, 1650)]), ("apps", [(40, 2050)]), ("admin", [(660, 2050), (1280, 2050)])):
        modulo = ast.parse((BASE_DIR / "construApp" / f"{archivo}.py").read_text(encoding="utf-8"))
        clases = [n for n in modulo.body if isinstance(n, ast.ClassDef)]
        for nodo, (x, y) in zip(clases, posiciones):
            atributos, metodos = [], []
            for miembro in nodo.body:
                if isinstance(miembro, ast.FunctionDef):
                    metodos.append(f"+ {miembro.name}({ast.unparse(miembro.args)})")
                elif isinstance(miembro, ast.Assign):
                    atributos.append(ast.unparse(miembro))
            bases = ", ".join(ast.unparse(b) for b in nodo.bases)
            if bases:
                atributos.insert(0, "{hereda de " + bases + "}")
            diagrama.caja(nodo.name, nodo.name, atributos, metodos, x, y, 510, "#e1d5e7", archivo)
    rutas_formularios = {
        "ClienteForm": [(1810, 180), (1810, 420), (295, 420)],
        "ProyectoForm": [(1820, 230), (1820, 430), (915, 430)],
        "EgresoForm": [(1830, 280), (1830, 440), (1535, 440)],
        "HitoForm": [(1840, 330), (1840, 950), (295, 950)],
        "UsuarioForm": [(1850, 380), (1850, 980), (915, 980)],
    }
    for indice, (formulario, puntos) in enumerate(rutas_formularios.items()):
        diagrama.enlace("views", formulario, "usa formulario", tipo="dependencia", estilo=f"exitX=0;exitY={0.2 + indice * 0.1};entryX=0.5;entryY=0;", puntos=puntos)
    diagrama.enlace("views", "permisos", "autoriza", tipo="dependencia")
    diagrama.enlace("context_processors", "permisos", "consulta rol", tipo="dependencia", estilo="exitX=1;exitY=0.5;entryX=1;entryY=0.5;", puntos=[(2570, 1588), (2570, 1080)])
    diagrama.enlace("ConstruappConfig", "signals", "ready(): importa señales", tipo="dependencia", estilo="exitX=0.5;exitY=0;entryX=0;entryY=0.5;", puntos=[(295, 1850), (1840, 1850), (1840, 1328)])
    diagrama.enlace("ClienteAdmin", "ClienteForm", "form", tipo="dependencia", estilo="exitX=0;exitY=0.5;entryX=1;entryY=0.6;", puntos=[(580, 2140), (580, 599)])
    diagrama.enlace("ProyectoAdmin", "ProyectoForm", "form", tipo="dependencia", estilo="exitX=0;exitY=0.5;entryX=1;entryY=0.5;", puntos=[(1230, 2140), (1230, 650)])
    diagrama.nota("capas-nota", "Los recuadros naranjas son módulos de funciones, no clases inventadas.\nVistas: autenticación, portal, obras, clientes, egresos, calendario y usuarios.\nADMIN modifica; VISUALIZADOR consulta; EMPLEADO ve su obra y sus pagos.\nLos cambios requieren POST y CSRF. El GET de eliminación solo confirma.\nEgresoForm.save() crea o actualiza el tipo original. Los totales se calculan desde los registros vigentes.\nLos atributos y operaciones de las clases propias se extraen del código. La API heredada del framework se resume.", 1900, 1930, 620, 240)
    diagrama.guardar()
    print(diagrama.destino)


if __name__ == "__main__":
    generar()
