"""Geração fora da thread da interface.

Cada nova edição de parâmetro cancela o token do pedido anterior antes de
agendar o novo, e o worker verifica o token entre as etapas do pipeline para
abortar cedo. Uma etapa que já começou dentro do OCCT não pode ser
interrompida no meio, então o cancelamento é cooperativo entre etapas e não
instantâneo — isso é aceitável e não deve ser contornado com terminação
forçada de thread. Ver a seção 6 do CENTRAL.md.

Este módulo importa Qt, o que é a única exceção da camada de núcleo: `QThread`
e os sinais são o mecanismo de concorrência do aplicativo, não interface. Nada
aqui monta widget nem conhece janela.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from central.contrato import Produto
from central.log import obter
from central.nucleo.cache import CacheEmMemoria, chave
from central.nucleo.cache_disco import CacheEmDisco
from central.nucleo.erros import ErroCentral, ErroDeValidacao
from central.nucleo.geracao import ResultadoGeracao, executar_pipeline
from central.nucleo.tesselagem import NivelTesselagem
from central.nucleo.validacao import validar

_log = obter(__name__)


class Cancelado(ErroCentral):
    """O pedido foi cancelado entre duas etapas do pipeline."""


@dataclass(slots=True)
class TokenDeCancelamento:
    """Bandeira cooperativa, verificada entre as etapas do pipeline.

    Attributes:
        cancelado: Verdadeiro depois que `cancelar` foi chamado.
    """

    cancelado: bool = False

    def cancelar(self) -> None:
        """Pede que o pedido pare na próxima fronteira de etapa."""
        self.cancelado = True

    def conferir(self) -> None:
        """Aborta se o token já foi cancelado.

        Raises:
            Cancelado: Se `cancelar` foi chamado.
        """
        if self.cancelado:
            raise Cancelado("pedido cancelado")


@dataclass(slots=True)
class Pedido:
    """Uma intenção de gerar.

    Attributes:
        produto: O manifesto a gerar.
        valores: Valores crus dos parâmetros.
        nivel: Nível de tesselagem desejado.
        token: A bandeira de cancelamento deste pedido.
        sequencia: Número crescente, usado para descartar respostas atrasadas.
    """

    produto: Produto
    valores: dict[str, Any]
    nivel: NivelTesselagem = NivelTesselagem.PREVIEW
    token: TokenDeCancelamento = field(default_factory=TokenDeCancelamento)
    sequencia: int = 0


@dataclass(slots=True)
class Falha:
    """O que o worker emite quando um pedido não vinga.

    Attributes:
        mensagem: Resumo de uma linha, para a barra de status.
        traceback_completo: Traceback formatado, para o painel de erro.
        erros_por_chave: Erros de validação indexados pela chave do parâmetro.
        sequencia: A sequência do pedido que falhou.
    """

    mensagem: str
    traceback_completo: str = ""
    erros_por_chave: dict[str, list[str]] = field(default_factory=dict)
    sequencia: int = 0


class GeradorEmThread(QObject):
    """Executa pedidos de geração numa `QThread` própria.

    Signals:
        pronto: Emitido com o `ResultadoGeracao` de um pedido bem-sucedido.
        falhou: Emitido com uma `Falha`.
        cancelado: Emitido com a sequência do pedido abortado.
        comecou: Emitido com a sequência do pedido que entrou em execução.
    """

    pronto = Signal(object)
    falhou = Signal(object)
    cancelado = Signal(int)
    comecou = Signal(int)

    _agendar_interno = Signal(object)

    def __init__(
        self,
        cache_em_memoria: CacheEmMemoria | None = None,
        cache_em_disco: CacheEmDisco | None = None,
        pai: QObject | None = None,
    ) -> None:
        """Cria o worker e sobe a thread.

        Args:
            cache_em_memoria: Cache de gerações completas. Um novo é criado se
                não for fornecido.
            cache_em_disco: Cache de malhas de preview, ou `None` para não
                persistir nada — o que é o padrão nos testes.
            pai: Objeto pai do Qt.
        """
        super().__init__(pai)
        self.cache = cache_em_memoria if cache_em_memoria is not None else CacheEmMemoria()
        self.cache_em_disco = cache_em_disco

        self._pedido_atual: Pedido | None = None
        self._sequencia = 0

        self._executor = _Executor(self)
        self._thread = QThread()
        self._executor.moveToThread(self._thread)
        self._agendar_interno.connect(self._executor.executar)
        self._thread.start()

    # --- ciclo de vida ---------------------------------------------------

    def encerrar(self, espera_em_ms: int = 5000) -> None:
        """Cancela o pedido em curso e derruba a thread.

        Args:
            espera_em_ms: Quanto esperar pela thread antes de desistir.
        """
        self.cancelar_pendente()
        self._thread.quit()
        if not self._thread.wait(espera_em_ms):
            _log.warning("a thread de geração não encerrou no tempo esperado")

    # --- agendamento -----------------------------------------------------

    def cancelar_pendente(self) -> None:
        """Cancela o pedido em curso, se houver."""
        if self._pedido_atual is not None:
            self._pedido_atual.token.cancelar()

    def agendar(
        self,
        produto: Produto,
        valores: dict[str, Any],
        nivel: NivelTesselagem = NivelTesselagem.PREVIEW,
    ) -> Pedido:
        """Cancela o pedido anterior e enfileira um novo.

        Args:
            produto: O manifesto a gerar.
            valores: Valores crus dos parâmetros.
            nivel: Nível de tesselagem desejado.

        Returns:
            O pedido criado, cuja `sequencia` identifica as respostas.
        """
        self.cancelar_pendente()
        self._sequencia += 1
        pedido = Pedido(
            produto=produto, valores=dict(valores), nivel=nivel, sequencia=self._sequencia
        )
        self._pedido_atual = pedido
        self._agendar_interno.emit(pedido)
        return pedido

    @property
    def sequencia_atual(self) -> int:
        """Sequência do último pedido agendado."""
        return self._sequencia

    # --- resultado -------------------------------------------------------

    def _e_o_pedido_corrente(self, pedido: Pedido) -> bool:
        """Diz se a resposta ainda interessa ou se já foi superada."""
        return pedido.sequencia == self._sequencia


class _Executor(QObject):
    """O lado que roda dentro da thread. Não é usado diretamente."""

    def __init__(self, dono: GeradorEmThread) -> None:
        """Guarda a referência ao dono, para acessar caches e sinais."""
        super().__init__()
        self._dono = dono

    def executar(self, pedido: Pedido) -> None:
        """Roda o pipeline de um pedido, verificando o token entre as etapas.

        Args:
            pedido: O pedido a executar.
        """
        dono = self._dono
        try:
            resultado = self._pipeline(pedido)
        except Cancelado:
            _log.debug("pedido %d cancelado", pedido.sequencia)
            dono.cancelado.emit(pedido.sequencia)
            return
        except ErroDeValidacao as erro:
            dono.falhou.emit(
                Falha(
                    mensagem=str(erro),
                    erros_por_chave=getattr(erro, "erros_por_chave", {}),
                    sequencia=pedido.sequencia,
                )
            )
            return
        except Exception as erro:  # noqa: BLE001 -- falha do produto ou do núcleo
            _log.warning("pedido %d falhou: %s", pedido.sequencia, erro)
            dono.falhou.emit(
                Falha(
                    mensagem=str(erro),
                    traceback_completo="".join(
                        traceback.format_exception(type(erro), erro, erro.__traceback__)
                    ),
                    sequencia=pedido.sequencia,
                )
            )
            return

        if not dono._e_o_pedido_corrente(pedido):
            _log.debug("pedido %d concluiu mas já foi superado", pedido.sequencia)
            dono.cancelado.emit(pedido.sequencia)
            return

        dono.pronto.emit(resultado)

    def _pipeline(self, pedido: Pedido) -> ResultadoGeracao:
        """Validar, consultar cache, gerar, normalizar, orientar, tesselar."""
        dono = self._dono
        dono.comecou.emit(pedido.sequencia)
        pedido.token.conferir()

        validacao = validar(pedido.produto, pedido.valores)
        if not validacao.valido:
            raise ErroDeValidacao("; ".join(validacao.mensagens()), validacao.erros)

        completa = chave(pedido.produto, validacao.valores, pedido.nivel)

        em_memoria = dono.cache.obter(completa)
        if em_memoria is not None:
            _log.debug("acerto no cache em memória para %s", completa)
            return em_memoria

        if dono.cache_em_disco is not None and pedido.nivel is NivelTesselagem.PREVIEW:
            payload = dono.cache_em_disco.obter(completa)
            if payload is not None:
                _log.debug("acerto no cache de disco para %s", completa)
                recuperada = payload.como_geracao()
                dono.cache.guardar(completa, recuperada)
                return recuperada

        geracao = executar_pipeline(
            pedido.produto,
            validacao.valores,
            pedido.nivel,
            conferir=pedido.token.conferir,
        )

        dono.cache.guardar(completa, geracao)
        if dono.cache_em_disco is not None:
            dono.cache_em_disco.guardar(completa, geracao)

        return geracao
