"""Persistência em SQLite (biblioteca padrão, sem dependências extras).

Para migrar para PostgreSQL basta trocar esta camada: o resto do sistema só
conversa com a classe ``Repo``.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .config import DEPOSITO_ID
from .delivery_fsm import Estado, ROTULOS
from .physics import Veiculo, veiculos_padrao

SCHEMA = """
CREATE TABLE IF NOT EXISTS veiculos(
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL,
    massa_kg REAL, cd REAL, area_m2 REAL, mu REAL, eta REAL, pc_kj_l REAL,
    capacidade_kg REAL, vmax_kmh REAL, max_paradas INTEGER, kml_ref REAL,
    posicao_no TEXT
);
CREATE TABLE IF NOT EXISTS entregas(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT NOT NULL, endereco TEXT NOT NULL, no_id TEXT NOT NULL,
    peso_kg REAL NOT NULL, prioridade INTEGER NOT NULL DEFAULT 2, prazo_min REAL,
    estado INTEGER NOT NULL DEFAULT 0, rota_id INTEGER, ordem INTEGER,
    eta_min REAL, no_prazo INTEGER, inviavel TEXT, criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rotas(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    veiculo_id INTEGER NOT NULL, viagem INTEGER NOT NULL,
    inicio_min REAL, fim_min REAL, dist_km REAL, tempo_min REAL, litros REAL, custo_rs REAL,
    base_dist_km REAL, base_tempo_min REAL, base_litros REAL, base_custo_rs REAL,
    caminho_json TEXT, criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vias_bloqueadas(
    u TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY(u, v)
);
CREATE TABLE IF NOT EXISTS historico_estados(
    id INTEGER PRIMARY KEY AUTOINCREMENT, entrega_id INTEGER,
    de_estado INTEGER, para_estado INTEGER, evento TEXT, ts TEXT
);
"""


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repo:
    def __init__(self, caminho: str) -> None:
        self.caminho = caminho
        with self.conn() as c:
            c.executescript(SCHEMA)
            if c.execute("SELECT COUNT(*) FROM veiculos").fetchone()[0] == 0:
                for i, v in enumerate(veiculos_padrao(), start=1):
                    c.execute(
                        "INSERT INTO veiculos(id,nome,tipo,massa_kg,cd,area_m2,mu,eta,pc_kj_l,"
                        "capacidade_kg,vmax_kmh,max_paradas,kml_ref,posicao_no) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (i, v["nome"], v["tipo"], v["massa_kg"], v["cd"], v["area_m2"], v["mu"],
                         v["eta"], v["pc_kj_l"], v["capacidade_kg"], v["vmax_kmh"],
                         v["max_paradas"], v["kml_ref"], DEPOSITO_ID),
                    )

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.caminho)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ---- veículos -------------------------------------------------------
    def listar_veiculos(self) -> List[Veiculo]:
        with self.conn() as c:
            return [Veiculo.de_linha(r) for r in c.execute("SELECT * FROM veiculos ORDER BY id")]

    def veiculos_com_posicao(self) -> List[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM veiculos ORDER BY id")]

    def definir_posicao(self, veiculo_id: int, no_id: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE veiculos SET posicao_no=? WHERE id=?", (no_id, veiculo_id))

    # ---- entregas -------------------------------------------------------
    def inserir_entrega(self, cliente, endereco, no_id, peso_kg, prioridade, prazo_min) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO entregas(cliente,endereco,no_id,peso_kg,prioridade,prazo_min,criada_em) "
                "VALUES(?,?,?,?,?,?,?)",
                (cliente, endereco, no_id, peso_kg, prioridade, prazo_min, agora()),
            )
            return cur.lastrowid

    @staticmethod
    def _entrega(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["estado_nome"] = ROTULOS[Estado(d["estado"])]
        return d

    def listar_entregas(self) -> List[dict]:
        with self.conn() as c:
            return [self._entrega(r) for r in c.execute("SELECT * FROM entregas ORDER BY id")]

    def obter_entrega(self, entrega_id: int) -> Optional[dict]:
        with self.conn() as c:
            r = c.execute("SELECT * FROM entregas WHERE id=?", (entrega_id,)).fetchone()
            return self._entrega(r) if r else None

    def remover_entrega(self, entrega_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM entregas WHERE id=?", (entrega_id,))
            c.execute("DELETE FROM historico_estados WHERE entrega_id=?", (entrega_id,))

    def definir_estado(self, entrega_id: int, de: int, para: int, evento: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE entregas SET estado=? WHERE id=?", (int(para), entrega_id))
            c.execute(
                "INSERT INTO historico_estados(entrega_id,de_estado,para_estado,evento,ts) VALUES(?,?,?,?,?)",
                (entrega_id, int(de), int(para), evento, agora()),
            )

    def historico(self, entrega_id: int) -> List[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM historico_estados WHERE entrega_id=? ORDER BY id", (entrega_id,))]

    def entregas_pendentes(self) -> List[dict]:
        """Aguardando saída e ainda sem rota (candidatas a planejamento)."""
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM entregas WHERE estado=0 AND rota_id IS NULL ORDER BY id")]

    def marcar_inviaveis(self, inviaveis: Iterable[Tuple[int, str]], planejadas: Iterable[int]) -> None:
        with self.conn() as c:
            for eid in planejadas:
                c.execute("UPDATE entregas SET inviavel=NULL WHERE id=?", (eid,))
            for eid, motivo in inviaveis:
                c.execute("UPDATE entregas SET inviavel=? WHERE id=?", (motivo, eid))

    # ---- rotas ----------------------------------------------------------
    def listar_rotas(self) -> List[dict]:
        with self.conn() as c:
            rotas = []
            for r in c.execute(
                "SELECT r.*, v.nome AS veiculo_nome, v.tipo AS veiculo_tipo "
                "FROM rotas r JOIN veiculos v ON v.id=r.veiculo_id ORDER BY r.id"
            ):
                d = dict(r)
                d["caminho"] = json.loads(d.pop("caminho_json") or "[]")
                d["paradas"] = [self._entrega(p) for p in c.execute(
                    "SELECT * FROM entregas WHERE rota_id=? ORDER BY ordem", (d["id"],))]
                rotas.append(d)
            return rotas

    def obter_rota(self, rota_id: int) -> Optional[dict]:
        return next((r for r in self.listar_rotas() if r["id"] == rota_id), None)

    def salvar_viagem(self, viagem) -> int:
        m, b = viagem.metricas, viagem.baseline
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO rotas(veiculo_id,viagem,inicio_min,fim_min,dist_km,tempo_min,litros,custo_rs,"
                "base_dist_km,base_tempo_min,base_litros,base_custo_rs,caminho_json,criada_em) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (viagem.veiculo_id, viagem.numero, viagem.inicio_min, viagem.fim_min, m.dist_km,
                 m.tempo_min, m.litros, m.custo_rs, b.dist_km, b.tempo_min, b.litros, b.custo_rs,
                 json.dumps(viagem.caminho), agora()),
            )
            rota_id = cur.lastrowid
            for ordem, p in enumerate(viagem.paradas, start=1):
                eta = viagem.etas[p.id]
                no_prazo = None if p.prazo_min is None else int(eta <= p.prazo_min)
                c.execute(
                    "UPDATE entregas SET rota_id=?, ordem=?, eta_min=?, no_prazo=? WHERE id=?",
                    (rota_id, ordem, eta, no_prazo, p.id),
                )
            return rota_id

    def atualizar_caminho(self, rota_id: int, caminho: List[str]) -> None:
        with self.conn() as c:
            c.execute("UPDATE rotas SET caminho_json=? WHERE id=?", (json.dumps(caminho), rota_id))

    def remover_rotas_planejadas(self) -> int:
        """Apaga rotas em que nenhuma entrega saiu ainda (todas aguardando)."""
        with self.conn() as c:
            ids = [r["id"] for r in c.execute(
                "SELECT r.id FROM rotas r WHERE NOT EXISTS "
                "(SELECT 1 FROM entregas e WHERE e.rota_id=r.id AND e.estado<>0)")]
            for rid in ids:
                c.execute("UPDATE entregas SET rota_id=NULL, ordem=NULL, eta_min=NULL, no_prazo=NULL "
                          "WHERE rota_id=?", (rid,))
                c.execute("DELETE FROM rotas WHERE id=?", (rid,))
            return len(ids)

    def veiculos_ocupados(self) -> set:
        """Veículos com viagem em andamento (algumas entregas já saíram, outras não concluíram)."""
        ocupados = set()
        for r in self.listar_rotas():
            estados = {p["estado"] for p in r["paradas"]}
            if estados and estados != {0} and estados != {3}:
                ocupados.add(r["veiculo_id"])
        return ocupados

    # ---- vias bloqueadas ------------------------------------------------
    def listar_bloqueios(self) -> List[Tuple[str, str]]:
        with self.conn() as c:
            return [(r["u"], r["v"]) for r in c.execute("SELECT u,v FROM vias_bloqueadas ORDER BY u,v")]

    def definir_bloqueio(self, u: str, v: str, bloqueada: bool) -> None:
        u, v = sorted((u, v))
        with self.conn() as c:
            if bloqueada:
                c.execute("INSERT OR IGNORE INTO vias_bloqueadas(u,v) VALUES(?,?)", (u, v))
            else:
                c.execute("DELETE FROM vias_bloqueadas WHERE u=? AND v=?", (u, v))

    # ---- manutenção -----------------------------------------------------
    def limpar_entregas_e_rotas(self) -> None:
        with self.conn() as c:
            for t in ("entregas", "rotas", "historico_estados"):
                c.execute(f"DELETE FROM {t}")
            c.execute("UPDATE veiculos SET posicao_no=?", (DEPOSITO_ID,))

    def resetar(self) -> None:
        self.limpar_entregas_e_rotas()
        with self.conn() as c:
            c.execute("DELETE FROM vias_bloqueadas")
