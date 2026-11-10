"""Funções de custo por aresta, injetadas no Dijkstra."""
from __future__ import annotations

from typing import Callable

from .graph import Aresta
from .physics import Veiculo, litros_trecho

MODOS = ("energia", "distancia", "tempo")


def vel_efetiva(veic: Veiculo, aresta: Aresta) -> float:
    """Velocidade praticada no trecho: limitada pela via (trânsito) e pelo veículo."""
    return max(5.0, min(aresta.vel_kmh, veic.vmax_kmh))


def tempo_trecho_min(dist_km: float, v_kmh: float) -> float:
    return dist_km / v_kmh * 60.0


def criar_custo(modo: str, veic: Veiculo, carga_kg: float) -> Callable[[Aresta], float]:
    if modo == "distancia":
        return lambda a: a.dist_km
    if modo == "tempo":
        return lambda a: tempo_trecho_min(a.dist_km, vel_efetiva(veic, a))
    if modo == "energia":
        return lambda a: litros_trecho(veic, carga_kg, a.dist_km, vel_efetiva(veic, a))
    raise ValueError(f"Modo de custo inválido: {modo}")
