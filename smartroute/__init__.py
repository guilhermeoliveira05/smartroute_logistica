"""SmartRoute Logística - roteirização inteligente com eficiência energética."""
from __future__ import annotations

import os
from typing import Optional

from flask import Flask, render_template

from .db import Repo
from .enderecos import IndiceEnderecos
from .malha import criar_malha


def create_app(db_path: Optional[str] = None) -> Flask:
    app = Flask(__name__)
    if db_path is None:
        db_path = os.environ.get(
            "SMARTROUTE_DB",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "smartroute.db"),
        )
    app.config["REPO"] = Repo(db_path)

    indice = IndiceEnderecos()                       # árvore (Trie) de endereços
    for no in criar_malha().nos.values():
        indice.inserir(no.nome, no.id)
    app.config["INDICE"] = indice

    from .api import bp
    app.register_blueprint(bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    return app
