"""Índice de endereços em árvore (Trie) para busca por prefixo.

Cada endereço é inserido a partir de cada palavra ("av c x rua 4", "c x rua 4",
"x rua 4", "rua 4", "4"), então o operador pode digitar o começo de qualquer
parte do endereço. A busca ignora acentos e maiúsculas.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Set


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(t.split())


class _NoTrie:
    __slots__ = ("filhos", "ids")

    def __init__(self) -> None:
        self.filhos: Dict[str, "_NoTrie"] = {}
        self.ids: Set[str] = set()


class IndiceEnderecos:
    def __init__(self) -> None:
        self.raiz = _NoTrie()

    def inserir(self, texto: str, id_: str) -> None:
        palavras = normalizar(texto).split(" ")
        for i in range(len(palavras)):
            self._inserir_chave(" ".join(palavras[i:]), id_)

    def _inserir_chave(self, chave: str, id_: str) -> None:
        no = self.raiz
        for ch in chave:
            no = no.filhos.setdefault(ch, _NoTrie())
        no.ids.add(id_)

    def buscar(self, prefixo: str, limite: int = 10) -> List[str]:
        """IDs cujo endereço contém uma palavra começando com ``prefixo``."""
        no = self.raiz
        for ch in normalizar(prefixo):
            no = no.filhos.get(ch)
            if no is None:
                return []
        achados: Set[str] = set()
        pilha = [no]
        while pilha:
            atual = pilha.pop()
            achados |= atual.ids
            pilha.extend(atual.filhos.values())
        return sorted(achados)[:limite]
