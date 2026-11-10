"""Relatórios gerenciais em CSV e PDF."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _n(valor, casas: int = 2) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    if valor is None:
        return "-"
    return f"{valor:.{casas}f}".replace(".", ",")


def _economia(otm: float, base: float) -> str:
    return _n((1 - otm / base) * 100, 1) + "%" if base else "-"


def _linhas_rotas(rotas: List[Dict]) -> List[List[str]]:
    return [
        [r["id"], r["veiculo_nome"], r["viagem"], len(r["paradas"]), _n(r["dist_km"]),
         _n(r["tempo_min"], 0), _n(r["litros"]), _n(r["custo_rs"]),
         _n(r["base_dist_km"]), _n(r["base_litros"]), _economia(r["litros"], r["base_litros"])]
        for r in rotas
    ]


CAB_ROTAS = ["Rota", "Veículo", "Viagem", "Paradas", "Km", "Tempo (min)", "Litros", "Custo (R$)",
             "Km empírico", "Litros empírico", "Economia comb."]


def rotas_csv(rotas: List[Dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(CAB_ROTAS)
    w.writerows(_linhas_rotas(rotas))
    return ("﻿" + buf.getvalue()).encode("utf-8")      # BOM: o Excel abre com acentos corretos


def entregas_csv(entregas: List[Dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["ID", "Cliente", "Endereço", "Peso (kg)", "Prioridade", "Prazo (min)", "Estado",
                "Rota", "Ordem", "ETA (min)", "No prazo"])
    for e in entregas:
        no_prazo = "-" if e["no_prazo"] is None else ("sim" if e["no_prazo"] else "não")
        w.writerow([e["id"], e["cliente"], e["endereco"], _n(e["peso_kg"], 1), e["prioridade"],
                    _n(e["prazo_min"], 0), e["estado_nome"], e["rota_id"] or "-", e["ordem"] or "-",
                    _n(e["eta_min"], 0), no_prazo])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _tabela(dados: List[List], larguras=None) -> Table:
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def relatorio_pdf(rotas: List[Dict], entregas: List[Dict], kpis: Dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Relatório Gerencial - SmartRoute Logística")
    st = getSampleStyleSheet()
    el = [
        Paragraph("Relatório Gerencial - SmartRoute Logística", st["Title"]),
        Paragraph(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}", st["Normal"]),
        Spacer(1, 0.4 * cm),
        Paragraph("Indicadores-chave (KPIs)", st["Heading2"]),
        _tabela([
            ["Indicador", "Valor"],
            ["Custo médio por entrega", f"R$ {_n(kpis['custo_medio_por_entrega_rs'])}"],
            ["Quilometragem hoje / últimos 7 dias", f"{_n(kpis['km_hoje'])} km / {_n(kpis['km_semana'])} km"],
            ["Entregas no prazo (previsto)", f"{_n(kpis['taxa_no_prazo_pct'], 1)}%"],
            ["Eficiência energética", f"{_n(kpis['eficiencia_km_por_l'])} km/L"],
            ["Combustível total / custo total", f"{_n(kpis['litros_total'])} L / R$ {_n(kpis['custo_total_rs'])}"],
            ["Economia de combustível vs. rota empírica", f"{_n(kpis['economia_combustivel_pct'], 1)}%"],
            ["Economia de custo vs. rota empírica", f"R$ {_n(kpis['economia_custo_rs'])}"],
        ], larguras=[9 * cm, 8 * cm]),
        Spacer(1, 0.5 * cm),
        Paragraph("Rotas", st["Heading2"]),
        _tabela([CAB_ROTAS] + _linhas_rotas(rotas)),
        Spacer(1, 0.5 * cm),
        Paragraph("Entregas", st["Heading2"]),
    ]
    linhas = [["ID", "Cliente", "Endereço", "Peso (kg)", "Prior.", "Estado", "Rota", "Ordem", "ETA (min)", "No prazo"]]
    for e in entregas:
        np_ = "-" if e["no_prazo"] is None else ("sim" if e["no_prazo"] else "não")
        linhas.append([e["id"], e["cliente"], e["endereco"], _n(e["peso_kg"], 1), e["prioridade"],
                       e["estado_nome"], e["rota_id"] or "-", e["ordem"] or "-", _n(e["eta_min"], 0), np_])
    el.append(_tabela(linhas))
    doc.build(el)
    return buf.getvalue()
