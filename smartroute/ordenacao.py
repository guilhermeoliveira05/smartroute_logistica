"""Merge Sort e Fila de Prioridade (Estrutura de Dados / Algorítmica)."""
from __future__ import annotations

import heapq
import itertools
from typing import Any, Callable, Iterable, List, Tuple


def merge_sort(itens: Iterable[Any], chave: Callable[[Any], Any] = lambda x: x) -> List[Any]:
    """Merge Sort estável, O(n log n)."""
    itens = list(itens)
    if len(itens) <= 1:
        return itens
    meio = len(itens) // 2
    esq = merge_sort(itens[:meio], chave)
    dir_ = merge_sort(itens[meio:], chave)
    resultado: List[Any] = []
    i = j = 0
    while i < len(esq) and j < len(dir_):
        if chave(esq[i]) <= chave(dir_[j]):
            resultado.append(esq[i])
            i += 1
        else:
            resultado.append(dir_[j])
            j += 1
    resultado.extend(esq[i:])
    resultado.extend(dir_[j:])
    return resultado


class FilaPrioridade:
    """Fila de prioridade (heap mínimo). Menor chave sai primeiro; empate = FIFO."""

    def __init__(self) -> None:
        self._heap: List[Tuple[Any, int, Any]] = []
        self._contador = itertools.count()

    def push(self, item: Any, prioridade: Any) -> None:
        heapq.heappush(self._heap, (prioridade, next(self._contador), item))

    def pop(self) -> Any:
        return heapq.heappop(self._heap)[2]

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)
