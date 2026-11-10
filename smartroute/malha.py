"""Malha viária sintética da região da Construlog (~15 km²).

Grade 7x7 de cruzamentos (Av. A-G x Rua 1-7), espaçados ~645 m, com duas
vias arteriais (Av. D e Rua 4), uma avenida diagonal e velocidades médias
variando por trecho (trânsito). O depósito fica no centro (Av. D x Rua 4).
Coordenadas centradas em Lorena-SP apenas para o mapa ter onde desenhar;
a malha é fictícia, como a empresa parceira.
"""
from __future__ import annotations

import math
import random

from .config import DEPOSITO_ID
from .graph import Grafo, No

N = 7
LAT0, LON0 = -22.7308, -45.1246
ESPACAMENTO_KM = 0.645


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _id(r: int, c: int) -> str:
    return f"N{r}{c}"


def criar_malha(seed: int = 42) -> Grafo:
    rng = random.Random(seed)
    g = Grafo()
    dlat = ESPACAMENTO_KM / 111.32
    dlon = ESPACAMENTO_KM / (111.32 * math.cos(math.radians(LAT0)))
    centro = N // 2

    for r in range(N):
        for c in range(N):
            nid = _id(r, c)
            nome = f"Av. {chr(65 + c)} x Rua {r + 1}"
            g.adicionar_no(
                No(nid, nome, LAT0 + (centro - r) * dlat, LON0 + (c - centro) * dlon,
                   deposito=(nid == DEPOSITO_ID))
            )

    def vel(arterial: bool) -> float:
        base = 50 if arterial else rng.choice([30, 35, 40, 45])
        return max(15, round(base * rng.uniform(0.7, 1.0)))

    def ligar(u: str, v: str, arterial: bool) -> None:
        a, b = g.nos[u], g.nos[v]
        g.adicionar_aresta(u, v, round(haversine_km(a.lat, a.lon, b.lat, b.lon), 4), vel(arterial))

    for r in range(N):
        for c in range(N):
            if c + 1 < N:
                ligar(_id(r, c), _id(r, c + 1), arterial=(r == centro))
            if r + 1 < N:
                ligar(_id(r, c), _id(r + 1, c), arterial=(c == centro))
    for i in range(N - 1):                       # avenida diagonal
        ligar(_id(i, i), _id(i + 1, i + 1), arterial=True)
    return g
