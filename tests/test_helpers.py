"""Testes dos utilitários de geometria."""

from __future__ import annotations

import pytest
from build123d import Box, Cylinder, Pos

from central.nucleo.erros import ErroDeGeometria
from central.nucleo.helpers import (
    assentar_na_mesa,
    conferir_fonte,
    dimensoes,
    fontes_disponiveis,
    texto_solido,
)

FONTE = "Arial"


# --- fontes --------------------------------------------------------------


def test_ha_fontes_disponiveis() -> None:
    assert len(fontes_disponiveis()) > 0


def test_arial_existe_e_e_aceita() -> None:
    conferir_fonte(FONTE)


def test_fonte_inexistente_e_recusada_em_vez_de_substituida() -> None:
    with pytest.raises(ErroDeGeometria, match="não existe nesta máquina"):
        conferir_fonte("Fonte Que Nao Existe 12345")


def test_mensagem_de_fonte_sugere_parecidas() -> None:
    with pytest.raises(ErroDeGeometria, match="Parecidas:"):
        conferir_fonte("Aria")


# --- texto_solido --------------------------------------------------------


def test_texto_solido_produz_volume_positivo() -> None:
    solido = texto_solido("Ana", FONTE, 10.0, 1.0)
    assert solido.volume > 0


def test_texto_solido_e_memoizado() -> None:
    texto_solido.cache_clear()
    primeiro = texto_solido("Memo", FONTE, 8.0, 0.8)
    assert texto_solido.cache_info().hits == 0

    segundo = texto_solido("Memo", FONTE, 8.0, 0.8)
    assert texto_solido.cache_info().hits == 1
    assert segundo is primeiro


def test_cache_distingue_cada_componente_da_tupla() -> None:
    texto_solido.cache_clear()
    texto_solido("A", FONTE, 8.0, 0.8)
    texto_solido("B", FONTE, 8.0, 0.8)
    texto_solido("A", FONTE, 9.0, 0.8)
    texto_solido("A", FONTE, 8.0, 1.0)
    assert texto_solido.cache_info().currsize == 4
    assert texto_solido.cache_info().hits == 0


def test_espessura_vira_a_altura_do_solido() -> None:
    _, _, z = dimensoes(texto_solido("Ana", FONTE, 10.0, 1.5))
    assert z == pytest.approx(1.5)


def test_tamanho_maior_produz_texto_mais_largo() -> None:
    pequeno, _, _ = dimensoes(texto_solido("Ana", FONTE, 5.0, 1.0))
    grande, _, _ = dimensoes(texto_solido("Ana", FONTE, 10.0, 1.0))
    assert grande > pequeno


def test_texto_solido_vem_centrado_em_xy_com_base_em_zero() -> None:
    caixa = texto_solido("Helena", FONTE, 9.0, 1.0).bounding_box()
    assert caixa.center().X == pytest.approx(0.0, abs=1e-6)
    assert caixa.center().Y == pytest.approx(0.0, abs=1e-6)
    assert caixa.min.Z == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("texto", ["", "   ", "\t"])
def test_texto_vazio_e_recusado(texto: str) -> None:
    with pytest.raises(ErroDeGeometria, match="texto vazio"):
        texto_solido(texto, FONTE, 10.0, 1.0)


@pytest.mark.parametrize(("tamanho", "espessura"), [(0.0, 1.0), (-1.0, 1.0)])
def test_tamanho_nao_positivo_e_recusado(tamanho: float, espessura: float) -> None:
    with pytest.raises(ErroDeGeometria, match="tamanho de fonte"):
        texto_solido("Ana", FONTE, tamanho, espessura)


@pytest.mark.parametrize("espessura", [0.0, -0.5])
def test_espessura_nao_positiva_e_recusada(espessura: float) -> None:
    with pytest.raises(ErroDeGeometria, match="espessura"):
        texto_solido("Ana", FONTE, 10.0, espessura)


def test_fonte_inexistente_recusada_tambem_pelo_texto_solido() -> None:
    with pytest.raises(ErroDeGeometria, match="não existe nesta máquina"):
        texto_solido("Ana", "Fonte Que Nao Existe 12345", 10.0, 1.0)


# --- dimensoes e assentar_na_mesa ---------------------------------------


def test_dimensoes_da_caixa() -> None:
    assert dimensoes(Box(10, 20, 30)) == pytest.approx((10.0, 20.0, 30.0))


def test_assentar_poe_minimo_z_em_zero_e_centro_xy_na_origem() -> None:
    deslocada = Pos(37.5, -12.25, 88.0) * Box(10, 20, 30)
    caixa = assentar_na_mesa(deslocada).bounding_box()
    assert caixa.min.Z == pytest.approx(0.0, abs=1e-6)
    assert caixa.center().X == pytest.approx(0.0, abs=1e-6)
    assert caixa.center().Y == pytest.approx(0.0, abs=1e-6)


def test_assentar_sobe_peca_que_estava_abaixo_da_mesa() -> None:
    afundada = Pos(0, 0, -50) * Cylinder(radius=5, height=10)
    assert assentar_na_mesa(afundada).bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)


def test_assentar_preserva_as_dimensoes() -> None:
    original = Pos(3, 4, 5) * Box(10, 20, 30)
    assert dimensoes(assentar_na_mesa(original)) == pytest.approx(dimensoes(original))


def test_assentar_nao_modifica_a_forma_original() -> None:
    original = Pos(0, 0, 50) * Box(10, 20, 30)
    antes = original.bounding_box().min.Z
    assentar_na_mesa(original)
    assert original.bounding_box().min.Z == pytest.approx(antes)
