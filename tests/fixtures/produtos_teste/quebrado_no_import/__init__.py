"""Produto de teste que falha ao ser importado, de propósito."""

from __future__ import annotations

MOTIVO = "falha proposital para o teste de descoberta"

raise RuntimeError(MOTIVO)
