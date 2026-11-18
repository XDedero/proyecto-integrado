# Obras, clientes y corrección de egresos

## Gastos de materiales y pagos de mano de obra

En **Gastos y pagos**, cada registro tiene las acciones **Editar** y **Eliminar**
para administradores. La edición permite corregir obra, fecha, monto y los datos
del proveedor o trabajador. En los pagos se puede cambiar, conservar o quitar la
cuenta del empleado. El tipo original de registro se conserva.

La eliminación muestra primero la obra, fecha, monto y destinatario. Solo el
botón de confirmación envía el POST que elimina el registro. Los saldos de las
obras, acumulados de clientes y pagos del portal se calculan desde los registros
vigentes, por lo que reflejan inmediatamente las correcciones y eliminaciones.

Una corrección permite conservar una obra o un empleado que actualmente esté
inactivo. Para cambiar de asignación solo se ofrecen otras obras activas y
empleados activos con rol de empleado. Las cuentas nunca se vinculan por una
coincidencia de nombre.

## Registro de obras

La ficha incluye nombre, cliente, tipo de obra, descripción y alcance, dirección,
comuna, región, responsable, presupuesto inicial, fecha de inicio, término
estimado, condiciones y observaciones, además del indicador de obra activa.

Al crear o actualizar una obra son obligatorios el nombre, cliente, tipo de obra,
descripción, dirección, presupuesto y ambas fechas. El presupuesto debe ser
positivo y el término estimado no puede ser anterior al inicio; esta última
condición también se comprueba en la base de datos.

Las obras anteriores conservan sus datos y pueden consultarse aunque todavía no
tengan cliente, dirección, descripción o término estimado. Al editar se debe
completar la ficha. No se inventan clientes ni fechas para los registros antiguos.

## Clientes e historial

**Clientes e historial** permite registrar, buscar, consultar y editar clientes.
Cada ficha contiene nombre o razón social, RUT opcional, teléfono, correo,
dirección y notas. El RUT se normaliza para impedir duplicados con y sin puntos
o guion; se comprueba su formato, sin verificar su dígito contra una fuente
externa. Se admiten clientes homónimos y varios clientes sin RUT.

Seleccione la misma ficha de cliente en todas sus obras. Su historial muestra
obras activas e inactivas, número de obras, presupuesto acumulado, gastos y saldo.
Desde el historial se puede registrar una obra con ese cliente preseleccionado.
Los clientes no son cuentas de usuario y no necesitan iniciar sesión.

Desactivar una obra conserva su historial. La eliminación permanente de una obra
mantiene el comportamiento anterior: borra sus gastos, pagos e hitos. El cliente
permanece registrado. La relación `PROTECT` impide borrar un cliente con obras
vinculadas, incluso desde el administrador de Django.

## Permisos

| Perfil | Clientes e historial | Obras | Gastos y pagos |
| --- | --- | --- | --- |
| Administrador | Registrar, consultar y editar | Gestión completa | Registrar, editar y eliminar |
| Visualizador / Contador | Consultar | Consultar todas | Consultar |
| Empleado | Sin acceso | Consultar su obra asignada | Consultar sus pagos en el portal |

Las rutas comprueban el rol en el servidor y los formularios utilizan CSRF.

## Migración y activación

La migración `0005_clientes_y_ficha_obra` crea la tabla de clientes y añade los
campos de obra sin borrar ni reasignar registros existentes. En PostgreSQL con
roles de Supabase también activa RLS y revoca el acceso de `PUBLIC`, `anon` y
`authenticated` a la tabla nueva, siguiendo la protección del resto del sistema.

Con el entorno y la base de destino configurados, ejecute:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

La migración se verificó sobre SQLite aislado. No se aplicó a la base remota ni
se realizó un despliegue desde esta tarea.

## Diagrama de clases editable

Abra [diagrama-clases.drawio](diagrama-clases.drawio) en draw.io mediante
**Archivo → Abrir desde → Dispositivo**. Contiene objetos y conectores editables,
en tres páginas:

1. **Modelo de dominio:** todos los modelos de negocio y `User`, atributos,
   tipos, claves, métodos, propiedades calculadas, opciones, cardinalidades y
   comportamiento de eliminación.
2. **Autenticación y tablas de Django:** usuarios, grupos, permisos, tablas
   intermedias M:N, tipos de contenido, sesiones y registros del administrador.
3. **Formularios y control de la aplicación:** formularios, herencia, vistas,
   permisos, señales, contexto, middleware, configuración y clases del administrador.
   Las vistas basadas en funciones se identifican como módulos.

El diagrama se obtiene de las clases y funciones del repositorio. La API heredada
del framework se resume. Para regenerarlo después de cambiar el código:

```powershell
.\.venv\Scripts\python.exe -B scripts/generar_diagrama_clases.py
```

## Comprobaciones

```powershell
.\.venv\Scripts\python.exe -B manage.py check --settings=Proyecto.test_settings
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=Proyecto.test_settings
.\.venv\Scripts\python.exe -B manage.py test construApp --settings=Proyecto.test_settings --noinput
```

Las pruebas verifican la migración de datos anteriores, formularios, relaciones,
permisos, CSRF, cambios de cuenta, montos y saldos, historial con varias obras,
inactividad y confirmaciones de eliminación.

Con Playwright y WebKit instalados, la comprobación de interfaz se reproduce con:

```powershell
.\.venv\Scripts\python.exe -B scripts/verificar_funcionalidades_navegador.py
```

Ese script utiliza una base SQLite temporal con datos ficticios y un servidor
local que se cierra al terminar. Guarda capturas e informe en
`reports/funcionalidades-2026-11-18/`. Si hay una copia de Bootstrap 5.3.3 en esa
carpeta, sirve ese mismo CSS al navegador para validar el diseño cuando el entorno
de comprobación no tiene acceso al CDN.
