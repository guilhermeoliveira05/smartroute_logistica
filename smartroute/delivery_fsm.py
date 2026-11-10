"""AFD (Autômato Finito Determinístico) dos estados de uma entrega.

    Q  = {AGUARDANDO_SAIDA, EM_ROTA, ENTREGUE, FINALIZADO}
    Σ  = {iniciar_viagem, chegar_destino, proxima_entrega}
    q0 = AGUARDANDO_SAIDA        F = {FINALIZADO}

    δ(AGUARDANDO_SAIDA, iniciar_viagem) = EM_ROTA
    δ(EM_ROTA,          chegar_destino) = ENTREGUE
    δ(ENTREGUE,         proxima_entrega) = FINALIZADO

Como o autômato é finito e determinístico, "esta sequência de eventos é válida?"
é sempre decidível em tempo linear no tamanho da sequência.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, Iterable, Optional, Tuple


class Estado(IntEnum):
    AGUARDANDO_SAIDA = 0
    EM_ROTA = 1
    ENTREGUE = 2
    FINALIZADO = 3


ROTULOS = {
    Estado.AGUARDANDO_SAIDA: "Aguardando saída",
    Estado.EM_ROTA: "Em rota",
    Estado.ENTREGUE: "Entregue",
    Estado.FINALIZADO: "Finalizado",
}

EVENTOS = ("iniciar_viagem", "chegar_destino", "proxima_entrega")

TRANSICOES: Dict[Tuple[Estado, str], Estado] = {
    (Estado.AGUARDANDO_SAIDA, "iniciar_viagem"): Estado.EM_ROTA,
    (Estado.EM_ROTA, "chegar_destino"): Estado.ENTREGUE,
    (Estado.ENTREGUE, "proxima_entrega"): Estado.FINALIZADO,
}


class TransicaoInvalida(ValueError):
    pass


class AFD:
    estado_inicial = Estado.AGUARDANDO_SAIDA
    estados_finais = frozenset({Estado.FINALIZADO})

    @staticmethod
    def transicao(estado: int, evento: str) -> Estado:
        try:
            return TRANSICOES[(Estado(estado), evento)]
        except (KeyError, ValueError):
            raise TransicaoInvalida(
                f"Evento '{evento}' não é permitido no estado "
                f"'{ROTULOS.get(Estado(estado), estado)}'."
            ) from None

    @classmethod
    def aceita(cls, eventos: Iterable[str]) -> bool:
        """True se a sequência leva do estado inicial a um estado final."""
        estado = cls.estado_inicial
        for ev in eventos:
            try:
                estado = cls.transicao(estado, ev)
            except TransicaoInvalida:
                return False
        return estado in cls.estados_finais

    @staticmethod
    def evento_esperado(estado: int) -> Optional[str]:
        """Único evento válido no estado (o AFD é determinístico e linear)."""
        for (q, ev) in TRANSICOES:
            if q == Estado(estado):
                return ev
        return None

    @staticmethod
    def para_mermaid() -> str:
        linhas = ["stateDiagram-v2", f"    [*] --> {Estado.AGUARDANDO_SAIDA.name}"]
        for (q, ev), r in TRANSICOES.items():
            linhas.append(f"    {q.name} --> {r.name}: {ev}")
        linhas.append(f"    {Estado.FINALIZADO.name} --> [*]")
        return "\n".join(linhas)
