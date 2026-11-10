"""Testes de integração da API (fluxo completo do operador/gestor)."""


def _demo_planejada(client, n=35):
    assert client.post("/api/demo", json={"n": n}).status_code == 201
    r = client.post("/api/rotas/planejar", json={})
    assert r.status_code == 200
    return r.get_json()


def test_pagina_inicial_e_mapa(client):
    assert client.get("/").status_code == 200
    mapa = client.get("/api/mapa").get_json()
    assert len(mapa["nos"]) == 49 and mapa["deposito"] == "N33"


def test_autocomplete_usa_indice_trie(client):
    r = client.get("/api/enderecos?q=av. c x rua 2").get_json()
    assert [x["nome"] for x in r] == ["Av. C x Rua 2"]


def test_cadastro_de_entrega_e_validacoes(client):
    ok = client.post("/api/entregas", json={"cliente": "Maria", "endereco": "Av. C x Rua 2",
                                            "peso_kg": 12.5, "prioridade": 1, "prazo_min": 90})
    assert ok.status_code == 201 and ok.get_json()["estado_nome"] == "Aguardando saída"
    assert client.post("/api/entregas", json={"cliente": "", "endereco": "Av. C x Rua 2", "peso_kg": 1}).status_code == 422
    assert client.post("/api/entregas", json={"cliente": "X", "endereco": "Av. C x Rua 2", "peso_kg": -1}).status_code == 422
    assert client.post("/api/entregas", json={"cliente": "X", "endereco": "Rua que não existe", "peso_kg": 1}).status_code == 422
    assert client.post("/api/entregas", json={"cliente": "X", "endereco": "Av. C x Rua 2", "peso_kg": 1,
                                              "prioridade": 9}).status_code == 422
    assert len(client.get("/api/entregas").get_json()) == 1


def test_planejamento_gera_rotas_e_kpis(client):
    resumo = _demo_planejada(client)
    assert resumo["entregas_planejadas"] == 35 and resumo["inviaveis"] == []
    assert resumo["economia_combustivel_pct"] > 0
    k = client.get("/api/kpis").get_json()
    assert k["total_entregas"] == 35 and k["total_viagens"] == resumo["viagens"]
    assert k["custo_medio_por_entrega_rs"] > 0 and k["eficiencia_km_por_l"] > 0
    assert 0 <= k["taxa_no_prazo_pct"] <= 100 and k["km_hoje"] > 0


def test_simulacao_percorre_o_afd_ate_finalizar(client):
    _demo_planejada(client, n=6)
    rota = client.get("/api/rotas").get_json()[0]
    n = len(rota["paradas"])
    esperados = ["iniciar_viagem", "chegar_destino", "proxima_entrega"] * n
    obtidos = [client.post(f"/api/rotas/{rota['id']}/avancar").get_json()["evento"] for _ in range(3 * n)]
    assert obtidos == esperados
    assert client.post(f"/api/rotas/{rota['id']}/avancar").status_code == 409     # já concluída
    rota = next(r for r in client.get("/api/rotas").get_json() if r["id"] == rota["id"])
    assert all(p["estado"] == 3 for p in rota["paradas"])
    veic = next(v for v in client.get("/api/veiculos").get_json() if v["id"] == rota["veiculo_id"])
    assert veic["posicao_no"] == "N33"                                              # voltou ao depósito


def test_evento_invalido_retorna_409_e_historico_registra(client):
    _demo_planejada(client, n=3)
    assert client.post("/api/entregas/1/evento", json={"evento": "chegar_destino"}).status_code == 409
    assert client.post("/api/entregas/1/evento", json={"evento": "voar"}).status_code == 422
    assert client.post("/api/entregas/1/evento", json={"evento": "iniciar_viagem"}).status_code == 200
    hist = client.get("/api/entregas/1/historico").get_json()
    assert [h["evento"] for h in hist] == ["iniciar_viagem"]


def test_segunda_viagem_so_inicia_apos_a_primeira(client):
    _demo_planejada(client)
    rotas = client.get("/api/rotas").get_json()
    por_veiculo = {}
    for r in rotas:
        por_veiculo.setdefault(r["veiculo_id"], []).append(r)
    segunda = next(rs[1] for rs in por_veiculo.values() if len(rs) > 1)
    assert client.post(f"/api/rotas/{segunda['id']}/avancar").status_code == 409


def test_bloqueio_de_via_replaneja_e_desvia(client):
    _demo_planejada(client)
    rotas = client.get("/api/rotas").get_json()
    u, v = rotas[0]["caminho"][0], rotas[0]["caminho"][1]
    r = client.post("/api/vias/bloquear", json={"u": u, "v": v})
    assert r.status_code == 200 and r.get_json()["replanejamento"]["entregas_planejadas"] == 35
    for rota in client.get("/api/rotas").get_json():
        assert not any({a, b} == {u, v} for a, b in zip(rota["caminho"], rota["caminho"][1:]))
    assert len(client.get("/api/vias/bloqueadas").get_json()) == 1
    assert next(a for a in client.get("/api/mapa").get_json()["arestas"] if {a["u"], a["v"]} == {u, v})["bloqueada"]
    assert client.post("/api/vias/desbloquear", json={"u": u, "v": v}).status_code == 200
    assert client.get("/api/vias/bloqueadas").get_json() == []


def test_bloqueio_em_rota_em_andamento_desvia_o_restante(client):
    _demo_planejada(client, n=10)
    rota = client.get("/api/rotas").get_json()[0]
    client.post(f"/api/rotas/{rota['id']}/avancar")                  # saiu: rota em andamento
    u, v = rota["caminho"][0], rota["caminho"][1]
    resumo = client.post("/api/vias/bloquear", json={"u": u, "v": v}).get_json()["replanejamento"]
    assert resumo["rotas_em_andamento_recalculadas"] >= 1
    nova = next(r for r in client.get("/api/rotas").get_json() if r["id"] == rota["id"])
    assert not any({a, b} == {u, v} for a, b in zip(nova["caminho"], nova["caminho"][1:]))


def test_via_inexistente_e_rejeitada(client):
    assert client.post("/api/vias/bloquear", json={"u": "N00", "v": "N66"}).status_code == 422


def test_entrega_isolada_aparece_como_inviavel(client):
    client.post("/api/entregas", json={"cliente": "Canto", "endereco": "Av. A x Rua 1", "peso_kg": 5})
    for u, v in (("N00", "N01"), ("N00", "N10"), ("N00", "N11")):
        client.post("/api/vias/bloquear", json={"u": u, "v": v})
    r = client.post("/api/rotas/planejar", json={}).get_json()
    assert len(r["inviaveis"]) == 1
    assert client.get("/api/entregas").get_json()[0]["inviavel"]


def test_remover_entrega_nao_iniciada_replaneja(client):
    _demo_planejada(client, n=8)
    assert client.delete("/api/entregas/1").get_json()["replanejado"] is True
    assert len(client.get("/api/entregas").get_json()) == 7
    planejadas = sum(len(r["paradas"]) for r in client.get("/api/rotas").get_json())
    assert planejadas == 7


def test_nao_remove_entrega_em_andamento(client):
    _demo_planejada(client, n=3)
    client.post("/api/entregas/1/evento", json={"evento": "iniciar_viagem"})
    assert client.delete("/api/entregas/1").status_code == 409


def test_relatorios_csv_e_pdf(client):
    _demo_planejada(client, n=10)
    csv_rotas = client.get("/api/relatorios/rotas.csv")
    assert csv_rotas.status_code == 200 and b"Rota;Ve" in csv_rotas.data
    assert client.get("/api/relatorios/entregas.csv").status_code == 200
    pdf = client.get("/api/relatorios/gerencial.pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_relatorios_vazios_nao_quebram(client):
    assert client.get("/api/relatorios/gerencial.pdf").data.startswith(b"%PDF")
    assert client.get("/api/kpis").get_json()["custo_medio_por_entrega_rs"] is None


def test_reset_limpa_tudo(client):
    _demo_planejada(client, n=5)
    client.post("/api/reset")
    assert client.get("/api/entregas").get_json() == [] and client.get("/api/rotas").get_json() == []
