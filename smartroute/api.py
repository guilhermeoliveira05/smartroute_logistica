"""API REST (Flask) consumida pelo dashboard."""
from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from . import reports, servico
from .config import DEPOSITO_ID, PRIORIDADES
from .delivery_fsm import AFD, EVENTOS, Estado, ROTULOS
from .demo import gerar_entregas_demo
from .enderecos import normalizar
from .malha import criar_malha

bp = Blueprint("api", __name__, url_prefix="/api")


def repo():
    return current_app.config["REPO"]


def grafo_atual():
    """Malha base + bloqueios persistidos (o grafo é pequeno: reconstruir é barato)."""
    g = criar_malha()
    for u, v in repo().listar_bloqueios():
        g.definir_bloqueio(u, v, True)
    return g


def erro(mensagem: str, status: int = 400):
    return jsonify({"erro": mensagem}), status


@bp.errorhandler(servico.ErroNegocio)
def _erro_negocio(e: servico.ErroNegocio):
    return erro(e.mensagem, e.status)


# ---- mapa e endereços ---------------------------------------------------
@bp.get("/mapa")
def mapa():
    g = grafo_atual()
    return jsonify({
        "deposito": DEPOSITO_ID,
        "nos": [vars(n) for n in g.nos.values()],
        "arestas": [{"u": a.origem, "v": a.destino, "dist_km": a.dist_km,
                     "vel_kmh": a.vel_kmh, "bloqueada": a.bloqueada} for a in g.arestas_unicas()],
    })


@bp.get("/enderecos")
def enderecos():
    g = criar_malha()
    ids = current_app.config["INDICE"].buscar(request.args.get("q", ""), limite=10)
    return jsonify([{"no_id": i, "nome": g.nos[i].nome} for i in ids])


# ---- veículos -----------------------------------------------------------
@bp.get("/veiculos")
def veiculos():
    return jsonify(repo().veiculos_com_posicao())


# ---- entregas -----------------------------------------------------------
@bp.get("/entregas")
def listar_entregas():
    return jsonify(repo().listar_entregas())


@bp.post("/entregas")
def criar_entrega():
    d = request.get_json(silent=True) or {}
    cliente = str(d.get("cliente", "")).strip()
    if not cliente:
        return erro("Informe o nome do cliente.", 422)
    try:
        peso = float(d.get("peso_kg"))
        prioridade = int(d.get("prioridade", 2))
        prazo = d.get("prazo_min")
        prazo = None if prazo in (None, "") else float(prazo)
    except (TypeError, ValueError):
        return erro("Peso, prioridade ou prazo inválidos.", 422)
    if peso <= 0:
        return erro("O peso da carga deve ser maior que zero.", 422)
    if prioridade not in PRIORIDADES:
        return erro("Prioridade deve ser 1 (urgente), 2 (normal) ou 3 (baixa).", 422)
    if prazo is not None and prazo <= 0:
        return erro("O prazo deve ser maior que zero (minutos desde a saída).", 422)

    g = criar_malha()
    no_id = d.get("no_id")
    if no_id not in g.nos:
        texto = str(d.get("endereco", "")).strip()
        exatos = [n for n in g.nos.values() if normalizar(n.nome) == normalizar(texto)]
        achados = exatos or [g.nos[i] for i in current_app.config["INDICE"].buscar(texto, limite=5)]
        if len(achados) != 1:
            sug = [n.nome for n in achados[:5]]
            msg = "Endereço não encontrado na malha." if not achados else \
                "Endereço ambíguo. Opções: " + "; ".join(sug)
            return erro(msg, 422)
        no_id = achados[0].id
    no = g.nos[no_id]
    eid = repo().inserir_entrega(cliente, no.nome, no_id, peso, prioridade, prazo)
    return jsonify(repo().obter_entrega(eid)), 201


@bp.delete("/entregas/<int:entrega_id>")
def remover_entrega(entrega_id: int):
    e = repo().obter_entrega(entrega_id)
    if e is None:
        return erro("Entrega não encontrada.", 404)
    if e["estado"] != Estado.AGUARDANDO_SAIDA:
        return erro("Só é possível remover entregas que ainda não saíram.", 409)
    repo().remover_entrega(entrega_id)
    replanejado = False
    if e["rota_id"]:                                   # a rota planejada ficou desatualizada
        servico.planejar(repo(), grafo_atual())
        replanejado = True
    return jsonify({"removida": entrega_id, "replanejado": replanejado})


@bp.post("/entregas/<int:entrega_id>/evento")
def evento_entrega(entrega_id: int):
    evento = (request.get_json(silent=True) or {}).get("evento")
    if evento not in EVENTOS:
        return erro(f"Evento inválido. Use um de: {', '.join(EVENTOS)}.", 422)
    return jsonify(servico.aplicar_evento(repo(), entrega_id, evento))


@bp.get("/entregas/<int:entrega_id>/historico")
def historico_entrega(entrega_id: int):
    if repo().obter_entrega(entrega_id) is None:
        return erro("Entrega não encontrada.", 404)
    return jsonify(repo().historico(entrega_id))


@bp.get("/estados")
def estados():
    """Definição do AFD (para documentação/diagrama)."""
    return jsonify({
        "estados": {int(e): ROTULOS[e] for e in Estado},
        "eventos": list(EVENTOS),
        "mermaid": AFD.para_mermaid(),
    })


# ---- rotas --------------------------------------------------------------
@bp.get("/rotas")
def listar_rotas():
    return jsonify(repo().listar_rotas())


@bp.post("/rotas/planejar")
def planejar():
    modo = (request.get_json(silent=True) or {}).get("modo", "energia")
    if modo not in ("energia", "distancia", "tempo"):
        return erro("Modo deve ser energia, distancia ou tempo.", 422)
    return jsonify(servico.planejar(repo(), grafo_atual(), modo))


@bp.post("/rotas/<int:rota_id>/avancar")
def avancar(rota_id: int):
    return jsonify(servico.avancar_rota(repo(), rota_id))


# ---- bloqueio de vias ---------------------------------------------------
@bp.get("/vias/bloqueadas")
def vias_bloqueadas():
    g = criar_malha()
    return jsonify([{"u": u, "v": v, "nome_u": g.nos[u].nome, "nome_v": g.nos[v].nome}
                    for u, v in repo().listar_bloqueios()])


def _alterar_via(bloquear: bool):
    d = request.get_json(silent=True) or {}
    u, v = d.get("u"), d.get("v")
    g = criar_malha()
    if g.aresta(u, v) is None:
        return erro("Não existe via entre esses dois cruzamentos.", 422)
    repo().definir_bloqueio(u, v, bloquear)
    resumo = servico.planejar(repo(), grafo_atual())          # recalcula as rotas ainda não iniciadas
    return jsonify({"bloqueada": bloquear, "u": u, "v": v, "replanejamento": resumo})


@bp.post("/vias/bloquear")
def bloquear_via():
    return _alterar_via(True)


@bp.post("/vias/desbloquear")
def desbloquear_via():
    return _alterar_via(False)


# ---- KPIs e relatórios --------------------------------------------------
@bp.get("/kpis")
def kpis():
    return jsonify(servico.kpis(repo()))


@bp.get("/relatorios/rotas.csv")
def relatorio_rotas_csv():
    return Response(reports.rotas_csv(repo().listar_rotas()), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=rotas.csv"})


@bp.get("/relatorios/entregas.csv")
def relatorio_entregas_csv():
    return Response(reports.entregas_csv(repo().listar_entregas()), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=entregas.csv"})


@bp.get("/relatorios/gerencial.pdf")
def relatorio_pdf():
    pdf = reports.relatorio_pdf(repo().listar_rotas(), repo().listar_entregas(), servico.kpis(repo()))
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=relatorio_gerencial.pdf"})


# ---- demonstração -------------------------------------------------------
@bp.post("/demo")
def demo():
    try:
        n = max(1, min(200, int((request.get_json(silent=True) or {}).get("n", 35))))
    except (TypeError, ValueError):
        return erro("Quantidade inválida.", 422)
    repo().limpar_entregas_e_rotas()
    g = criar_malha()
    for d in gerar_entregas_demo(g, n):
        repo().inserir_entrega(d["cliente"], d["endereco"], d["no_id"], d["peso_kg"],
                               d["prioridade"], d["prazo_min"])
    return jsonify({"criadas": n}), 201


@bp.post("/reset")
def reset():
    repo().resetar()
    return jsonify({"ok": True})
