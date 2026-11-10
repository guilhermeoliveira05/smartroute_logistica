"""Regras de negócio: planejamento, simulação de andamento e KPIs."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from .config import DEPOSITO_ID, PRECO_COMBUSTIVEL_RS_L
from .db import Repo
from .delivery_fsm import AFD, TransicaoInvalida
from .graph import Grafo
from .router import Avaliador, EntregaPlan, planejar as planejar_rotas


class ErroNegocio(Exception):
    """Erro de regra de negócio (vira HTTP 409/422 na API)."""

    def __init__(self, mensagem: str, status: int = 409) -> None:
        super().__init__(mensagem)
        self.mensagem, self.status = mensagem, status


# ---- planejamento -------------------------------------------------------
def planejar(repo: Repo, grafo: Grafo, modo: str = "energia") -> Dict:
    """(Re)planeja todas as entregas ainda não iniciadas.

    Rotas já em andamento são preservadas; rotas só planejadas são descartadas
    e recalculadas (é isso que faz o bloqueio de vias desviar as rotas).
    """
    removidas = repo.remover_rotas_planejadas()
    ocupados = repo.veiculos_ocupados()
    veiculos = [v for v in repo.listar_veiculos() if v.id not in ocupados]
    pendentes = repo.entregas_pendentes()
    entregas = [EntregaPlan(e["id"], e["no_id"], e["peso_kg"], e["prioridade"], e["prazo_min"])
                for e in pendentes]
    plano = planejar_rotas(grafo, DEPOSITO_ID, veiculos, entregas, modo)

    planejadas = []
    for viagem in plano.viagens:
        repo.salvar_viagem(viagem)
        planejadas.extend(p.id for p in viagem.paradas)
    repo.marcar_inviaveis(plano.inviaveis, planejadas)

    desviadas = desviar_rotas_ativas(repo, grafo)

    otm, base = plano.totais()
    economia = (1 - otm.litros / base.litros) * 100 if base.litros else 0.0
    return {
        "rotas_em_andamento_recalculadas": desviadas,
        "rotas_replanejadas": removidas,
        "viagens": len(plano.viagens),
        "entregas_planejadas": len(planejadas),
        "inviaveis": [{"entrega_id": i, "motivo": m} for i, m in plano.inviaveis],
        "economia_combustivel_pct": round(economia, 1),
    }


def desviar_rotas_ativas(repo: Repo, grafo: Grafo) -> int:
    """Recalcula o caminho restante das rotas em andamento (desvio de obras/acidentes).

    A ordem das paradas é mantida; muda só o caminho entre a posição atual do
    veículo, as paradas que faltam e o retorno ao depósito.
    """
    veiculos = {v.id: v for v in repo.listar_veiculos()}
    posicoes = {v["id"]: v["posicao_no"] for v in repo.veiculos_com_posicao()}
    recalculadas = 0
    for r in repo.listar_rotas():
        estados = {p["estado"] for p in r["paradas"]}
        if not estados or estados == {0} or estados == {3}:
            continue                                   # não iniciada (replanejada) ou concluída
        restantes = [p for p in r["paradas"] if p["estado"] in (0, 1)]   # ainda com carga a bordo
        aval = Avaliador(grafo, veiculos[r["veiculo_id"]], "energia")
        carga = sum(p["peso_kg"] for p in restantes)
        no, caminho = posicoes[r["veiculo_id"]], []
        try:
            for destino, peso in [(p["no_id"], p["peso_kg"]) for p in restantes] + [(DEPOSITO_ID, 0.0)]:
                tr = aval.trecho(no, destino, carga)
                caminho.extend(tr.caminho if not caminho else tr.caminho[1:])
                carga, no = max(0.0, carga - peso), destino
        except ValueError:
            continue                                   # sem caminho: mantém o atual
        repo.atualizar_caminho(r["id"], caminho)
        recalculadas += 1
    return recalculadas


# ---- estados das entregas (AFD) ----------------------------------------
def aplicar_evento(repo: Repo, entrega_id: int, evento: str) -> Dict:
    e = repo.obter_entrega(entrega_id)
    if e is None:
        raise ErroNegocio("Entrega não encontrada.", 404)
    try:
        novo = AFD.transicao(e["estado"], evento)
    except TransicaoInvalida as ex:
        raise ErroNegocio(str(ex), 409)
    repo.definir_estado(entrega_id, e["estado"], novo, evento)
    if evento == "chegar_destino" and e["rota_id"]:
        rota = repo.obter_rota(e["rota_id"])
        repo.definir_posicao(rota["veiculo_id"], e["no_id"])
    return repo.obter_entrega(entrega_id)


def avancar_rota(repo: Repo, rota_id: int) -> Dict:
    """Simulação: avança um passo do AFD na próxima entrega pendente da rota."""
    rota = repo.obter_rota(rota_id)
    if rota is None:
        raise ErroNegocio("Rota não encontrada.", 404)
    for outra in repo.listar_rotas():
        if (outra["veiculo_id"] == rota["veiculo_id"] and outra["viagem"] < rota["viagem"]
                and any(p["estado"] != 3 for p in outra["paradas"])):
            raise ErroNegocio(f"Conclua a viagem {outra['viagem']} deste veículo antes.", 409)
    atual = next((p for p in rota["paradas"] if p["estado"] != 3), None)
    if atual is None:
        raise ErroNegocio("Rota já concluída.", 409)
    evento = AFD.evento_esperado(atual["estado"])
    entrega = aplicar_evento(repo, atual["id"], evento)
    rota = repo.obter_rota(rota_id)
    if all(p["estado"] == 3 for p in rota["paradas"]):
        repo.definir_posicao(rota["veiculo_id"], DEPOSITO_ID)      # voltou ao depósito
    return {"evento": evento, "entrega": entrega}


# ---- KPIs ----------------------------------------------------------------
def _pct(a: float, b: float) -> Optional[float]:
    return round((1 - a / b) * 100, 1) if b else None


def kpis(repo: Repo) -> Dict:
    rotas = repo.listar_rotas()
    entregas = repo.listar_entregas()
    hoje = datetime.now().date()
    semana = hoje - timedelta(days=6)

    def km(filtro) -> float:
        return round(sum(r["dist_km"] for r in rotas if filtro(datetime.fromisoformat(r["criada_em"]).date())), 2)

    com_rota = [e for e in entregas if e["rota_id"]]
    com_prazo = [e for e in com_rota if e["no_prazo"] is not None]
    litros = sum(r["litros"] for r in rotas)
    dist = sum(r["dist_km"] for r in rotas)
    custo = sum(r["custo_rs"] for r in rotas)
    base_litros = sum(r["base_litros"] for r in rotas)
    base_custo = sum(r["base_custo_rs"] for r in rotas)
    base_dist = sum(r["base_dist_km"] for r in rotas)

    por_estado: Dict[str, int] = {}
    for e in entregas:
        por_estado[e["estado_nome"]] = por_estado.get(e["estado_nome"], 0) + 1

    return {
        "total_entregas": len(entregas),
        "entregas_planejadas": len(com_rota),
        "entregas_inviaveis": sum(1 for e in entregas if e["inviavel"]),
        "total_viagens": len(rotas),
        "custo_medio_por_entrega_rs": round(custo / len(com_rota), 2) if com_rota else None,
        "km_hoje": km(lambda d: d == hoje),
        "km_semana": km(lambda d: d >= semana),
        "taxa_no_prazo_pct": round(100 * sum(e["no_prazo"] for e in com_prazo) / len(com_prazo), 1)
        if com_prazo else None,
        "eficiencia_km_por_l": round(dist / litros, 2) if litros else None,
        "litros_total": round(litros, 2),
        "custo_total_rs": round(custo, 2),
        "economia_combustivel_pct": _pct(litros, base_litros),
        "economia_custo_rs": round(base_custo - custo, 2),
        "economia_km_pct": _pct(dist, base_dist),
        "preco_combustivel_rs_l": PRECO_COMBUSTIVEL_RS_L,
        "entregas_por_estado": por_estado,
    }
