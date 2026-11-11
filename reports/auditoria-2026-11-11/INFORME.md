# Auditoría funcional y de seguridad — 11 de noviembre de 2026

Se revisó el código local basado en el commit `90e9b42`, se ampliaron las pruebas y se corrigieron los defectos reproducidos. Los cambios de esta auditoría **todavía no están desplegados en Render**.

## Resultado

| Comprobación | Resultado |
| --- | --- |
| Pruebas automáticas Django | **61 aprobadas**, sin fallos ni errores |
| Cobertura de código de aplicación | **94,17 %** combinando líneas y ramas; 95,57 % de líneas y 88,33 % de ramas |
| Análisis estático Bandit | **0 hallazgos**, 0 errores del analizador |
| Dependencias instaladas, incluidos los instrumentos de auditoría | **41 paquetes, 0 avisos conocidos** tras actualizar pip |
| Consistencia de dependencias | `pip check` sin conflictos |
| Comprobación normal Django | Sin incidencias |
| Migraciones del código | Sin cambios pendientes de generar |
| Comprobaciones públicas de Render | 16 solicitudes acotadas; respuestas esperadas, sin errores 500 |
| RLS y permisos de Supabase | **15 tablas / 30 combinaciones tabla–rol correctas**, en transacción de solo lectura |

La cobertura excluye tests y migraciones. No equivale a probar todas las combinaciones posibles de entradas ni a certificar ausencia de vulnerabilidades. Bandit y pip-audit tampoco sustituyen las pruebas de autorización y lógica de negocio. [Alcance de pip-audit](https://github.com/pypa/pip-audit#readme).

## Defectos corregidos

| Hallazgo reproducido | Corrección local |
| --- | --- |
| Finanzas podía producir 500 ante montos no numéricos, fechas incorrectas e identificadores manipulados | Validación de formularios antes de consultar o guardar |
| Se admitían categorías y tipos de egreso arbitrarios, textos vacíos o demasiado largos | Campos con opciones, obligatoriedad y longitudes comprobadas en servidor |
| Un pago podía vincularse a una cuenta ajena al rol de empleado, inexistente o desactivada | Selección restringida a empleados activos; también se conserva la posibilidad de registrar un trabajador sin cuenta |
| Valores aceptados por SQLite podían superar el rango de enteros de PostgreSQL | Máximo de 2.147.483.647 CLP para presupuestos y egresos, acorde a los campos actuales |
| Los errores de formulario no se mostraban de forma consistente ni conservaban los valores enviados | Mensajes visibles y campos vinculados al formulario; el tipo de egreso seleccionado se conserva |
| Una eliminación concurrente de relaciones podía producir un error de integridad al crear un egreso o hito | Transacción y mensaje controlado; sin escritura parcial |
| Algunas vistas aceptaban métodos HTTP que no utilizaban | Respuesta 405 para métodos no admitidos |
| Las páginas privadas no indicaban al navegador que evitara almacenarlas | Middleware `Cache-Control: no-store, private` para respuestas dinámicas; WhiteNoise conserva el manejo de estáticos |
| `pip` local 25.2 tenía avisos de seguridad conocidos | Actualizado a 26.3; el build exige una versión de la serie 26 desde 26.2 |
| `db.sqlite3` estaba versionada y contiene dos cuentas | Retirada del índice de Git, manteniendo intacto el archivo local e ignorando futuras incorporaciones |

## Riesgos y tareas pendientes

1. **Prioridad alta: datos históricos en Git.** Retirar `db.sqlite3` del índice evita incluirla en versiones futuras cuando se confirme el cambio, pero **no la elimina de commits anteriores, clones o copias**. Si esas cuentas son reales o reutilizan contraseñas, cambiar sus contraseñas y revisar la exposición del repositorio. Cualquier limpieza del historial debe coordinarse antes de reescribirlo. No se extrajeron nombres, hashes ni contraseñas al informe, ni se reescribió el historial.
2. **Prioridad alta: protección contra intentos repetidos de acceso pendiente.** La aplicación no implementa limitación de intentos en `/login/` ni una protección adicional para el login del administrador. En SQLite temporal, siete contraseñas erróneas devolvieron 200 y la siguiente correcta permitió entrar. Esto demuestra ausencia de bloqueo en ese escenario local, no un acceso sin contraseña ni la ausencia de posibles límites externos de Render. Implementar una limitación temporal compartida entre procesos y comprobar su recuperación y resistencia a bloqueos abusivos. [Recomendaciones de seguridad de Django](https://docs.djangoproject.com/en/6.1/topics/security/).
3. **Correo de producción pendiente.** La comprobación del perfil Render simulado detecta `mail.E001`: `MAILERS` utiliza el backend de consola. El código actual no ofrece envíos de correo ni recuperación por email; si se incorporan, requieren un proveedor y configuración de producción. No se ocultó esta incidencia ni se configuró un SMTP ficticio para aprobar la comprobación.
4. **Recomendaciones HSTS, no fallos del CRUD:** el perfil simulado emite `security.W005` y `security.W021` por no usar `includeSubDomains` ni preload. No se activaron automáticamente; requieren evaluar el dominio y sus subdominios. El sitio publicado sí entrega `Strict-Transport-Security: max-age=3600`.
5. **Despliegue pendiente.** Las correcciones de validación, caché y build deben confirmarse en Git, subirse y desplegarse antes de estar disponibles en la web pública. La comprobación pública corresponde a la versión que Render servía al realizar la auditoría.

## Funcionalidades y controles comprobados

- Login de administrador, visualizador y empleado, redirección por rol, contraseña incorrecta y mensaje genérico ante usuario inexistente.
- Logout por POST y cancelación de sesión; invalidación de sesiones al desactivar una cuenta o cambiar su contraseña.
- Creación, detalle, edición, activación/desactivación y eliminación de proyectos; repetición de eliminación y proyectos inexistentes.
- Creación y edición de cuentas, roles, contraseñas y asignaciones; eliminación de usuarios manteniendo los pagos históricos.
- Protección del propio administrador y de cuentas de superusuario; campos extra no permiten elevar privilegios.
- Registro de compras y pagos con/sin cuenta de trabajador, totales y saldo; propagación del pago al portal correcto.
- Creación y visualización de hitos; fechas límite, alertas de color y aislamiento de obras.
- Eliminación en cascada de gastos, pagos e hitos; conservación y desasignación de cuentas.
- Acceso directo por URL y POST con roles de lectura; aislamiento de proyectos, presupuestos, pagos e hitos del empleado.
- Rechazo de formularios sin CSRF y con origen ajeno; aceptación de un formulario con token válido.
- Escape de HTML persistente en proyectos, páginas de confirmación y mensajes; entradas con patrones de inyección SQL no autentican ni se aceptan como identificadores.
- Métodos HTTP no admitidos, cabeceras anti-clickjacking, `nosniff`, política de referencia y caché de páginas privadas.
- Render: login accesible, rutas privadas redirigen, `.env`, `.git/config` y `db.sqlite3` devuelven 404; estáticos disponibles; POST sin CSRF devuelve 403; no se observaron trazas internas.
- Supabase: RLS activo y sin permisos de tabla ni columna para `anon` y `authenticated` en las 15 tablas comprobadas. La consulta utilizó `transaction_read_only=on`.

## Alcance y límites

Los CRUD y las pruebas de entradas manipuladas se ejecutaron en SQLite temporal, sin modificar cuentas ni registros de Supabase. La consulta de permisos remotos fue de solo lectura. En Render solo se hicieron GET públicos y dos POST vacíos rechazados por CSRF; no se probaron contraseñas reales ni se ejecutaron pruebas de carga.

Se probaron las vistas y plantillas con el cliente de Django; no se automatizó un navegador real ni se validó visualmente cada tamaño de pantalla. No se ejecutó la batería de CRUD contra PostgreSQL ni contra una sesión autenticada de Render. La auditoría de paquetes no cubre vulnerabilidades del intérprete Python, el sistema operativo o la infraestructura de Render. No se verificaron privilegios personalizados de otros roles de PostgreSQL ni datos de servicios ajenos al proyecto.

## Reproducir

En PowerShell desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B manage.py test construApp --settings=Proyecto.test_settings
.\.venv\Scripts\python.exe -B -m coverage run --branch --source=construApp manage.py test construApp --settings=Proyecto.test_settings
.\.venv\Scripts\python.exe -B -m coverage report --omit='*/tests.py,*/test_auditoria.py,*/migrations/*'
.\.venv\Scripts\python.exe -B -m bandit -r construApp Proyecto scripts -x construApp/tests.py,construApp/test_auditoria.py
.\.venv\Scripts\python.exe -B -m pip_audit
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=Proyecto.test_settings
.\.venv\Scripts\python.exe -B scripts/check_login_throttle.py
.\.venv\Scripts\python.exe -B scripts/security_smoke.py https://proyecto-integrado-1.onrender.com
.\.venv\Scripts\python.exe -B scripts/check_database_security.py
```

Los dos últimos comandos requieren red; el de base de datos utiliza la conexión configurada en `.env` y solo consulta permisos. Los resultados están en `coverage.json`, `bandit.json`, `dependencias.json`, `login-throttle.json`, `render.json` y `supabase.json`, sin valores de cookies ni credenciales.
