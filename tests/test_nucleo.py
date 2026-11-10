"""Testes do núcleo: Dijkstra, física, AFD, ordenação e índice de endereços."""
import math

import pytest

from smartroute.config import VEL_REF_KMH
from smartroute.delivery_fsm import AFD, Estado, TransicaoInvalida
from smartroute.dijkstra import dijkstra, menor_caminho
from smartroute.enderecos import IndiceEnderecos, normalizar
from smartroute.malha import criar_malha
from smartroute.ordenacao import FilaPrioridade, merge_sort
from smartroute.physics import forca_ar, forca_atrito, litros_trecho, potencia_w


# ---- Dijkstra ------------------------------------------------------------
def test_dijkstra_menor_caminho(grafo_pequeno):
    caminho, custo = menor_caminho(grafo_pequeno, "A", "C", lambda a: a.dist_km)
    assert caminho == ["A", "B", "C"]
    assert custo == pytest.approx(2.0)


def test_dijkstra_desvia_de_via_bloqueada(grafo_pequeno):
    grafo_pequeno.definir_bloqueio("A", "B", True)
    caminho, custo = menor_caminho(grafo_pequeno, "A", "C", lambda a: a.dist_km)
    assert caminho == ["A", "C"]
    assert custo == pytest.approx(3.0)


def test_dijkstra_sem_caminho_retorna_infinito(grafo_pequeno):
    grafo_pequeno.definir_bloqueio("A", "B", True)
    grafo_pequeno.definir_bloqueio("A", "C", True)
    caminho, custo = menor_caminho(grafo_pequeno, "A", "C", lambda a: a.dist_km)
    assert caminho is None and math.isinf(custo)
    dist, _ = dijkstra(grafo_pequeno, "A", lambda a: a.dist_km)
    assert "C" not in dist


def test_dijkstra_na_malha_confere_com_forca_bruta():
    g = criar_malha()
    dist, _ = dijkstra(g, "N33", lambda a: a.dist_km)
    # Bellman-Ford simples como oráculo
    ref = {n: math.inf for n in g.nos}
    ref["N33"] = 0.0
    for _ in range(len(g.nos)):
        for a in g.arestas_unicas():
            for u, v in ((a.origem, a.destino), (a.destino, a.origem)):
                ref[v] = min(ref[v], ref[u] + a.dist_km)
    assert all(dist[n] == pytest.approx(ref[n]) for n in g.nos)


# ---- Física ---------------------------------------------------------------
def test_calibracao_reproduz_km_por_litro_de_referencia(veiculos):
    for v in veiculos:
        km_l = 1.0 / litros_trecho(v, 0.0, 1.0, VEL_REF_KMH)
        assert km_l == pytest.approx(v.kml_ref, rel=1e-9)


def test_mais_carga_consome_mais(veiculos):
    moto = veiculos[0]
    assert litros_trecho(moto, 40, 1.0, 40) > litros_trecho(moto, 0, 1.0, 40)


def test_mais_velocidade_consome_mais(veiculos):
    moto = veiculos[0]
    assert litros_trecho(moto, 0, 1.0, 60) > litros_trecho(moto, 0, 1.0, 30)


def test_formulas_basicas():
    assert forca_atrito(1000, 0.01) == pytest.approx(98.1)
    # resistência do ar cresce com v²: dobrar v quadruplica a força
    assert forca_ar(0.7, 0.6, 20) == pytest.approx(4 * forca_ar(0.7, 0.6, 10))


def test_potencia_e_forca_vezes_velocidade(veiculos):
    moto = veiculos[0]
    p = potencia_w(moto, 0, 36)  # 36 km/h = 10 m/s
    f = forca_atrito(moto.massa_kg, moto.mu) + forca_ar(moto.cd, moto.area_m2, 10)
    assert p == pytest.approx(f * 10)


# ---- AFD -------------------------------------------------------------------
def test_afd_fluxo_completo():
    assert AFD.aceita(["iniciar_viagem", "chegar_destino", "proxima_entrega"])


def test_afd_rejeita_sequencias_invalidas():
    assert not AFD.aceita(["chegar_destino"])
    assert not AFD.aceita(["iniciar_viagem", "iniciar_viagem"])
    assert not AFD.aceita(["iniciar_viagem", "chegar_destino"])      # não chegou ao final
    assert not AFD.aceita([])


def test_afd_transicao_invalida_levanta_erro():
    with pytest.raises(TransicaoInvalida):
        AFD.transicao(Estado.FINALIZADO, "iniciar_viagem")


def test_afd_evento_esperado():
    assert AFD.evento_esperado(Estado.AGUARDANDO_SAIDA) == "iniciar_viagem"
    assert AFD.evento_esperado(Estado.FINALIZADO) is None


# ---- Ordenação e filas ---------------------------------------------------
def test_merge_sort_e_estavel():
    itens = [(2, "a"), (1, "b"), (2, "c"), (1, "d")]
    assert merge_sort(itens, chave=lambda x: x[0]) == [(1, "b"), (1, "d"), (2, "a"), (2, "c")]


def test_merge_sort_vazio_e_unitario():
    assert merge_sort([]) == [] and merge_sort([5]) == [5]


def test_fila_prioridade_ordem_e_fifo_no_empate():
    f = FilaPrioridade()
    f.push("normal-1", 2)
    f.push("urgente", 1)
    f.push("normal-2", 2)
    assert [f.pop(), f.pop(), f.pop()] == ["urgente", "normal-1", "normal-2"]
    assert not f


# ---- Índice de endereços (Trie) ---------------------------------------
def test_trie_busca_por_prefixo_sem_acentos():
    idx = IndiceEnderecos()
    idx.inserir("Avenida São João x Rua 4", "n1")
    idx.inserir("Av. Brasil x Rua 10", "n2")
    assert idx.buscar("sao joao") == ["n1"]
    assert idx.buscar("RUA 1") == ["n2"]
    assert idx.buscar("rua") == ["n1", "n2"]
    assert idx.buscar("inexistente") == []


def test_normalizar():
    assert normalizar("  Av. São  João!! ") == "av sao joao"
