"""Modelo físico de consumo de combustível (Física II).

Para um trecho de comprimento d percorrido a velocidade v com massa total m:

    F_atrito = mu * m * g                  (atrito/rolamento: cresce com a carga)
    F_ar     = 1/2 * rho * Cd * A * v^2    (resistência do ar: cresce com v^2)
    F_total  = F_atrito + F_ar
    P        = F_total * v                 (potência para manter a velocidade)
    E_comb   = F_total * d / eta           (energia química consumida)
    litros   = E_comb / PC                 (PC = poder calorífico, kJ/L)

O modelo ideal subestima o consumo urbano real (arranca-e-para, marcha lenta,
perdas de transmissão). Por isso cada veículo tem um ``fator_calibracao`` que
ajusta o modelo ao km/L de referência informado (8 km/L moto, 4 km/L caminhão,
segundo o documento de abertura). A *forma* do consumo (peso e velocidade)
continua vindo da física; a calibração só ajusta a escala.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .config import VEL_REF_KMH

G = 9.81          # m/s²
RHO_AR = 1.2      # kg/m³ (ar ao nível do mar, ~20 °C)


@dataclass
class Veiculo:
    id: int
    nome: str
    tipo: str                 # "moto" | "caminhao"
    massa_kg: float           # massa do veículo vazio (com condutor)
    cd: float                 # coeficiente de arrasto
    area_m2: float            # área frontal
    mu: float                 # coeficiente de atrito/rolamento
    eta: float                # rendimento do motor (0-1)
    pc_kj_l: float            # poder calorífico do combustível (kJ/L)
    capacidade_kg: float
    vmax_kmh: float
    max_paradas: int
    kml_ref: float            # km/L de referência (calibração)
    fator_calibracao: float = 1.0

    def __post_init__(self) -> None:
        self.calibrar()

    @classmethod
    def de_linha(cls, linha: Mapping[str, Any]) -> "Veiculo":
        campos = (
            "id nome tipo massa_kg cd area_m2 mu eta pc_kj_l "
            "capacidade_kg vmax_kmh max_paradas kml_ref"
        ).split()
        return cls(**{c: linha[c] for c in campos})

    def calibrar(self) -> None:
        """Ajusta a escala para render ``kml_ref`` km/L vazio a VEL_REF_KMH."""
        self.fator_calibracao = 1.0
        modelo = litros_trecho(self, 0.0, 1.0, VEL_REF_KMH)
        self.fator_calibracao = (1.0 / self.kml_ref) / modelo

    @property
    def consumo_ref_l_km(self) -> float:
        """Consumo de referência (L/km), usado só em estimativas rápidas."""
        return 1.0 / self.kml_ref


def forca_atrito(massa_kg: float, mu: float) -> float:
    return mu * massa_kg * G


def forca_ar(cd: float, area_m2: float, v_ms: float) -> float:
    return 0.5 * RHO_AR * cd * area_m2 * v_ms ** 2


def forca_total(veic: Veiculo, carga_kg: float, v_kmh: float) -> float:
    massa = veic.massa_kg + max(0.0, carga_kg)
    v_ms = v_kmh / 3.6
    return forca_atrito(massa, veic.mu) + forca_ar(veic.cd, veic.area_m2, v_ms)


def potencia_w(veic: Veiculo, carga_kg: float, v_kmh: float) -> float:
    """P = F * v (potência mecânica necessária para manter a velocidade)."""
    return forca_total(veic, carga_kg, v_kmh) * (v_kmh / 3.6)


def litros_trecho(veic: Veiculo, carga_kg: float, dist_km: float, v_kmh: float) -> float:
    """Combustível (L) para percorrer ``dist_km`` a ``v_kmh`` com ``carga_kg``."""
    trabalho_kj = forca_total(veic, carga_kg, v_kmh) * dist_km   # N * km = kJ
    energia_combustivel_kj = trabalho_kj / veic.eta
    return veic.fator_calibracao * energia_combustivel_kj / veic.pc_kj_l


def veiculos_padrao() -> list[dict]:
    """Frota da Construlog: 2 motos e 1 caminhão pequeno (seção 3.1)."""
    moto = dict(
        tipo="moto", massa_kg=200.0, cd=0.7, area_m2=0.6, mu=0.02, eta=0.25,
        pc_kj_l=32000.0, capacidade_kg=50.0, vmax_kmh=60.0, max_paradas=10, kml_ref=8.0,
    )
    caminhao = dict(
        tipo="caminhao", massa_kg=3500.0, cd=0.8, area_m2=5.0, mu=0.012, eta=0.30,
        pc_kj_l=35800.0, capacidade_kg=1500.0, vmax_kmh=80.0, max_paradas=12, kml_ref=4.0,
    )
    return [
        {**moto, "nome": "Moto 1"},
        {**moto, "nome": "Moto 2"},
        {**caminhao, "nome": "Caminhão"},
    ]
