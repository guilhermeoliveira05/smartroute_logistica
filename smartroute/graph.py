"""Grafo ponderado (lista de adjacências) que modela a malha viária.

Cada trecho de via é guardado nos dois sentidos (vias de mão dupla). Os pesos
são dinâmicos: velocidade média (trânsito) e bloqueio (obras/acidentes) podem
mudar a qualquer momento sem reconstruir o grafo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass
class No:
    id: str
    nome: str
    lat: float
    lon: float
    deposito: bool = False


@dataclass
class Aresta:
    origem: str
    destino: str
    dist_km: float
    vel_kmh: float
    bloqueada: bool = False


class Grafo:
    def __init__(self) -> None:
        self.nos: Dict[str, No] = {}
        self.adj: Dict[str, List[Aresta]] = {}

    # ---- construção -----------------------------------------------------
    def adicionar_no(self, no: No) -> None:
        self.nos[no.id] = no
        self.adj.setdefault(no.id, [])

    def adicionar_aresta(self, u: str, v: str, dist_km: float, vel_kmh: float) -> None:
        if u not in self.nos or v not in self.nos:
            raise KeyError(f"Nó inexistente: {u} ou {v}")
        self.adj[u].append(Aresta(u, v, dist_km, vel_kmh))
        self.adj[v].append(Aresta(v, u, dist_km, vel_kmh))

    # ---- consulta -------------------------------------------------------
    def vizinhos(self, u: str) -> Iterator[Aresta]:
        """Arestas de saída de u, ignorando as vias bloqueadas."""
        for a in self.adj[u]:
            if not a.bloqueada:
                yield a

    def aresta(self, u: str, v: str) -> Optional[Aresta]:
        for a in self.adj.get(u, []):
            if a.destino == v:
                return a
        return None

    def arestas_unicas(self) -> List[Aresta]:
        """Uma aresta por trecho (evita duplicar os dois sentidos)."""
        return [a for u in self.adj for a in self.adj[u] if a.origem < a.destino]

    # ---- bloqueio de vias -----------------------------------------------
    def definir_bloqueio(self, u: str, v: str, bloqueada: bool = True) -> bool:
        a, b = self.aresta(u, v), self.aresta(v, u)
        if a is None or b is None:
            return False
        a.bloqueada = b.bloqueada = bloqueada
        return True

    def bloqueios(self) -> List[Tuple[str, str]]:
        return [(a.origem, a.destino) for a in self.arestas_unicas() if a.bloqueada]
