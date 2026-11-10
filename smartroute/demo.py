"""Gerador de entregas de demonstração (~35/dia, como a Construlog)."""
from __future__ import annotations

import random
from typing import Dict, List

from .graph import Grafo


def gerar_entregas_demo(grafo: Grafo, n: int = 35, seed: int = 7) -> List[Dict]:
    rng = random.Random(seed)
    nos = [no for no in grafo.nos.values() if not no.deposito]
    entregas = []
    for i in range(1, n + 1):
        no = rng.choice(nos)
        pesado = rng.random() < 0.25                      # sacos de cimento, tubos...
        peso = round(rng.uniform(80, 800), 1) if pesado else round(rng.uniform(2, 25), 1)
        prioridade = rng.choices([1, 2, 3], weights=[15, 65, 20])[0]
        if prioridade == 1:
            prazo = rng.randint(60, 180)
        elif prioridade == 2:
            prazo = rng.randint(240, 480)
        else:
            prazo = rng.choice([None, 480, 540])
        entregas.append(
            dict(cliente=f"Cliente {i:02d}", endereco=no.nome, no_id=no.id,
                 peso_kg=peso, prioridade=prioridade, prazo_min=prazo)
        )
    return entregas
