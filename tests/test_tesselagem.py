"""Testes da tesselagem."""

from __future__ import annotations

import math

import pytest
from build123d import Box, Cylinder, Sphere

from central.nucleo.tesselagem import DESVIOS, NivelTesselagem, tesselar

RAIO = 20.0
ALTURA = 10.0
VOLUME_ANALITICO = math.pi * RAIO**2 * ALTURA


@pytest.fixture(scope="module")
def cilindro():
    return Cylinder(radius=RAIO, height=ALTURA)


@pytest.mark.parametrize("nivel", list(NivelTesselagem))
def test_malha_e_estanque_em_ambos_os_niveis(cilindro, nivel: NivelTesselagem) -> None:
    malha = tesselar(cilindro, nivel)
    assert malha.is_watertight
    assert malha.is_winding_consistent
    assert malha.volume > 0


def test_exportacao_fica_dentro_de_um_decimo_de_por_cento(cilindro) -> None:
    malha = tesselar(cilindro, NivelTesselagem.EXPORTACAO)
    erro = abs(malha.volume - VOLUME_ANALITICO) / VOLUME_ANALITICO
    assert erro < 0.001, f"erro de volume de {erro:.4%}"


def test_preview_e_mais_leve_que_exportacao(cilindro) -> None:
    leve = tesselar(cilindro, NivelTesselagem.PREVIEW)
    fina = tesselar(cilindro, NivelTesselagem.EXPORTACAO)
    assert len(leve.faces) < len(fina.faces)


def test_exportacao_e_mais_fiel_que_preview(cilindro) -> None:
    def erro(nivel: NivelTesselagem) -> float:
        return abs(tesselar(cilindro, nivel).volume - VOLUME_ANALITICO)

    assert erro(NivelTesselagem.EXPORTACAO) < erro(NivelTesselagem.PREVIEW)


def test_desvios_sao_os_da_secao_6() -> None:
    assert DESVIOS[NivelTesselagem.PREVIEW].linear == 0.08
    assert DESVIOS[NivelTesselagem.PREVIEW].angular == 0.5
    assert DESVIOS[NivelTesselagem.EXPORTACAO].linear == 0.015
    assert DESVIOS[NivelTesselagem.EXPORTACAO].angular == 0.2


def test_desvio_e_absoluto_e_nao_relativo() -> None:
    """Peça dez vezes maior, com desvio absoluto, precisa de muito mais malha.

    Com `isRelative=True` a contagem de triângulos seria praticamente a mesma
    nos dois tamanhos, porque a tolerância acompanharia a aresta.
    """
    pequeno = tesselar(Cylinder(radius=1, height=1), NivelTesselagem.EXPORTACAO)
    grande = tesselar(Cylinder(radius=100, height=50), NivelTesselagem.EXPORTACAO)
    assert len(grande.faces) > 2 * len(pequeno.faces)


def test_resultado_nao_depende_da_ordem_das_chamadas() -> None:
    """O OCCT guarda a triangulação dentro da forma e reaproveitaria a fina.

    Sem limpar a triangulação anterior, pedir EXPORTACAO e depois PREVIEW na
    mesma forma devolveria a malha fina, e a malha passaria a depender do
    histórico de chamadas — o que corromperia um cache indexado por hash.
    """
    forma = Cylinder(radius=RAIO, height=ALTURA)
    leve_antes = len(tesselar(forma, NivelTesselagem.PREVIEW).faces)
    tesselar(forma, NivelTesselagem.EXPORTACAO)
    leve_depois = len(tesselar(forma, NivelTesselagem.PREVIEW).faces)
    assert leve_depois == leve_antes


def test_caixa_tem_a_malha_minima_de_um_paralelepipedo() -> None:
    malha = tesselar(Box(10, 20, 30), NivelTesselagem.PREVIEW)
    assert len(malha.faces) == 12
    assert malha.is_watertight
    assert malha.volume == pytest.approx(6000.0)


def test_vertices_sao_soldados() -> None:
    """Sem soldagem o cubo teria 24 vértices, quatro por face."""
    assert len(tesselar(Box(10, 10, 10), NivelTesselagem.PREVIEW).vertices) == 8


def test_esfera_tambem_sai_estanque() -> None:
    malha = tesselar(Sphere(radius=15), NivelTesselagem.EXPORTACAO)
    assert malha.is_watertight
    erro = abs(malha.volume - (4 / 3) * math.pi * 15**3) / ((4 / 3) * math.pi * 15**3)
    assert erro < 0.002
