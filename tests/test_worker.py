"""Testes do worker de geração em thread."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from build123d import Box

from central.contrato import Param, Produto, TipoParam
from central.nucleo.cache import CacheEmMemoria, chave
from central.nucleo.cache_disco import CacheEmDisco
from central.nucleo.tesselagem import NivelTesselagem
from central.nucleo.worker import (
    Falha,
    GeradorEmThread,
    Pedido,
    TokenDeCancelamento,
)

pytestmark = pytest.mark.ui


def produto_de_teste(gerar=None, **extras: Any) -> Produto:
    def padrao(valores: dict[str, Any]):
        return Box(valores["lado"], 10, 10)

    base: dict[str, Any] = {
        "id": "teste",
        "nome": "Teste",
        "versao": "1.0.0",
        "descricao": "",
        "categoria": "Teste",
        "params": (
            Param(
                chave="lado",
                rotulo="Lado",
                tipo=TipoParam.DECIMAL,
                padrao=10.0,
                minimo=1.0,
                maximo=50.0,
            ),
        ),
        "gerar": gerar or padrao,
    }
    base.update(extras)
    return Produto(**base)


@pytest.fixture
def gerador(qapp):
    worker = GeradorEmThread()
    yield worker
    worker.encerrar()


# --- token ---------------------------------------------------------------


def test_token_comeca_ativo() -> None:
    token = TokenDeCancelamento()
    assert not token.cancelado
    token.conferir()


def test_token_cancelado_aborta() -> None:
    from central.nucleo.worker import Cancelado

    token = TokenDeCancelamento()
    token.cancelar()
    with pytest.raises(Cancelado):
        token.conferir()


# --- caminho feliz -------------------------------------------------------


def test_pedido_bem_sucedido_emite_pronto(gerador, qtbot) -> None:
    with qtbot.waitSignal(gerador.pronto, timeout=30_000) as capturado:
        gerador.agendar(produto_de_teste(), {"lado": 20.0})
    resultado = capturado.args[0]
    assert resultado.malhas["corpo_1"].is_watertight
    assert resultado.dimensoes[0] == pytest.approx(20.0)


def test_comecou_e_emitido_antes_de_pronto(gerador, qtbot) -> None:
    ordem: list[str] = []
    gerador.comecou.connect(lambda _s: ordem.append("comecou"))
    gerador.pronto.connect(lambda _r: ordem.append("pronto"))

    with qtbot.waitSignal(gerador.pronto, timeout=30_000):
        gerador.agendar(produto_de_teste(), {})
    assert ordem == ["comecou", "pronto"]


def test_geracao_roda_fora_da_thread_da_interface(gerador, qtbot) -> None:
    threads: list[int] = []

    def gerar(valores: dict[str, Any]):
        threads.append(threading.get_ident())
        return Box(valores["lado"], 10, 10)

    with qtbot.waitSignal(gerador.pronto, timeout=30_000):
        gerador.agendar(produto_de_teste(gerar), {})
    assert threads[0] != threading.get_ident()


# --- cancelamento --------------------------------------------------------


def test_novo_pedido_cancela_o_anterior(gerador, qtbot) -> None:
    """Cada edição cancela o pedido em curso antes de agendar o próximo."""
    liberar = threading.Event()
    entrou = threading.Event()

    def gerar_lento(valores: dict[str, Any]):
        entrou.set()
        liberar.wait(timeout=10)
        return Box(valores["lado"], 10, 10)

    produto = produto_de_teste(gerar_lento)
    cancelados: list[int] = []
    prontos: list[Any] = []
    gerador.cancelado.connect(cancelados.append)
    gerador.pronto.connect(prontos.append)

    primeiro = gerador.agendar(produto, {"lado": 10.0})
    assert entrou.wait(timeout=10)

    segundo = gerador.agendar(produto, {"lado": 20.0})
    liberar.set()

    qtbot.waitUntil(lambda: len(prontos) == 1, timeout=30_000)

    assert primeiro.token.cancelado
    assert not segundo.token.cancelado
    assert cancelados == [primeiro.sequencia]
    assert prontos[0].dimensoes[0] == pytest.approx(20.0)


def test_cancelar_pendente_sem_pedido_nao_lanca(gerador) -> None:
    gerador.cancelar_pendente()


def test_sequencia_cresce_a_cada_pedido(gerador) -> None:
    produto = produto_de_teste()
    primeiro = gerador.agendar(produto, {})
    segundo = gerador.agendar(produto, {})
    assert segundo.sequencia == primeiro.sequencia + 1
    assert gerador.sequencia_atual == segundo.sequencia


# --- falhas --------------------------------------------------------------


def test_erro_no_produto_emite_falha_com_traceback(gerador, qtbot) -> None:
    def gerar(_valores: dict[str, Any]):
        raise ZeroDivisionError("division by zero")

    with qtbot.waitSignal(gerador.falhou, timeout=30_000) as capturado:
        gerador.agendar(produto_de_teste(gerar), {})

    falha: Falha = capturado.args[0]
    assert "ZeroDivisionError" in falha.mensagem or "ZeroDivisionError" in falha.traceback_completo
    assert "Traceback" in falha.traceback_completo


def test_worker_sobrevive_a_uma_falha(gerador, qtbot) -> None:
    """Erro dentro de um produto jamais derruba a Central."""
    def gerar_quebrado(_valores: dict[str, Any]):
        raise RuntimeError("estourou")

    with qtbot.waitSignal(gerador.falhou, timeout=30_000):
        gerador.agendar(produto_de_teste(gerar_quebrado), {})

    with qtbot.waitSignal(gerador.pronto, timeout=30_000) as capturado:
        gerador.agendar(produto_de_teste(), {"lado": 15.0})
    assert capturado.args[0].dimensoes[0] == pytest.approx(15.0)


def test_valor_invalido_emite_falha_com_a_chave_culpada(gerador, qtbot) -> None:
    with qtbot.waitSignal(gerador.falhou, timeout=30_000) as capturado:
        gerador.agendar(produto_de_teste(), {"lado": 999.0})

    falha: Falha = capturado.args[0]
    assert "lado" in falha.erros_por_chave
    assert "máximo" in falha.erros_por_chave["lado"][0]


# --- cache ---------------------------------------------------------------


def test_segundo_pedido_identico_vem_do_cache(gerador, qtbot) -> None:
    chamadas: list[int] = []

    def gerar(valores: dict[str, Any]):
        chamadas.append(1)
        return Box(valores["lado"], 10, 10)

    produto = produto_de_teste(gerar)

    with qtbot.waitSignal(gerador.pronto, timeout=30_000):
        gerador.agendar(produto, {"lado": 12.0})
    with qtbot.waitSignal(gerador.pronto, timeout=30_000):
        gerador.agendar(produto, {"lado": 12.0})

    assert len(chamadas) == 1
    assert gerador.cache.estatisticas.acertos == 1


def test_cache_em_disco_e_consultado(qapp, qtbot, tmp_path: Path) -> None:
    disco = CacheEmDisco(diretorio=tmp_path / "cache")
    produto = produto_de_teste()

    primeiro = GeradorEmThread(cache_em_disco=disco)
    try:
        with qtbot.waitSignal(primeiro.pronto, timeout=30_000):
            primeiro.agendar(produto, {"lado": 13.0})
    finally:
        primeiro.encerrar()

    assert len(disco) == 1

    chamadas: list[int] = []

    def gerar_contando(valores: dict[str, Any]):
        chamadas.append(1)
        return Box(valores["lado"], 10, 10)

    segundo = GeradorEmThread(
        cache_em_memoria=CacheEmMemoria(),
        cache_em_disco=disco,
    )
    try:
        with qtbot.waitSignal(segundo.pronto, timeout=30_000) as capturado:
            segundo.agendar(produto_de_teste(gerar_contando), {"lado": 13.0})
    finally:
        segundo.encerrar()

    assert chamadas == []
    assert capturado.args[0].tem_solidos is False


def test_nivel_de_exportacao_nao_reaproveita_o_preview(gerador, qtbot) -> None:
    produto = produto_de_teste()

    with qtbot.waitSignal(gerador.pronto, timeout=30_000) as leve:
        gerador.agendar(produto, {"lado": 20.0}, NivelTesselagem.PREVIEW)
    with qtbot.waitSignal(gerador.pronto, timeout=30_000) as fina:
        gerador.agendar(produto, {"lado": 20.0}, NivelTesselagem.EXPORTACAO)

    assert fina.args[0].nivel is NivelTesselagem.EXPORTACAO
    assert fina.args[0].tem_solidos is True
    assert chave(produto, {"lado": 20.0}, NivelTesselagem.PREVIEW) != chave(
        produto, {"lado": 20.0}, NivelTesselagem.EXPORTACAO
    )
    assert leve.args[0] is not fina.args[0]


# --- encerramento --------------------------------------------------------


def test_encerrar_e_idempotente(qapp) -> None:
    worker = GeradorEmThread()
    worker.encerrar()
    worker.encerrar()


def test_encerrar_cancela_o_pedido_em_curso(qapp) -> None:
    liberar = threading.Event()

    def gerar_lento(valores: dict[str, Any]):
        liberar.wait(timeout=5)
        return Box(valores["lado"], 10, 10)

    worker = GeradorEmThread()
    pedido: Pedido = worker.agendar(produto_de_teste(gerar_lento), {})
    time.sleep(0.05)
    worker.encerrar(espera_em_ms=8000)
    liberar.set()

    assert pedido.token.cancelado
