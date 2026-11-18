# Despliegue verificado — 11 de noviembre de 2026

La aplicación publicada en https://proyecto-integrado-1.onrender.com sirve el commit **42c8e83da580f55a5595119403a78aacc624f61f**, publicado en la rama `main` de `XDedero/proyecto-integrado`.

El panel de Render mostró el build correcto completado y el despliegue de ese commit. El endpoint público `/health/` confirmó HTTP 200, revisión coincidente y conexión con la base de datos. Esta verificación reemplaza el estado «pendiente de despliegue» del informe inicial de auditoría.

## Validaciones

- **67 pruebas automáticas Django aprobadas** antes de publicar; comprobación del sistema y coherencia de migraciones correctas.
- **50 comprobaciones de navegador en producción aprobadas** con Edge: inicio y cierre de sesión, rutas administrativas, creación y edición de una obra y un empleado, compra de materiales, pago al empleado, saldo, calendario, cambio de campos mediante JavaScript, portal del empleado, permisos, CSRF y eliminación.
- **Eliminación de usuario:** confirmación correcta, pagos históricos conservados, sesión de cuenta eliminada invalidada y repetición de GET/POST sin 404. Se comprobó también el enlace reportado `/usuarios/10/eliminar/` mediante GET autenticado.
- **Eliminación de proyecto:** confirmación correcta, eliminación de gastos/pagos/hitos temporales y repetición de GET/POST sin 404.
- **16 solicitudes públicas adicionales:** rutas privadas protegidas, archivos sensibles inaccesibles, estáticos disponibles y formularios sin CSRF rechazados con 403. Sin respuestas 500 ni trazas internas expuestas.
- Sin excepciones JavaScript ni respuestas 500 durante el flujo de navegador.
- Páginas dinámicas con `Cache-Control: no-store, private`.

## Limpieza y alcance

Se creó una cuenta administrativa temporal para la verificación, un empleado y una obra con nombres aleatorios. Se eliminaron al terminar: **0 cuentas y 0 proyectos temporales restantes**. Sus registros de gasto, pago e hito también se eliminaron. No se cambiaron contraseñas ni se eliminaron cuentas u obras preexistentes. La SQLite local se conserva y quedó retirada del seguimiento de Git.

Las pruebas funcionales aprobadas no resuelven las tareas de seguridad pendientes del informe inicial: limitación de intentos de acceso, revisión de copias históricas de SQLite en Git y configuración de correo de producción si se habilitan envíos. No se alteraron esos servicios ni se reescribió el historial.

Resultados detallados en `despliegue-2026-11-11.json` y `despliegue-2026-11-11-publico.json`. La prueba previa de navegador con SQLite aislada se conserva en `prueba-navegador-local-2026-11-11.json`.
