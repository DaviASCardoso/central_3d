"""Testes do inspetor gerado a partir da declaração de parâmetros."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

from central.contrato import Param, Produto, TipoParam
from central.nucleo import descobrir
from central.ui import tema
from central.ui.inspetor import (
    BotoesSegmentados,
    CampoDeCor,
    CampoDeTexto,
    DecimalComSlider,
    Inspetor,
    montar_widget,
)

pytestmark = pytest.mark.ui


def um_de_cada_tipo() -> tuple[Param, ...]:
    return (
        Param(chave="texto", rotulo="Texto", tipo=TipoParam.TEXTO, padrao="Ana", max_len=10),
        Param(chave="texto_livre", rotulo="Livre", tipo=TipoParam.TEXTO, padrao="x"),
        Param(
            chave="inteiro",
            rotulo="Inteiro",
            tipo=TipoParam.INTEIRO,
            padrao=3,
            minimo=1,
            maximo=9,
        ),
        Param(
            chave="decimal_limitado",
            rotulo="Limitado",
            tipo=TipoParam.DECIMAL,
            padrao=2.0,
            minimo=1.0,
            maximo=5.0,
            passo=0.5,
            unidade="mm",
        ),
        Param(chave="decimal_livre", rotulo="Livre", tipo=TipoParam.DECIMAL, padrao=1.5),
        Param(chave="booleano", rotulo="Booleano", tipo=TipoParam.BOOLEANO, padrao=True),
        Param(
            chave="poucas_opcoes",
            rotulo="Poucas",
            tipo=TipoParam.ESCOLHA,
            padrao="a",
            opcoes=("a", "b", "c"),
        ),
        Param(
            chave="muitas_opcoes",
            rotulo="Muitas",
            tipo=TipoParam.ESCOLHA,
            padrao="um",
            opcoes=("um", "dois", "tres", "quatro"),
        ),
        Param(chave="cor", rotulo="Cor", tipo=TipoParam.COR, padrao="#8AB4F8"),
    )


def produto_de_teste(params: tuple[Param, ...] | None = None) -> Produto:
    return Produto(
        id="teste",
        nome="Teste",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=params if params is not None else um_de_cada_tipo(),
        gerar=lambda valores: valores,
    )


@pytest.fixture
def inspetor(qtbot, qapp):
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    widget = Inspetor(produto_de_teste())
    qtbot.addWidget(widget)
    return widget


# --- mapeamento fixo de tipo para widget ---------------------------------


@pytest.mark.parametrize(
    ("chave", "classe"),
    [
        ("texto", CampoDeTexto),
        ("texto_livre", CampoDeTexto),
        ("inteiro", QSpinBox),
        ("decimal_limitado", DecimalComSlider),
        ("decimal_livre", QDoubleSpinBox),
        ("booleano", QCheckBox),
        ("poucas_opcoes", BotoesSegmentados),
        ("muitas_opcoes", QComboBox),
        ("cor", CampoDeCor),
    ],
)
def test_cada_tipo_gera_o_widget_esperado(inspetor, chave: str, classe: type) -> None:
    assert isinstance(inspetor.campos[chave].widget, classe)


def test_tipo_sem_mapeamento_levanta() -> None:
    param = Param(chave="x", rotulo="X", tipo="inexistente", padrao=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sem mapeamento"):
        montar_widget(param)


# --- valores -------------------------------------------------------------


def test_valores_iniciais_sao_os_padroes(inspetor) -> None:
    valores = inspetor.valores()
    assert valores["texto"] == "Ana"
    assert valores["inteiro"] == 3
    assert valores["decimal_limitado"] == pytest.approx(2.0)
    assert valores["booleano"] is True
    assert valores["poucas_opcoes"] == "a"
    assert valores["muitas_opcoes"] == "um"
    assert valores["cor"] == "#8AB4F8"


def test_editar_emite_o_dicionario_completo(inspetor, qtbot) -> None:
    campo = inspetor.campos["texto"].widget
    with qtbot.waitSignal(inspetor.valores_mudaram) as capturado:
        campo.linha.setText("Helena")
    assert capturado.args[0]["texto"] == "Helena"
    assert set(capturado.args[0]) == set(inspetor.campos)


def test_definir_valores_nao_dispara_geracao(inspetor, qtbot) -> None:
    with qtbot.assertNotEmitted(inspetor.valores_mudaram):
        inspetor.definir_valores({"texto": "Bia", "inteiro": 7})
    assert inspetor.valores()["texto"] == "Bia"
    assert inspetor.valores()["inteiro"] == 7


def test_chave_ausente_volta_ao_padrao(inspetor) -> None:
    inspetor.definir_valores({"texto": "Bia"})
    assert inspetor.valores()["inteiro"] == 3


def test_chave_desconhecida_e_ignorada(inspetor) -> None:
    inspetor.definir_valores({"nao_existe": 42})
    assert "nao_existe" not in inspetor.valores()


def test_restaurar_padroes_volta_tudo(inspetor, qtbot) -> None:
    inspetor.definir_valores({"texto": "Bia", "inteiro": 8, "booleano": False})
    with qtbot.waitSignal(inspetor.valores_mudaram):
        inspetor.restaurar_padroes()
    assert inspetor.valores()["texto"] == "Ana"
    assert inspetor.valores()["inteiro"] == 3
    assert inspetor.valores()["booleano"] is True


# --- slider e spinbox acoplados -----------------------------------------


def test_slider_e_spin_ficam_em_sincronia(inspetor) -> None:
    campo = inspetor.campos["decimal_limitado"].widget
    campo.spin.setValue(4.0)
    assert campo.slider.value() == campo._para_slider(4.0)

    campo.slider.setValue(campo._para_slider(1.5))
    assert campo.spin.value() == pytest.approx(1.5)


def test_slider_respeita_os_limites(inspetor) -> None:
    campo = inspetor.campos["decimal_limitado"].widget
    campo.spin.setValue(99.0)
    assert campo.valor() == pytest.approx(5.0)
    campo.spin.setValue(-99.0)
    assert campo.valor() == pytest.approx(1.0)


def test_unidade_aparece_como_sufixo_e_nao_no_rotulo(inspetor) -> None:
    campo = inspetor.campos["decimal_limitado"]
    assert campo.widget.spin.suffix().strip() == "mm"
    assert "mm" not in campo.rotulo.text()


def test_contador_de_caracteres_com_max_len(inspetor) -> None:
    campo = inspetor.campos["texto"].widget
    assert campo.contador is not None
    assert campo.contador.text() == "3/10"
    campo.linha.setText("Helena")
    assert campo.contador.text() == "6/10"


def test_sem_max_len_nao_ha_contador(inspetor) -> None:
    assert inspetor.campos["texto_livre"].widget.contador is None


def test_max_len_limita_a_digitacao(inspetor) -> None:
    campo = inspetor.campos["texto"].widget
    campo.linha.setText("x" * 30)
    assert len(campo.valor()) == 10


# --- grupos e avançado ---------------------------------------------------


def test_avancados_ficam_em_secao_colapsada_e_fechada(qtbot, qapp) -> None:
    params = (
        Param(chave="normal", rotulo="Normal", tipo=TipoParam.INTEIRO, padrao=1),
        Param(chave="oculto", rotulo="Oculto", tipo=TipoParam.INTEIRO, padrao=2, avancado=True),
    )
    inspetor = Inspetor(produto_de_teste(params))
    qtbot.addWidget(inspetor)

    assert inspetor.secao_avancada is not None
    assert not inspetor.secao_avancada.esta_aberta()
    assert "oculto" in inspetor.valores()

    inspetor.secao_avancada.abrir()
    assert inspetor.secao_avancada.esta_aberta()


def test_sem_avancados_nao_ha_secao(qtbot, qapp) -> None:
    params = (Param(chave="normal", rotulo="Normal", tipo=TipoParam.INTEIRO, padrao=1),)
    inspetor = Inspetor(produto_de_teste(params))
    qtbot.addWidget(inspetor)
    assert inspetor.secao_avancada is None


def test_grupos_aparecem_na_ordem_de_declaracao(qtbot, qapp) -> None:
    from PySide6.QtWidgets import QGroupBox

    params = (
        Param(chave="a", rotulo="A", tipo=TipoParam.INTEIRO, padrao=1, grupo="Segundo"),
        Param(chave="b", rotulo="B", tipo=TipoParam.INTEIRO, padrao=1, grupo="Primeiro"),
    )
    inspetor = Inspetor(produto_de_teste(params))
    qtbot.addWidget(inspetor)
    titulos = [c.title() for c in inspetor.findChildren(QGroupBox)]
    assert titulos == ["Segundo", "Primeiro"]


# --- visivel_se ----------------------------------------------------------


def _params_condicionais() -> tuple[Param, ...]:
    return (
        Param(chave="tem_furo", rotulo="Tem furo", tipo=TipoParam.BOOLEANO, padrao=False),
        Param(
            chave="diametro",
            rotulo="Diâmetro",
            tipo=TipoParam.DECIMAL,
            padrao=4.0,
            minimo=1.0,
            maximo=10.0,
            visivel_se=lambda v: bool(v["tem_furo"]),
        ),
    )


def test_campo_condicional_nasce_escondido(qtbot, qapp) -> None:
    inspetor = Inspetor(produto_de_teste(_params_condicionais()))
    qtbot.addWidget(inspetor)
    inspetor.show()
    qtbot.waitExposed(inspetor)
    assert "diametro" not in inspetor.campos_visiveis()


def test_campo_condicional_aparece_ao_mudar_a_condicao(qtbot, qapp) -> None:
    inspetor = Inspetor(produto_de_teste(_params_condicionais()))
    qtbot.addWidget(inspetor)
    inspetor.show()
    qtbot.waitExposed(inspetor)

    inspetor.campos["tem_furo"].widget.setChecked(True)
    assert "diametro" in inspetor.campos_visiveis()


def test_campo_escondido_mantem_o_valor_e_segue_no_dicionario(qtbot, qapp) -> None:
    """O contrato exige que campo escondido continue sendo passado a gerar."""
    inspetor = Inspetor(produto_de_teste(_params_condicionais()))
    qtbot.addWidget(inspetor)
    inspetor.show()
    qtbot.waitExposed(inspetor)

    inspetor.campos["tem_furo"].widget.setChecked(True)
    inspetor.campos["diametro"].widget.spin.setValue(7.5)
    inspetor.campos["tem_furo"].widget.setChecked(False)

    valores = inspetor.valores()
    assert "diametro" in valores
    assert valores["diametro"] == pytest.approx(7.5)


# --- grifo de erro -------------------------------------------------------


def test_grifar_marca_o_campo_culpado(inspetor) -> None:
    inspetor.grifar_erros({"inteiro": ["é maior que o máximo de 9"]})
    campo = inspetor.campos["inteiro"]
    assert tema.ESCURA.erro.lower() in campo.rotulo.styleSheet().lower()
    assert "máximo" in campo.widget.toolTip()


def test_grifar_limpa_os_campos_sem_erro(inspetor) -> None:
    inspetor.grifar_erros({"inteiro": ["erro"]})
    inspetor.grifar_erros({})
    assert inspetor.campos["inteiro"].rotulo.styleSheet() == ""


# --- com o produto de verdade -------------------------------------------


def test_inspetor_monta_a_placa_nome(qtbot, qapp) -> None:
    produto = descobrir().obter("placa_nome")
    inspetor = Inspetor(produto)
    qtbot.addWidget(inspetor)

    assert set(inspetor.campos) == {p.chave for p in produto.params}
    assert isinstance(inspetor.campos["nome"].widget, CampoDeTexto)
    assert isinstance(inspetor.campos["altura_texto"].widget, DecimalComSlider)
    assert isinstance(inspetor.campos["fonte"].widget, QComboBox)
    assert isinstance(inspetor.campos["cor"].widget, CampoDeCor)
    assert inspetor.secao_avancada is not None


def test_valores_do_inspetor_geram_a_placa(qtbot, qapp) -> None:
    """A ponte entre interface e núcleo: o dicionário emitido é gerável."""
    from central.nucleo.geracao import gerar_sincrono

    produto = descobrir().obter("placa_nome")
    inspetor = Inspetor(produto)
    qtbot.addWidget(inspetor)

    saida = gerar_sincrono(produto, inspetor.valores())
    assert saida.malhas["placa"].is_watertight
