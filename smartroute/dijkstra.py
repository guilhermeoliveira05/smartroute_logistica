"""Algoritmo de Dijkstra com heap mínimo.

Complexidade: O((V + E) log V). A função de custo é injetável, então o mesmo
algoritmo minimiza distância, tempo ou consumo de combustível (Física II).
Os custos precisam ser não negativos.
"""
from __future__ import annotations

import heapq
import math
from typing import Callable, Dict, List, Optional, Tuple

from .graph import Aresta, Grafo

FuncaoCusto = Callable[[Aresta], float]


def dijkstra(
    grafo: Grafo,
    origem: str,
    custo: FuncaoCusto,
    destino: Optional[str] = None,
) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Retorna (dist, prev). Nós inalcançáveis não aparecem em ``dist``."""
    dist: Dict[str, float] = {origem: 0.0}
    prev: Dict[str, str] = {}
    visitados = set()
    heap: List[Tuple[float, str]] = [(0.0, origem)]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visitados:
            continue
        visitados.add(u)
        if destino is not None and u == destino:
            break
        for a in grafo.vizinhos(u):
            nd = d + custo(a)
            if nd < dist.get(a.destino, math.inf):
                dist[a.destino] = nd
                prev[a.destino] = u
                heapq.heappush(heap, (nd, a.destino))
    return dist, prev


def reconstruir_caminho(prev: Dict[str, str], origem: str, destino: str) -> Optional[List[str]]:
    """Lista de nós de origem até destino, ou None se não houver caminho."""
    if origem == destino:
        return [origem]
    if destino not in prev:
        return None
    caminho = [destino]
    while caminho[-1] != origem:
        caminho.append(prev[caminho[-1]])
    caminho.reverse()
    return caminho


def menor_caminho(
    grafo: Grafo, origem: str, destino: str, custo: FuncaoCusto
) -> Tuple[Optional[List[str]], float]:
    dist, prev = dijkstra(grafo, origem, custo, destino)
    if destino not in dist:
        return None, math.inf
    return reconstruir_caminho(prev, origem, destino), dist[destino]
