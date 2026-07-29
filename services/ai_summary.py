"""Geração de resumos executivos com a API da OpenAI."""

import json
import os
from typing import Any, Optional

from openai import OpenAI


def _fallback_summary(metrics_summary: dict[str, Any], client_name: str, campaign_name: Optional[str] = None) -> str:
    """Resumo local usado quando a chave OpenAI não está disponível no ambiente."""
    spend = float(metrics_summary.get("spend", 0) or 0)
    results = float(metrics_summary.get("conversions", 0) or 0)
    cost = float(metrics_summary.get("cost_per_result", metrics_summary.get("cpa", 0)) or 0)
    ctr = float(metrics_summary.get("ctr", 0) or 0)
    scope = f"na campanha {campaign_name}" if campaign_name else "na visão geral da conta"
    return (
        f"No período analisado, {client_name} registrou {results:,.0f} resultados {scope}, com investimento de R$ {spend:,.2f}. "
        f"O custo por resultado foi de R$ {cost:,.2f} e o CTR ficou em {ctr:,.2f}%.\n\n"
        "O próximo diagnóstico deve priorizar a comparação entre campanhas, criativos e públicos para identificar os elementos que sustentam o volume de resultados e os pontos de menor eficiência.\n\n"
        "A ação recomendada é manter o acompanhamento periódico do custo por resultado e do alcance, redistribuindo investimento de forma gradual para os segmentos com melhor desempenho."
    )


def generate_executive_summary(
    metrics_summary: dict[str, Any],
    client_name: str,
    campaign_name: Optional[str] = None,
    campaign_objective: Optional[str] = None,
) -> str:
    """Retorna uma análise executiva concisa em três parágrafos.

    A chave é obtida da variável de ambiente ``OPENAI_API_KEY``. O modelo pode ser
    alterado por ``OPENAI_MODEL`` sem necessidade de mudar o código.
    """
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return _fallback_summary(metrics_summary, client_name, campaign_name)

    campaign_context = (
        f"A análise deve ser exclusivamente da campanha selecionada: {campaign_name}. "
        f"Objetivo cadastrado: {campaign_objective or 'não informado'}. Compare os indicadores "
        "com a finalidade desse objetivo e não tire conclusões sobre toda a conta."
        if campaign_name
        else "A análise deve cobrir a visão geral da conta, considerando o conjunto de campanhas do período."
    )
    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        instructions=(
            "Você é o gestor de tráfego da Zeplin Lab Digital, especialista em Meta Ads, "
            "engajamento, campanhas de mensagens WhatsApp/Direct e geração de conversas. "
            "Escreva em português do Brasil, com tom executivo, claro e baseado exclusivamente "
            "nos dados recebidos."
        ),
        input=(
            f"Analise os resultados do cliente {client_name}.\n"
            f"Métricas do período: {json.dumps(metrics_summary, ensure_ascii=False)}\n\n"
            f"Escopo: {campaign_context}\n\n"
            "Use explicitamente Investimento (spend), Conversões/Resultados (conversions), "
            "CPA (cpa) e CTR (ctr). Para contas de mensagens, trate conversas iniciadas e "
            "cliques no link como indicadores de interesse, sem afirmar que são vendas. "
            "Retorne exatamente três parágrafos em texto corrido: o primeiro destaca os "
            "resultados de engajamento e mensagens; o segundo identifica eficiência, gargalos "
            "e riscos; o terceiro recomenda uma próxima ação concreta. Não use títulos, listas, "
            "markdown nem invente métricas."
        ),
    )
    summary = (response.output_text or "").strip()
    if not summary:
        raise RuntimeError("A OpenAI não retornou conteúdo para o resumo executivo.")
    return summary
