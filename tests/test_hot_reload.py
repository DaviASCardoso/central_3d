"""Testes do recarregamento a quente dos módulos de produto."""

from __future__ import annotations

import shutil
import sys
import textwrap
import time
from pathlib import Path

import pytest

from central.contrato import Param, TipoParam
from central.nucleo.vigia import VigiaDeProdutos, preservar_valores

pytestmark = pytest.mark.ui

ESPERA = 15_000

MODELO_DE_PRODUTO = '''\
"""Produto de teste do recarregamento a quente."""

from __future__ import annotations

from typing import Any

from build123d import Box

from central.contrato import Param, Produto, TipoParam


def gerar(valores: dict[str, Any]) -> Box:
    """Devolve uma caixa do tamanho pedido."""
    return Box(valores["lado"], 10, 10)


MANIFESTO = Produto(
    id="quente",
    nome={nome!r},
    versao={versao!r},
    descricao="Produto que muda em disco durante o teste.",
    categoria="Teste",
    params=(
{params}
    ),
    gerar=gerar,
)
'''

PARAM_LADO = (
    '        Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),'
)
PARAM_ALTURA = (
    '        Param(chave="altura", rotulo="Altura", tipo=TipoParam.DECIMAL, padrao=3.0),'
)


def escrever_produto(
    diretorio: Path, nome: str = "Quente", versao: str = "1.0.0", params: str = PARAM_LADO
) -> Path:
    """Grava o pacote do produto de teste no diretório vigiado."""
    pacote = diretorio / "quente"
    pacote.mkdir(parents=True, exist_ok=True)
    arquivo = pacote / "__init__.py"
    arquivo.write_text(
        MODELO_DE_PRODUTO.format(nome=nome, versao=versao, params=params),
        encoding="utf-8",
    )
    return arquivo


@pytest.fixture
def diretorio_vigiado(tmp_path: Path):
    """Um diretório de produtos isolado, importável e limpo ao final."""
    raiz = tmp_path / f"produtos_quentes_{int(time.time() * 1000) % 100000}"
    raiz.mkdir()
    (raiz / "__init__.py").write_text(
        '"""Produtos de teste."""\n', encoding="utf-8"
    )
    escrever_produto(raiz)

    yield raiz

    for nome in [n for n in list(sys.modules) if n.split(".")[0] == raiz.name]:
        del sys.modules[nome]
    shutil.rmtree(raiz, ignore_errors=True)


@pytest.fixture
def vigia(diretorio_vigiado: Path, qapp):
    observador = VigiaDeProdutos(diretorio=diretorio_vigiado, silencio_em_ms=200)
    observador.recarregar()
    observador.iniciar()
    yield observador
    observador.encerrar()


# --- recarga manual ------------------------------------------------------


def test_registro_inicial_tem_o_produto(vigia) -> None:
    assert "quente" in vigia.registro
    assert vigia.registro.obter("quente").nome == "Quente"


def test_recarregar_reflete_a_mudanca_em_disco(vigia, diretorio_vigiado: Path) -> None:
    escrever_produto(diretorio_vigiado, nome="Quente Editado", versao="1.1.0")
    novo = vigia.recarregar()

    assert novo.obter("quente").nome == "Quente Editado"
    assert novo.obter("quente").versao == "1.1.0"


def test_recarregar_emite_o_registro(vigia, diretorio_vigiado: Path, qtbot) -> None:
    escrever_produto(diretorio_vigiado, nome="Outro Nome")
    with qtbot.waitSignal(vigia.registro_mudou, timeout=ESPERA) as capturado:
        vigia.recarregar()
    assert capturado.args[0].obter("quente").nome == "Outro Nome"


def test_recarregar_emite_os_produtos_invalidados(vigia, qtbot) -> None:
    with qtbot.waitSignal(vigia.produtos_invalidados, timeout=ESPERA) as capturado:
        vigia.recarregar()
    assert "quente" in capturado.args[0]


# --- disparo pelo observador de arquivos --------------------------------


def test_editar_em_disco_dispara_recarga(vigia, diretorio_vigiado: Path, qtbot) -> None:
    antes = vigia.recarregamentos
    escrever_produto(diretorio_vigiado, nome="Disparado")

    qtbot.waitUntil(lambda: vigia.recarregamentos > antes, timeout=ESPERA)
    assert vigia.registro.obter("quente").nome == "Disparado"


def test_gravacao_em_duas_etapas_dispara_uma_recarga_so(
    vigia, diretorio_vigiado: Path, qtbot
) -> None:
    """Editor que escreve e depois trunca produziria dois eventos seguidos."""
    antes = vigia.recarregamentos

    escrever_produto(diretorio_vigiado, nome="Parcial")
    time.sleep(0.05)
    escrever_produto(diretorio_vigiado, nome="Completo")

    qtbot.waitUntil(lambda: vigia.recarregamentos > antes, timeout=ESPERA)
    qtbot.wait(600)

    assert vigia.recarregamentos == antes + 1
    assert vigia.registro.obter("quente").nome == "Completo"


def test_arquivo_que_nao_e_python_nao_dispara(vigia, diretorio_vigiado: Path, qtbot) -> None:
    antes = vigia.recarregamentos
    (diretorio_vigiado / "anotacao.txt").write_text("nada", encoding="utf-8")
    qtbot.wait(700)
    assert vigia.recarregamentos == antes


# --- robustez ------------------------------------------------------------


def test_erro_de_sintaxe_mantem_a_versao_anterior_ativa(
    vigia, diretorio_vigiado: Path, qtbot
) -> None:
    """A seção 5 é explícita: falha de reload mantém a versão anterior ativa.

    O operador que digitou um erro de sintaxe no meio da edição continua vendo
    a última peça que funcionava, em vez de o produto sumir da biblioteca.
    """
    antes = vigia.recarregamentos
    (diretorio_vigiado / "quente" / "__init__.py").write_text(
        "isto ( nao e python valido\n", encoding="utf-8"
    )

    qtbot.waitUntil(lambda: vigia.recarregamentos > antes, timeout=ESPERA)

    assert "quente" in vigia.registro.produtos
    assert vigia.registro.obter("quente").nome == "Quente"
    assert "quente" not in vigia.registro.falhas


def test_produto_atualiza_depois_de_corrigido(
    vigia, diretorio_vigiado: Path, qtbot
) -> None:
    (diretorio_vigiado / "quente" / "__init__.py").write_text(
        "isto ( nao e python valido\n", encoding="utf-8"
    )
    antes = vigia.recarregamentos
    qtbot.waitUntil(lambda: vigia.recarregamentos > antes, timeout=ESPERA)

    escrever_produto(diretorio_vigiado, nome="Corrigido")
    qtbot.waitUntil(
        lambda: vigia.registro.obter("quente").nome == "Corrigido", timeout=ESPERA
    )


def test_encerrar_e_idempotente(vigia) -> None:
    vigia.encerrar()
    vigia.encerrar()


def test_iniciar_duas_vezes_nao_lanca(vigia) -> None:
    vigia.iniciar()


# --- submódulos ----------------------------------------------------------


def test_mudanca_em_submodulo_e_refletida(diretorio_vigiado: Path, qapp) -> None:
    """Recarregar o pacote antes do submódulo pegaria a versão velha."""
    pacote = diretorio_vigiado / "com_submodulo"
    pacote.mkdir()
    (pacote / "geometria.py").write_text(
        textwrap.dedent(
            '''\
            """Geometria do produto."""

            from typing import Any

            MARCA = "primeira"


            def gerar(valores: dict[str, Any]) -> dict[str, Any]:
                """Devolve os valores com a marca."""
                return {**valores, "marca": MARCA}
            '''
        ),
        encoding="utf-8",
    )
    (pacote / "__init__.py").write_text(
        textwrap.dedent(
            '''\
            """Produto com submódulo."""

            from central.contrato import Produto

            from .geometria import gerar

            MANIFESTO = Produto(
                id="com_submodulo",
                nome="Com Submodulo",
                versao="1.0.0",
                descricao="",
                categoria="Teste",
                params=(),
                gerar=gerar,
            )
            '''
        ),
        encoding="utf-8",
    )

    observador = VigiaDeProdutos(diretorio=diretorio_vigiado)
    try:
        observador.recarregar()
        assert observador.registro.obter("com_submodulo").gerar({})["marca"] == "primeira"

        (pacote / "geometria.py").write_text(
            (pacote / "geometria.py")
            .read_text(encoding="utf-8")
            .replace('"primeira"', '"segunda"'),
            encoding="utf-8",
        )
        observador.recarregar()
        assert observador.registro.obter("com_submodulo").gerar({})["marca"] == "segunda"
    finally:
        observador.encerrar()


# --- preservação de valores ---------------------------------------------


def test_valores_com_chave_sobrevivente_sao_mantidos() -> None:
    params = (
        Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),
        Param(chave="altura", rotulo="Altura", tipo=TipoParam.DECIMAL, padrao=3.0),
    )
    preservados = preservar_valores({"lado": 25.0, "altura": 7.0}, params)
    assert preservados == {"lado": 25.0, "altura": 7.0}


def test_valor_de_chave_que_sumiu_e_descartado() -> None:
    """O que sumiu do manifesto volta ao padrão, e quem devolve é o inspetor."""
    params = (Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),)
    preservados = preservar_valores({"lado": 25.0, "altura": 7.0}, params)
    assert preservados == {"lado": 25.0}


def test_sem_valores_anteriores_devolve_vazio() -> None:
    params = (Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),)
    assert preservar_valores({}, params) == {}


# --- integração com a janela --------------------------------------------


def test_janela_preserva_o_valor_editado_ao_recarregar(
    diretorio_vigiado: Path, qtbot, qapp
) -> None:
    from central.nucleo import descobrir
    from central.ui import tema
    from central.ui.janela import JanelaPrincipal

    tema.aplicar(qapp, tema.Esquema.ESCURO)
    escrever_produto(diretorio_vigiado, params=f"{PARAM_LADO}\n{PARAM_ALTURA}")

    janela = JanelaPrincipal(descobrir(diretorio_vigiado), vigiar=False)
    qtbot.addWidget(janela)
    try:
        janela.vigia.diretorio = diretorio_vigiado
        janela.vigia.registro = janela.registro

        with qtbot.waitSignal(janela.editor.gerado, timeout=ESPERA):
            janela.abrir_no_editor("quente")
        janela.editor.inspetor.campos["lado"].widget.setValue(42.0)

        # O produto perde o parâmetro "altura" e ganha uma versão nova.
        escrever_produto(diretorio_vigiado, versao="2.0.0", params=PARAM_LADO)
        with qtbot.waitSignal(janela.editor.gerado, timeout=ESPERA):
            janela.vigia.recarregar()

        assert janela.editor.produto.versao == "2.0.0"
        assert janela.editor.inspetor.valores()["lado"] == pytest.approx(42.0)
        assert "altura" not in janela.editor.inspetor.valores()
    finally:
        janela.vigia.encerrar()
        janela.editor.encerrar()
