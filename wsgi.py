"""Punct de intrare WSGI pentru hosting (ex: PythonAnywhere)."""
from werkzeug.middleware.proxy_fix import ProxyFix

from app import app

# Hostingul pune aplicatia in spatele unui proxy: fara ProxyFix toti utilizatorii ar aparea
# cu acelasi IP (limita de incercari de login i-ar bloca pe toti deodata) si cu HTTP in loc de HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config["SESSION_COOKIE_SECURE"] = True

# Pe un server public, primul cont de casier NU se creeaza din browser (oricine ar putea ajunge primul
# la pagina /setup), ci din consola: python3 create_admin.py
app.config["WEB_SETUP"] = False


@app.after_request
def hsts(resp):
    """Browserul retine ca site-ul se deschide doar prin HTTPS."""
    resp.headers["Strict-Transport-Security"] = "max-age=15552000"
    return resp


application = app
