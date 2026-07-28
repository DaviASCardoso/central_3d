"""Testes da biblioteca de produtos."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from central.nucleo import descobrir
from central.ui import tema
from central.ui.biblioteca import (
    TODAS_AS_CATEGORIAS,
    Biblioteca,
    CardDeFalha,
    CardDeProduto,
    DialogoDeTraceback,
    corresponde,
)

pytestmark = pytest.mark.ui

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def registro_misto():
    """Registro com produtos válidos e produtos que falharam ao carregar."""
    return descobrir(FIXTURES / "produtos_teste")


@pytest.fixture
def biblioteca(qtbot, qapp, registro_misto):
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    widget = Biblioteca(registro_misto)
    qtbot.addWidget(widget)
    return widget


# --- busca ---------------------------------------------------------------


def _produto_de(registro, id_produto: str):
    return registro.obter(id_produto)


def test_busca_vazia_casa_com_tudo(registro_misto) -> None:
    assert corresponde(_produto_de(registro_misto, "cubo_simples"), "")
    assert corresponde(_produto_de(registro_misto, "cubo_simples"), "   ")


def test_busca_ignora_caixa(registro_misto) -> None:
    assert corresponde(_produto_de(registro_misto, "cubo_simples"), "CUBO")


def test_busca_ignora_acento(registro_misto) -> None:
    produto = _produto_de(registro_misto, "placa_com_submodulo")
    assert corresponde(produto, "submodulo")
    assert corresponde(produto, "SUBMÓDULO")


def test_busca_varre_as_tags(registro_misto) -> None:
    assert corresponde(_produto_de(registro_misto, "cubo_simples"), "teste")


def test_busca_varre_a_descricao(registro_misto) -> None:
    assert corresponde(_produto_de(registro_misto, "cubo_simples"), "sem submódulos")


def test_busca_que_nao_casa(registro_misto) -> None:
    assert not corresponde(_produto_de(registro_misto, "cubo_simples"), "guarda-chuva")


# --- grade ---------------------------------------------------------------


def test_grade_mostra_validos_e_falhos(biblioteca, registro_misto) -> None:
    esperados = len(registro_misto.produtos) + len(registro_misto.falhas)
    assert biblioteca.quantidade_de_cards() == esperados


def test_ha_card_vermelho_para_cada_falha(biblioteca, registro_misto) -> None:
    falhos = [c for c in biblioteca.cards() if isinstance(c, CardDeFalha)]
    assert len(falhos) == len(registro_misto.falhas)


def test_card_de_falha_usa_a_cor_de_erro(biblioteca) -> None:
    falho = next(c for c in biblioteca.cards() if isinstance(c, CardDeFalha))
    assert tema.ESCURA.erro.lower() in falho.styleSheet().lower()


def test_card_de_produto_mostra_nome_categoria_e_versao(biblioteca) -> None:
    from PySide6.QtWidgets import QLabel

    card = next(
        c
        for c in biblioteca.cards()
        if isinstance(c, CardDeProduto) and c.produto.id == "placa_com_submodulo"
    )
    textos = " | ".join(f.text() for f in card.findChildren(QLabel))
    assert "Placa com Submódulo" in textos
    assert "Papelaria" in textos
    assert "v2.1.0" in textos


def test_clique_no_card_emite_o_id(biblioteca, qtbot) -> None:
    card = next(c for c in biblioteca.cards() if isinstance(c, CardDeProduto))
    with qtbot.waitSignal(biblioteca.produto_escolhido) as capturado:
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert capturado.args == [card.produto.id]


# --- filtros -------------------------------------------------------------


def test_filtro_por_categoria(biblioteca) -> None:
    biblioteca.categoria.setCurrentText("Papelaria")
    visiveis = [p.id for p in biblioteca.produtos_visiveis()]
    assert visiveis == ["placa_com_submodulo"]


def test_todas_as_categorias_volta_a_mostrar_tudo(biblioteca, registro_misto) -> None:
    biblioteca.categoria.setCurrentText("Papelaria")
    biblioteca.categoria.setCurrentText(TODAS_AS_CATEGORIAS)
    assert len(biblioteca.produtos_visiveis()) == len(registro_misto.produtos)


def test_busca_filtra_a_grade(biblioteca) -> None:
    biblioteca.busca.setText("cubo")
    assert [p.id for p in biblioteca.produtos_visiveis()] == ["cubo_simples"]


def test_falhas_aparecem_mesmo_com_filtro_que_nao_casa(biblioteca, registro_misto) -> None:
    """Esconder produto quebrado é exatamente o que a seção 5 proíbe."""
    biblioteca.busca.setText("xyz-nada-casa-com-isto")
    assert biblioteca.produtos_visiveis() == []
    assert biblioteca.quantidade_de_cards() == len(registro_misto.falhas)


def test_combo_lista_as_categorias_do_registro(biblioteca, registro_misto) -> None:
    itens = [biblioteca.categoria.itemText(i) for i in range(biblioteca.categoria.count())]
    assert itens == [TODAS_AS_CATEGORIAS, *registro_misto.categorias()]


def test_mensagem_de_vazio_aparece_e_some(biblioteca) -> None:
    biblioteca.busca.setText("cubo")
    assert not biblioteca._vazio.isVisible()

    biblioteca.busca.setText("nada casa")
    biblioteca.categoria.setCurrentText("Papelaria")
    assert biblioteca.produtos_visiveis() == []


# --- traceback -----------------------------------------------------------


def test_dialogo_mostra_o_traceback(qtbot, registro_misto) -> None:
    falha = registro_misto.falhas["quebrado_no_import"]
    dialogo = DialogoDeTraceback(falha)
    qtbot.addWidget(dialogo)
    assert "Traceback" in dialogo.texto.toPlainText()
    assert "falha proposital" in dialogo.texto.toPlainText()


def test_traceback_e_selecionavel_e_somente_leitura(qtbot, registro_misto) -> None:
    dialogo = DialogoDeTraceback(registro_misto.falhas["quebrado_no_import"])
    qtbot.addWidget(dialogo)
    assert dialogo.texto.isReadOnly()


def test_pedir_traceback_de_falha_inexistente_nao_lanca(biblioteca) -> None:
    biblioteca.mostrar_traceback("nao_existe")


def test_registro_do_repositorio_nao_tem_falhas(qtbot, qapp) -> None:
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    widget = Biblioteca(descobrir())
    qtbot.addWidget(widget)
    assert all(isinstance(c, CardDeProduto) for c in widget.cards())
    assert any(c.produto.id == "placa_nome" for c in widget.cards())
