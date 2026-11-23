"""Inicia o servidor de desenvolvimento: python run.py  ->  http://127.0.0.1:5000"""
import os

from smartroute import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=debug)
