"""Testes da viewport.

Estes testes criam janela de verdade, porque o VTK precisa de contexto de
OpenGL para renderizar. São de fumaça, conforme a seção 15 do CENTRAL.md, mais
o teste da câmera, que protege o comportamento da seção 7 que mais afeta a
percepção de qualidade.
"""

from __future__ import annotations

import pytest
from build123d import Box, Cylinder

from central.nucleo.impressora import VOLUME_DE_CONSTRUCAO
from central.nucleo.tesselagem import NivelTesselagem, tesselar
from central.ui import tema
from central.ui.viewport import (
    OPACIDADE_GERANDO,
    OPACIDADE_NORMAL,
    Viewport,
    malha_para_polydata,
)

pytestmark = pytest.mark.ui

ATORES_DA_CENA_FIXA = 3
"""Grade, perímetro e arestas do volume de construção."""


@pytest.fixture
def malha_cubo():
    return tesselar(Box(20, 20, 20), NivelTesselagem.PREVIEW)


@pytest.fixture
def malha_cilindro():
    return tesselar(Cylinder(radius=15, height=30), NivelTesselagem.PREVIEW)


@pytest.fixture
def viewport(qtbot, qapp):
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    widget = Viewport()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget.iniciar()
    yield widget
    widget.encerrar()


# --- conversão de malha --------------------------------------------------


def test_polydata_preserva_vertices_e_triangulos(malha_cubo) -> None:
    polydata = malha_para_polydata(malha_cubo)
    assert polydata.GetNumberOfPoints() == len(malha_cubo.vertices)
    assert polydata.GetNumberOfPolys() == len(malha_cubo.faces)


# --- cena fixa -----------------------------------------------------------


def test_cena_nasce_com_mesa_e_volume(viewport) -> None:
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA


def test_fundo_vem_do_tema(viewport) -> None:
    fundo = viewport._renderer.GetBackground()
    assert 0.0 <= min(fundo) <= max(fundo) <= 1.0
    assert max(fundo) < 0.5, "o tema escuro não deveria produzir fundo claro"


def test_ha_tres_luzes_direcionais(viewport) -> None:
    assert viewport._renderer.GetLights().GetNumberOfItems() == 3


def test_a_mesa_tem_o_tamanho_do_volume_de_construcao(viewport) -> None:
    limites = viewport._ator_perimetro.GetBounds()
    assert limites[1] - limites[0] == pytest.approx(VOLUME_DE_CONSTRUCAO.x)
    assert limites[3] - limites[2] == pytest.approx(VOLUME_DE_CONSTRUCAO.y)


def test_as_arestas_do_volume_sobem_ate_a_altura_maxima(viewport) -> None:
    limites = viewport._ator_volume.GetBounds()
    assert limites[5] == pytest.approx(VOLUME_DE_CONSTRUCAO.z)


# --- peça ----------------------------------------------------------------


def test_mostrar_acrescenta_um_ator_por_corpo(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo})
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA + 1


def test_dois_corpos_dois_atores(viewport, malha_cubo, malha_cilindro) -> None:
    viewport.mostrar({"base": malha_cubo, "tampa": malha_cilindro})
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA + 2


def test_trocar_a_malha_reaproveita_o_mesmo_ator(
    viewport, malha_cubo, malha_cilindro
) -> None:
    """A seção 7 exige swap de vtkPolyData no mesmo ator, sem recriar a cena."""
    viewport.mostrar({"placa": malha_cubo})
    antes = viewport.ator_do_corpo("placa")

    viewport.mostrar({"placa": malha_cilindro})
    assert viewport.ator_do_corpo("placa") is antes
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA + 1


def test_a_camera_nao_se_move_ao_trocar_de_malha(
    viewport, malha_cubo, malha_cilindro
) -> None:
    """Ver a câmera pular a cada slider destrói o senso de edição contínua."""
    viewport.mostrar({"placa": malha_cubo})
    posicao = viewport.posicao_da_camera()

    viewport.mostrar({"placa": malha_cilindro})
    assert viewport.posicao_da_camera() == pytest.approx(posicao)


def test_a_primeira_carga_enquadra_a_peca(viewport, malha_cubo) -> None:
    inicial = viewport.posicao_da_camera()
    viewport.mostrar({"placa": malha_cubo})
    assert viewport.posicao_da_camera() != pytest.approx(inicial)


def test_corpo_que_some_tem_o_ator_removido(viewport, malha_cubo, malha_cilindro) -> None:
    viewport.mostrar({"base": malha_cubo, "tampa": malha_cilindro})
    viewport.mostrar({"base": malha_cubo})
    assert viewport.ator_do_corpo("tampa") is None
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA + 1


def test_cor_declarada_chega_ao_ator(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo}, cores={"placa": "#FF0000"})
    cor = viewport.ator_do_corpo("placa").GetProperty().GetColor()
    assert cor == pytest.approx((1.0, 0.0, 0.0))


def test_peca_que_excede_o_volume_fica_vermelha_e_transparente(
    viewport, malha_cubo
) -> None:
    viewport.mostrar({"placa": malha_cubo}, excede_volume=True)
    propriedade = viewport.ator_do_corpo("placa").GetProperty()
    vermelho, verde, azul = propriedade.GetColor()
    assert vermelho > verde and vermelho > azul
    assert propriedade.GetOpacity() < OPACIDADE_NORMAL


def test_material_e_fosco_com_leve_especularidade(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo})
    propriedade = viewport.ator_do_corpo("placa").GetProperty()
    assert propriedade.GetSpecular() < 0.3
    assert propriedade.GetDiffuse() > 0.7


def test_visibilidade_por_corpo(viewport, malha_cubo, malha_cilindro) -> None:
    viewport.mostrar({"base": malha_cubo, "tampa": malha_cilindro})
    viewport.definir_visibilidade("tampa", False)
    assert viewport.ator_do_corpo("tampa").GetVisibility() == 0
    assert viewport.ator_do_corpo("base").GetVisibility() == 1

    viewport.definir_visibilidade("tampa", True)
    assert viewport.ator_do_corpo("tampa").GetVisibility() == 1


def test_visibilidade_de_corpo_inexistente_nao_lanca(viewport) -> None:
    viewport.definir_visibilidade("nao_existe", False)


def test_opacidade_de_geracao_esmaece_e_volta(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo})
    viewport.definir_opacidade_de_geracao(True)
    assert viewport.ator_do_corpo("placa").GetProperty().GetOpacity() == pytest.approx(
        OPACIDADE_GERANDO
    )

    viewport.definir_opacidade_de_geracao(False)
    assert viewport.ator_do_corpo("placa").GetProperty().GetOpacity() == pytest.approx(
        OPACIDADE_NORMAL
    )


def test_limpar_tira_a_peca_e_mantem_a_mesa(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo})
    viewport.limpar()
    assert viewport.quantidade_de_atores() == ATORES_DA_CENA_FIXA
    assert viewport.ator_do_corpo("placa") is None


def test_renderizar_de_verdade_nao_lanca(viewport, malha_cubo) -> None:
    viewport.mostrar({"placa": malha_cubo})
    viewport.redesenhar()
