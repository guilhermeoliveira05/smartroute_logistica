import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartroute import create_app
from smartroute.graph import Grafo, No
from smartroute.physics import Veiculo, veiculos_padrao


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "teste.db"))
    app.testing = True
    return app.test_client()


@pytest.fixture
def veiculos():
    return [Veiculo(id=i + 1, **v) for i, v in enumerate(veiculos_padrao())]


@pytest.fixture
def grafo_pequeno():
    """A--B--C em linha (1 km cada) + atalho direto A--C de 3 km (mais longo)."""
    g = Grafo()
    for i, nid in enumerate("ABC"):
        g.adicionar_no(No(nid, nid, 0.0, float(i)))
    g.adicionar_aresta("A", "B", 1.0, 40)
    g.adicionar_aresta("B", "C", 1.0, 40)
    g.adicionar_aresta("A", "C", 3.0, 40)
    return g
