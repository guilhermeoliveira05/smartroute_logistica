"""Testes do roteirizador."""
from smartroute.config import DEPOSITO_ID
from smartroute.demo import gerar_entregas_demo
from smartroute.malha import criar_malha
from smartroute.router import EntregaPlan, planejar


def _entregas_demo(g, n=35):
    return [EntregaPlan(i + 1, d["no_id"], d["peso_kg"], d["prioridade"], d["prazo_min"])
            for i, d in enumerate(gerar_entregas_demo(g, n))]


def test_malha_tem_tamanho_esperado():
    g = criar_malha()
    assert len(g.nos) == 49
    assert g.nos[DEPOSITO_ID].deposito
    assert len(g.arestas_unicas()) == 2 * 7 * 6 + 6   # grade 7x7 + 6 diagonais


def test_todas_as_entregas_planejadas_uma_unica_vez(veiculos):
    g = criar_malha()
    entregas = _entregas_demo(g)
    plano = planejar(g, DEPOSITO_ID, veiculos, entregas)
    ids = [p.id for v in plano.viagens for p in v.paradas]
    assert sorted(ids) == sorted(e.id for e in entregas)
    assert len(ids) == len(set(ids))
    assert plano.inviaveis == []


def test_respeita_capacidade_e_maximo_de_paradas(veiculos):
    g = criar_malha()
    por_id = {v.id: v for v in veiculos}
    plano = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    for viagem in plano.viagens:
        v = por_id[viagem.veiculo_id]
        assert sum(p.peso_kg for p in viagem.paradas) <= v.capacidade_kg + 1e-9
        assert len(viagem.paradas) <= v.max_paradas


def test_urgentes_antes_das_demais_em_cada_viagem(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    for viagem in plano.viagens:
        prioridades = [p.prioridade for p in viagem.paradas]
        assert prioridades == sorted(prioridades)


def test_caminhos_comecam_e_terminam_no_deposito_e_sao_conexos(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    for viagem in plano.viagens:
        cam = viagem.caminho
        assert cam[0] == DEPOSITO_ID and cam[-1] == DEPOSITO_ID
        assert all(g.aresta(a, b) is not None for a, b in zip(cam, cam[1:]))
        for p in viagem.paradas:
            assert p.no in cam


def test_otimizado_consome_menos_que_rota_empirica(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    otm, base = plano.totais()
    assert otm.litros < base.litros
    assert otm.custo_rs < base.custo_rs


def test_planejamento_e_deterministico(veiculos):
    g = criar_malha()
    a = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    b = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    assert [[p.id for p in v.paradas] for v in a.viagens] == [[p.id for p in v.paradas] for v in b.viagens]


def test_nao_usa_via_bloqueada(veiculos):
    g = criar_malha()
    entregas = _entregas_demo(g)
    bloqueada = planejar(g, DEPOSITO_ID, veiculos, entregas).viagens[0].caminho[:2]
    g.definir_bloqueio(*bloqueada, True)
    plano = planejar(g, DEPOSITO_ID, veiculos, entregas)
    for v in plano.viagens:
        assert not any({a, b} == set(bloqueada) for a, b in zip(v.caminho, v.caminho[1:]))


def test_entrega_isolada_por_bloqueios_e_inviavel_e_o_resto_segue(veiculos):
    g = criar_malha()
    alvo = "N00"                                        # canto da malha
    for a in list(g.adj[alvo]):
        g.definir_bloqueio(a.origem, a.destino, True)
    entregas = [EntregaPlan(1, alvo, 5.0), EntregaPlan(2, "N10", 5.0)]
    plano = planejar(g, DEPOSITO_ID, veiculos, entregas)
    assert [i for i, _ in plano.inviaveis] == [1]
    assert [p.id for v in plano.viagens for p in v.paradas] == [2]


def test_peso_acima_da_capacidade_da_frota_e_inviavel(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, [EntregaPlan(1, "N10", 99999.0)])
    assert plano.inviaveis and plano.inviaveis[0][0] == 1 and not plano.viagens


def test_carga_pesada_vai_para_o_caminhao(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, [EntregaPlan(1, "N10", 300.0)])
    caminhao = next(v for v in veiculos if v.tipo == "caminhao")
    assert plano.viagens[0].veiculo_id == caminhao.id


def test_sem_entregas_nao_gera_viagens(veiculos):
    assert planejar(criar_malha(), DEPOSITO_ID, veiculos, []).viagens == []


def test_etas_crescem_e_respeitam_tempo_de_servico(veiculos):
    g = criar_malha()
    plano = planejar(g, DEPOSITO_ID, veiculos, _entregas_demo(g))
    for viagem in plano.viagens:
        etas = [viagem.etas[p.id] for p in viagem.paradas]
        assert etas == sorted(etas)
        assert viagem.fim_min > etas[-1]
