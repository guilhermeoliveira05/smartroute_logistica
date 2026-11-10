"""Roteirizador: atribui entregas a viagens, ordena paradas e traça os caminhos.

Pipeline (cada etapa usa uma das disciplinas do projeto):

1. Decidibilidade: entregas sem caminho a partir do depósito (vias bloqueadas)
   ou acima da capacidade são separadas como *inviáveis*; o sistema sempre termina.
2. Fila de Prioridade: entregas saem na ordem (prioridade, prazo, cadastro).
3. Atribuição gulosa a viagens (veículo + capacidade em kg + máximo de paradas),
   pelo menor custo marginal de combustível.
4. Ordem das paradas em cada viagem: prioridades urgentes primeiro; dentro de
   cada prioridade, vizinho mais próximo + 2-opt, avaliados com o custo REAL de
   energia (que depende da carga que ainda está no veículo).
5. Cada trecho entre paradas é um Dijkstra com custo físico (atrito + arrasto).
6. Linha de base "empírica" (ordem de cadastro, caminho mais curto em km) para
   medir a economia obtida.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import PRECO_COMBUSTIVEL_RS_L, TEMPO_SERVICO_MIN
from .custos import criar_custo, tempo_trecho_min, vel_efetiva
from .dijkstra import dijkstra, reconstruir_caminho
from .graph import Grafo
from .ordenacao import FilaPrioridade, merge_sort
from .physics import Veiculo, litros_trecho

INF = math.inf


def _custo_km(a) -> float:
    return a.dist_km


# --------------------------------------------------------------------------
# Estruturas de dados
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class EntregaPlan:
    id: int
    no: str
    peso_kg: float
    prioridade: int = 2
    prazo_min: Optional[float] = None


@dataclass
class Trecho:
    origem: str
    destino: str
    caminho: List[str]
    dist_km: float
    tempo_min: float
    litros: float
    carga_kg: float


@dataclass
class Metricas:
    dist_km: float = 0.0
    tempo_min: float = 0.0
    litros: float = 0.0
    custo_rs: float = 0.0


@dataclass
class Viagem:
    veiculo_id: int
    numero: int
    inicio_min: float
    paradas: List[EntregaPlan]
    trechos: List[Trecho]
    etas: Dict[int, float]
    fim_min: float
    metricas: Metricas
    baseline: Metricas

    @property
    def caminho(self) -> List[str]:
        """Sequência completa de nós (depósito -> paradas -> depósito)."""
        nos: List[str] = []
        for t in self.trechos:
            nos.extend(t.caminho if not nos else t.caminho[1:])
        return nos


@dataclass
class Plano:
    viagens: List[Viagem] = field(default_factory=list)
    inviaveis: List[Tuple[int, str]] = field(default_factory=list)

    def totais(self) -> Tuple[Metricas, Metricas]:
        otm, base = Metricas(), Metricas()
        for v in self.viagens:
            for dst, src in ((otm, v.metricas), (base, v.baseline)):
                dst.dist_km += src.dist_km
                dst.tempo_min += src.tempo_min
                dst.litros += src.litros
                dst.custo_rs += src.custo_rs
        return otm, base


# --------------------------------------------------------------------------
# Avaliação de custos (com cache de Dijkstra por origem e carga)
# --------------------------------------------------------------------------
class Avaliador:
    def __init__(self, grafo: Grafo, veiculo: Veiculo, modo: str = "energia") -> None:
        self.g = grafo
        self.v = veiculo
        self.modo = modo
        self._quantum = max(5.0, 0.01 * veiculo.capacidade_kg)
        self._cache: Dict[tuple, tuple] = {}

    def _sp(self, origem: str, carga: float, modo: str):
        # A escolha do caminho quase não muda com poucos kg de diferença:
        # agrupamos a carga em faixas para reaproveitar o Dijkstra.
        carga_ref = round(carga / self._quantum) * self._quantum if modo == "energia" else 0.0
        chave = (origem, modo, carga_ref)
        if chave not in self._cache:
            self._cache[chave] = dijkstra(self.g, origem, criar_custo(modo, self.v, carga_ref))
        return self._cache[chave]

    def custo(self, origem: str, destino: str, carga: float) -> float:
        dist, _ = self._sp(origem, carga, self.modo)
        return dist.get(destino, INF)

    def trecho(self, origem: str, destino: str, carga: float, modo: Optional[str] = None) -> Trecho:
        dist, prev = self._sp(origem, carga, modo or self.modo)
        caminho = reconstruir_caminho(prev, origem, destino) if destino in dist else None
        if caminho is None:
            raise ValueError(f"Sem caminho de {origem} até {destino}")
        d = t = litros = 0.0
        for a, b in zip(caminho, caminho[1:]):
            ar = self.g.aresta(a, b)
            v = vel_efetiva(self.v, ar)
            d += ar.dist_km
            t += tempo_trecho_min(ar.dist_km, v)
            litros += litros_trecho(self.v, carga, ar.dist_km, v)   # carga exata
        return Trecho(origem, destino, caminho, d, t, litros, carga)


# --------------------------------------------------------------------------
# Ordenação das paradas de uma viagem
# --------------------------------------------------------------------------
def _simular(aval: Avaliador, no0: str, carga0: float, t0: float,
             seq: Sequence[EntregaPlan], retorno_ao: Optional[str] = None):
    """Percorre ``seq`` e devolve (atrasos, custo, no_final, carga_final, t_final)."""
    custo, atrasos, no, carga, t = 0.0, 0, no0, carga0, t0
    for p in seq:
        custo += aval.custo(no, p.no, carga)
        t += aval.trecho(no, p.no, carga).tempo_min
        if p.prazo_min is not None and t > p.prazo_min:
            atrasos += 1
        t += TEMPO_SERVICO_MIN
        carga = max(0.0, carga - p.peso_kg)
        no = p.no
    if retorno_ao is not None:
        custo += aval.custo(no, retorno_ao, 0.0)
    return atrasos, custo, no, carga, t


def _dois_opt(aval, no0, carga0, t0, seq: List[EntregaPlan], retorno_ao) -> List[EntregaPlan]:
    if len(seq) < 3:
        return seq
    melhor = list(seq)
    m_atr, m_custo, *_ = _simular(aval, no0, carga0, t0, melhor, retorno_ao)
    for _ in range(30):
        melhorou = False
        for i in range(len(melhor) - 1):
            for j in range(i + 1, len(melhor)):
                cand = melhor[:i] + melhor[i:j + 1][::-1] + melhor[j + 1:]
                atr, custo, *_ = _simular(aval, no0, carga0, t0, cand, retorno_ao)
                if atr < m_atr or (atr == m_atr and custo < m_custo - 1e-9):
                    melhor, m_atr, m_custo, melhorou = cand, atr, custo, True
        if not melhorou:
            break
    return melhor


def ordenar_paradas(aval: Avaliador, deposito: str, paradas: List[EntregaPlan],
                    inicio_min: float) -> List[EntregaPlan]:
    grupos: Dict[int, List[EntregaPlan]] = {}
    for p in paradas:
        grupos.setdefault(p.prioridade, []).append(p)

    ordem: List[EntregaPlan] = []
    no, carga, t = deposito, sum(p.peso_kg for p in paradas), inicio_min
    prioridades = sorted(grupos)
    for k, prio in enumerate(prioridades):
        grupo = merge_sort(grupos[prio], lambda p: (p.prazo_min if p.prazo_min is not None else INF, p.id))
        # vizinho mais próximo com custo real de energia (carga atual)
        restantes, seq, n_at, c_at = list(grupo), [], no, carga
        while restantes:
            prox = min(restantes, key=lambda p: (aval.custo(n_at, p.no, c_at),
                                                 p.prazo_min if p.prazo_min is not None else INF, p.id))
            restantes.remove(prox)
            seq.append(prox)
            n_at, c_at = prox.no, max(0.0, c_at - prox.peso_kg)
        ultimo_grupo = k == len(prioridades) - 1
        seq = _dois_opt(aval, no, carga, t, seq, deposito if ultimo_grupo else None)
        _, _, no, carga, t = _simular(aval, no, carga, t, seq)
        ordem.extend(seq)
    return ordem


# --------------------------------------------------------------------------
# Montagem de viagem + linha de base
# --------------------------------------------------------------------------
def _percorrer(aval: Avaliador, deposito: str, ordem: Sequence[EntregaPlan], modo: str) -> List[Trecho]:
    carga = sum(p.peso_kg for p in ordem)
    no, trechos = deposito, []
    for p in ordem:
        trechos.append(aval.trecho(no, p.no, carga, modo))
        carga, no = max(0.0, carga - p.peso_kg), p.no
    trechos.append(aval.trecho(no, deposito, 0.0, modo))
    return trechos


def _metricas(trechos: Sequence[Trecho], n_paradas: int, preco: float) -> Metricas:
    litros = sum(t.litros for t in trechos)
    return Metricas(
        dist_km=sum(t.dist_km for t in trechos),
        tempo_min=sum(t.tempo_min for t in trechos) + n_paradas * TEMPO_SERVICO_MIN,
        litros=litros,
        custo_rs=litros * preco,
    )


def _montar_viagem(g: Grafo, deposito: str, veic: Veiculo, numero: int, inicio: float,
                   paradas: List[EntregaPlan], modo: str, preco: float) -> Viagem:
    aval = Avaliador(g, veic, modo)
    ordem = ordenar_paradas(aval, deposito, paradas, inicio)
    trechos = _percorrer(aval, deposito, ordem, modo)

    etas: Dict[int, float] = {}
    t = inicio
    for p, tr in zip(ordem, trechos):
        t += tr.tempo_min
        etas[p.id] = t
        t += TEMPO_SERVICO_MIN
    t += trechos[-1].tempo_min

    ordem_base = sorted(paradas, key=lambda p: p.id)          # ordem de cadastro (empírica)
    trechos_base = _percorrer(aval, deposito, ordem_base, "distancia")
    return Viagem(
        veiculo_id=veic.id, numero=numero, inicio_min=inicio, paradas=ordem, trechos=trechos,
        etas=etas, fim_min=t, metricas=_metricas(trechos, len(ordem), preco),
        baseline=_metricas(trechos_base, len(ordem), preco),
    )


# --------------------------------------------------------------------------
# Planejamento completo
# --------------------------------------------------------------------------
def planejar(grafo: Grafo, deposito: str, veiculos: Sequence[Veiculo],
             entregas: Sequence[EntregaPlan], modo: str = "energia",
             preco: float = PRECO_COMBUSTIVEL_RS_L) -> Plano:
    if deposito not in grafo.nos:
        raise ValueError("Depósito inexistente na malha")
    plano = Plano()
    dist_dep, _ = dijkstra(grafo, deposito, _custo_km)
    cap_max = max((v.capacidade_kg for v in veiculos), default=0.0)

    viaveis: List[EntregaPlan] = []
    for e in entregas:
        if e.no not in grafo.nos or e.no not in dist_dep:
            plano.inviaveis.append((e.id, "sem caminho a partir do depósito (vias bloqueadas)"))
        elif e.peso_kg > cap_max:
            plano.inviaveis.append((e.id, f"peso {e.peso_kg:g} kg excede a capacidade da frota disponível"))
        else:
            viaveis.append(e)
    if not viaveis:
        return plano

    fila = FilaPrioridade()
    for e in viaveis:
        fila.push(e, (e.prioridade, e.prazo_min if e.prazo_min is not None else INF, e.id))
    ordenadas: List[EntregaPlan] = []
    while fila:
        ordenadas.append(fila.pop())

    nos = {deposito} | {e.no for e in viaveis}
    D = {n: dijkstra(grafo, n, _custo_km)[0] for n in nos}

    viagens_v: Dict[int, List[dict]] = {v.id: [] for v in veiculos}
    paradas_v: Dict[int, int] = {v.id: 0 for v in veiculos}
    for e in ordenadas:
        melhor = None                                    # (custo, veic_id, novo?, veic, viagem)
        for v in veiculos:
            if e.peso_kg > v.capacidade_kg:
                continue
            cons = v.consumo_ref_l_km
            fator = 1.0 + 0.05 * paradas_v[v.id]          # equilibra a carga de trabalho
            for t in viagens_v[v.id]:
                if t["peso"] + e.peso_kg <= v.capacidade_kg and len(t["paradas"]) < v.max_paradas:
                    u = t["ultimo"]
                    marginal = (D[u][e.no] + D[e.no][deposito] - D[u][deposito]) * cons
                    cand = (marginal * fator, v.id, 0, v, t)
                    if melhor is None or cand[:3] < melhor[:3]:
                        melhor = cand
            cand = (2 * D[deposito][e.no] * cons * fator, v.id, 1, v, None)
            if melhor is None or cand[:3] < melhor[:3]:
                melhor = cand
        _, _, _, v, t = melhor
        if t is None:
            t = {"paradas": [], "peso": 0.0, "ultimo": deposito}
            viagens_v[v.id].append(t)
        t["paradas"].append(e)
        t["peso"] += e.peso_kg
        t["ultimo"] = e.no
        paradas_v[v.id] += 1

    for v in veiculos:
        relogio = 0.0
        for numero, t in enumerate(viagens_v[v.id], start=1):
            viagem = _montar_viagem(grafo, deposito, v, numero, relogio, t["paradas"], modo, preco)
            plano.viagens.append(viagem)
            relogio = viagem.fim_min
    return plano
