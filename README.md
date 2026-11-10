# Constructora LC

Aplicación Django para administrar proyectos, personal, gastos, pagos e hitos, con PostgreSQL alojado en Supabase.

## Permisos

| Rol | Proyectos | Usuarios | Finanzas y calendario |
| --- | --- | --- | --- |
| Administrador | Crear, consultar, editar, activar/desactivar y eliminar | Crear, consultar, editar roles y asignaciones, cambiar contraseñas, activar/desactivar y eliminar | Gestión completa |
| Visualizador / Contador | Consultar todas las obras | Sin acceso | Solo consulta |
| Empleado | Consultar exclusivamente su obra asignada y sus hitos | Sin acceso | En su portal ve exclusivamente los pagos vinculados a su cuenta |

Los permisos se comprueban en el servidor incluso si se escribe una URL directamente o se envía un formulario manualmente. Un administrador no puede eliminarse, desactivarse ni quitarse su propio rol. Solo los superusuarios pueden editar o eliminar otras cuentas de superusuario.

## Instalación

Requiere Python 3.12 o posterior. En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si el entorno virtual se copió desde otro computador, vuelva a crearlo con su instalación local de Python. El ejecutable de un entorno virtual no es portable.

Configure `.env` usando `.env.example` como referencia. No sobrescriba un `.env` que ya contenga su conexión. Use los datos de **Connect → Session pooler** en Supabase, incluyendo el usuario completo `postgres.PROJECT_REF`. El puerto habitual de ese pooler es `5432`. La conexión exige SSL por defecto; `DB_SSLMODE=disable` se reserva para PostgreSQL local sin SSL. Para el pooler se desactivan los cursores del servidor. [Documentación de conexiones de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

Con `DB_HOST` configurado, Django guarda las cuentas y todos los registros directamente en PostgreSQL de Supabase. Sin `DB_HOST`, el proyecto usa SQLite para desarrollo local.

La autenticación usa **Django Auth**: las cuentas están en `public.auth_user` y sus roles/asignaciones en `public.construApp_perfilusuario`. No se crean cuentas en Supabase Authentication (`auth.users`), porque la aplicación utiliza sesiones y contraseñas de Django.

## Migraciones y puesta en marcha

### Despliegue en Render

Suba estos cambios al repositorio conectado a Render. Cree un **Web Service**
con lenguaje **Python 3** y deje **Root Directory** vacío si `manage.py`
está en la raíz del repositorio. Configure:

| Campo | Valor |
| --- | --- |
| Build Command | `bash build.sh` |
| Start Command | `gunicorn Proyecto.wsgi:application --bind 0.0.0.0:$PORT` |

En **Environment**, añada `SECRET_KEY` (use **Generate**), `DEBUG=false` y
las variables `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` y
`DB_SSLMODE` de su conexión actual a Supabase. Use el **Session pooler**,
puerto `5432` y `DB_SSLMODE=require`. Copie los valores desde su `.env`
al panel, sin subir ese archivo al repositorio.

También puede crear un **Blueprint** desde el archivo `render.yaml`: solicita
las credenciales de Supabase y genera la clave secreta automáticamente.
No crea otra base de datos. `.python-version` selecciona Python 3.13.

El build instala dependencias, recopila archivos estáticos y ejecuta las
migraciones pendientes sobre la base configurada. Si ya usa esa base localmente,
el despliegue comparte sus cuentas y registros. En Render se exige PostgreSQL
para evitar guardar datos en un SQLite que se perdería al redesplegar.

Render proporciona `RENDER_EXTERNAL_HOSTNAME`; Django permite ese dominio y
configura HTTPS y cookies seguras automáticamente. Para un dominio propio,
añada `ALLOWED_HOSTS=su-dominio.cl` y
`CSRF_TRUSTED_ORIGINS=https://su-dominio.cl` (listas separadas por comas).
Gunicorn sirve la aplicación y WhiteNoise sirve los archivos estáticos,
incluidos los del administrador de Django.

Referencias: [Django en Render](https://render.com/docs/deploy-django) y
[servicios web](https://render.com/docs/web-services).

La migración `0003_completar_perfiles_usuarios` crea los perfiles que falten para cuentas existentes. Las cuentas nuevas reciben su perfil automáticamente, incluidas las creadas mediante `createsuperuser` o el administrador de Django.

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

No repita `createsuperuser` si ya tiene un administrador. Inicie sesión en `/login/`; desde **Obras y presupuestos** (`/proyectos/`) y **Usuarios y personal** (`/usuarios/`) puede gestionar las obras, cuentas y asignaciones.

### Protección de la API de Supabase

La migración `0004_proteger_tablas_supabase` cierra el acceso de la Data API a las 15 tablas de Django indicadas en el archivo: activa RLS y revoca los privilegios de `PUBLIC`, `anon` y `authenticated`. El backend conserva su acceso mediante la conexión PostgreSQL del servidor. No se crean políticas basadas en `auth.uid()`, porque las identidades de esta aplicación pertenecen a Django.

**Aplicada y verificada en la base remota de Supabase el 9 de noviembre de 2026, con autorización del usuario.** Las 15 tablas tienen RLS activo y los roles `anon` y `authenticated` no conservan privilegios de tabla ni de columna. Los clientes que utilizan las claves públicas de Supabase no pueden consultar ni modificar esas tablas directamente; las operaciones pasan por el backend y sus controles de sesión y rol. No cambia las tablas del esquema `auth` de Supabase. La migración es irreversible desde Django para que una reversión de código no vuelva a exponer cuentas y sesiones.

En otra instalación con una base nueva, `python manage.py migrate` aplica también esta protección. Para consultar el estado:

```powershell
python manage.py showmigrations construApp
```

Use las migraciones de Django como fuente de verdad de este backend. El SQL inicial en `supabase/migrations/` conserva el esquema original; no debe volver a ejecutarse sobre una base ya migrada.

## Validación y comportamiento

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run --settings=Proyecto.test_settings
python manage.py test construApp --settings=Proyecto.test_settings
```

Las pruebas usan una base SQLite temporal en memoria, sin crear tablas ni datos de pruebas en Supabase. Comprueban el CRUD, validaciones, roles, aislamiento de empleados, cambios de contraseña y protección CSRF.

Las cuentas y perfiles se guardan en una transacción: si falla el perfil, se revierte también la cuenta. Se validan contraseñas y su confirmación, roles, obras seleccionadas, fechas, presupuestos y nombres duplicados. Al editar, dejar ambas contraseñas vacías conserva la actual.

Las eliminaciones requieren confirmación y un POST con CSRF. Eliminar una obra elimina sus gastos, pagos e hitos y deja al personal sin esa asignación; desactivarla permite conservar el historial. Eliminar un usuario conserva sus pagos con el nombre del trabajador y elimina la vinculación a su cuenta.
