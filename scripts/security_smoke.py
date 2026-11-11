"""Comprobaciones públicas acotadas; no inicia sesión ni modifica registros."""

import argparse
import json
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SinRedireccion(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    args = parser.parse_args()
    if urlsplit(args.base_url).scheme not in ("https", "http"):
        parser.error("Se requiere una URL HTTP(S).")
    opener = build_opener(SinRedireccion())
    resultados = []
    rutas = ("/login/", "/", "/proyectos/", "/proyectos/6/eliminar/", "/usuarios/", "/finanzas/", "/calendario/", "/mi-portal/", "/admin/", "/.env", "/.git/config", "/db.sqlite3", "/auditoria-ruta-inexistente/", "/static/admin/css/base.css")
    for ruta, metodo in [(ruta, "GET") for ruta in rutas] + [("/login/", "POST"), ("/finanzas/", "POST")]:
        peticion = Request(urljoin(args.base_url, ruta), method=metodo, data=b"" if metodo == "POST" else None, headers={"User-Agent": "ConstructoraCL-security-check/1.0"})
        try:
            respuesta = opener.open(peticion, timeout=30)
        except HTTPError as error:
            respuesta = error
        with respuesta:
            cuerpo = respuesta.read(1024 * 1024)
            cookies = SimpleCookie()
            for cookie in respuesta.headers.get_all("Set-Cookie", []):
                cookies.load(cookie)
            resultados.append({
                "path": ruta, "method": metodo, "status": respuesta.status,
                "headers": {nombre: respuesta.headers.get(nombre) for nombre in ("Location", "Strict-Transport-Security", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Cache-Control")},
                "cookie_flags": {nombre: {"secure": bool(cookie["secure"]), "httponly": bool(cookie["httponly"]), "samesite": cookie["samesite"]} for nombre, cookie in cookies.items()},
                "traceback_exposed": b"Traceback (most recent call last)" in cuerpo or b"Technical 500" in cuerpo,
                "sqlite_exposed": cuerpo.startswith(b"SQLite format 3"),
            })
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
