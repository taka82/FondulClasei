"""Punct de intrare WSGI pentru hosting (ex: PythonAnywhere)."""
from werkzeug.middleware.proxy_fix import ProxyFix

from app import app

# Hostingul pune aplicatia in spatele unui proxy: fara ProxyFix toti utilizatorii ar aparea
# cu acelasi IP (limita de incercari de login i-ar bloca pe toti deodata) si cu HTTP in loc de HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config["SESSION_COOKIE_SECURE"] = True

application = app
