"""Integração com a Meta Marketing (Graph) API."""

import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Iterable, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Ad, Campaign, Client, MetricDaily


logger = logging.getLogger("zeplin.meta")


class MetaAdsAPIError(RuntimeError):
    """Erro retornado pela Meta Graph API."""


class MetaAdsService:
    """Consulta e sincroniza dados do Meta Ads com o banco local."""

    API_VERSION = "v25.0"
    BASE_URL = "https://graph.facebook.com"
    INSIGHT_FIELDS = (
        "date_start,date_stop,spend,impressions,reach,clicks,inline_link_clicks,"
        "actions,action_values,cost_per_action_type,account_id,campaign_id,ad_id"
    )

    def __init__(self, timeout: int = 30, session: Optional[requests.Session] = None) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        self.meta_app_id = os.getenv("META_APP_ID")
        self.meta_app_secret = os.getenv("META_APP_SECRET")

    def validate_access_token(self, access_token: str) -> bool:
        """Verifica o token salvo antes de consultar contas ou métricas Meta."""
        if not access_token or access_token == "MOCK_TOKEN":
            raise MetaAdsAPIError("META_ACCESS_TOKEN não está configurado.")
        try:
            if self.meta_app_id and self.meta_app_secret:
                response = self.session.get(
                    f"{self.BASE_URL}/{self.API_VERSION}/debug_token",
                    params={
                        "input_token": access_token,
                        "access_token": f"{self.meta_app_id}|{self.meta_app_secret}",
                    },
                    timeout=self.timeout,
                )
                if not response.ok:
                    self._raise_response_error(response)
                payload = response.json().get("data", {})
                if payload.get("is_valid"):
                    return True
                detail = payload.get("error", {}).get("message", "Token inválido ou sem permissão.")
                raise MetaAdsAPIError(f"Meta Graph API: {detail}")
            response = self.session.get(f"{self.BASE_URL}/{self.API_VERSION}/me", params={"access_token": access_token}, timeout=self.timeout)
            if not response.ok:
                self._raise_response_error(response)
            return True
        except requests.RequestException as exc:
            raise MetaAdsAPIError("Não foi possível conectar à Meta Graph API.") from exc

    def fetch_account_insights(
        self,
        account_id: str,
        access_token: str,
        start_date: date | str,
        end_date: date | str,
        result_preferences: Optional[dict[str, str]] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca métricas diárias nos níveis de conta, campanha e anúncio.

        O retorno é organizado por nível e normalizado para os campos usados pela
        aplicação. ``clicks`` representa ``inline_link_clicks`` quando disponível.
        """
        account_id = self._normalize_account_id(account_id)
        time_range = json.dumps({"since": str(start_date), "until": str(end_date)})

        insights = {
            level: [self._normalize_insight(
                row,
                level,
                (result_preferences or {}).get(row.get("campaign_id")),
            ) for row in self._paginate(
                f"{self.BASE_URL}/{self.API_VERSION}/{account_id}/insights",
                {
                    "access_token": access_token,
                    "fields": self.INSIGHT_FIELDS,
                    "level": level,
                    "time_increment": 1,
                    "time_range": time_range,
                    "limit": 500,
                },
            )]
            for level in ("account", "campaign", "ad")
        }
        # Alcance do período: sem time_increment para evitar a soma de alcances diários.
        for level in ("account", "campaign"):
            insights[f"period_{level}"] = [self._normalize_insight(
                row,
                level,
                (result_preferences or {}).get(row.get("campaign_id")),
            ) for row in self._paginate(
                f"{self.BASE_URL}/{self.API_VERSION}/{account_id}/insights",
                {
                    "access_token": access_token,
                    "fields": self.INSIGHT_FIELDS,
                    "level": level,
                    "time_range": time_range,
                    "limit": 500,
                },
            )]
        return insights

    def fetch_campaign_insights(
        self,
        campaign_id: str,
        access_token: str,
        start_date: date | str,
        end_date: date | str,
        result_preference: Optional[str] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca insights diários de uma única campanha, inclusive por anúncio."""
        time_range = json.dumps({"since": str(start_date), "until": str(end_date)})
        result: dict[str, list[dict[str, Any]]] = {"account": [], "campaign": [], "ad": []}
        for level in ("campaign", "ad"):
            rows = self._paginate(
                f"{self.BASE_URL}/{self.API_VERSION}/{campaign_id}/insights",
                {
                    "access_token": access_token,
                    "fields": self.INSIGHT_FIELDS,
                    "level": level,
                    "time_increment": 1,
                    "time_range": time_range,
                    "limit": 500,
                },
            )
            for row in rows:
                # O endpoint /{campaign_id}/insights pode omitir campaign_id no nível campanha.
                row.setdefault("campaign_id", campaign_id)
                result[level].append(self._normalize_insight(row, level, result_preference))
        result["period_campaign"] = []
        for row in self._paginate(
            f"{self.BASE_URL}/{self.API_VERSION}/{campaign_id}/insights",
            {
                "access_token": access_token,
                "fields": self.INSIGHT_FIELDS,
                "level": "campaign",
                "time_range": time_range,
                "limit": 500,
            },
        ):
            row.setdefault("campaign_id", campaign_id)
            result["period_campaign"].append(self._normalize_insight(row, "campaign", result_preference))
        return result

    def sync_campaigns_and_ads(
        self,
        client_id: int,
        db_session: Session,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        campaign_meta_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Sincroniza campanhas, anúncios ativos e métricas dos últimos 30 dias.

        A sessão é confirmada apenas ao fim. Em caso de falha, as alterações locais
        são desfeitas e a exceção é propagada para a camada FastAPI tratá-la.
        """
        client = db_session.get(Client, client_id)
        if not client:
            raise ValueError(f"Cliente {client_id} não encontrado.")
        if not client.meta_account_id or not client.meta_access_token:
            raise ValueError("O cliente não possui credenciais Meta configuradas.")

        try:
            campaigns = self._paginate(
                f"{self.BASE_URL}/{self.API_VERSION}/{self._normalize_account_id(client.meta_account_id)}/campaigns",
                {
                    "access_token": client.meta_access_token,
                    "fields": "id,name,objective,status,effective_status",
                    "limit": 500,
                },
            )

            synced_campaigns: dict[str, Campaign] = {}
            for payload in campaigns:
                campaign = self._upsert_campaign(client.id, payload, db_session)
                synced_campaigns[payload["id"]] = campaign
            if campaign_meta_id:
                if campaign_meta_id not in synced_campaigns:
                    raise ValueError("A campanha selecionada não pertence à conta Meta deste cliente.")
                synced_campaigns = {campaign_meta_id: synced_campaigns[campaign_meta_id]}
            db_session.flush()

            result_preferences = {
                meta_campaign_id: self._campaign_result_preference(meta_campaign_id, client.meta_access_token)
                for meta_campaign_id in synced_campaigns
            }

            ads_synced = 0
            for meta_campaign_id, campaign in synced_campaigns.items():
                ads = self._paginate(
                    f"{self.BASE_URL}/{self.API_VERSION}/{meta_campaign_id}/ads",
                    {
                        "access_token": client.meta_access_token,
                        "fields": "id,name,status,effective_status,creative{thumbnail_url,body}",
                        "effective_status": json.dumps(["ACTIVE"]),
                        "limit": 500,
                    },
                )
                for payload in ads:
                    self._upsert_ad(campaign, payload, db_session)
                    ads_synced += 1
            db_session.flush()

            end_date = end_date or date.today()
            start_date = start_date or (end_date - timedelta(days=29))
            insights = (
                self.fetch_campaign_insights(
                    campaign_meta_id,
                    client.meta_access_token,
                    start_date,
                    end_date,
                    result_preferences.get(campaign_meta_id),
                )
                if campaign_meta_id
                else self.fetch_account_insights(
                    client.meta_account_id,
                    client.meta_access_token,
                    start_date,
                    end_date,
                    result_preferences,
                )
            )
            metrics_synced = self._sync_metrics(client.id, insights, db_session)
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

        return {
            "campaigns": len(synced_campaigns),
            "ads": ads_synced,
            "metrics_synced": metrics_synced,
            "metrics": self._summarize_account_insights(
                insights["period_campaign"] if campaign_meta_id else insights["period_account"]
            ),
            "campaign_metrics": self._campaign_metrics(insights["period_campaign"], synced_campaigns),
        }

    def _campaign_result_preference(self, campaign_id: str, access_token: str) -> Optional[str]:
        """Lê o objetivo de otimização do conjunto para identificar o resultado oficial."""
        adsets = self._paginate(
            f"{self.BASE_URL}/{self.API_VERSION}/{campaign_id}/adsets",
            {"access_token": access_token, "fields": "optimization_goal", "limit": 100},
        )
        return next((item.get("optimization_goal") for item in adsets if item.get("optimization_goal")), None)

    def _paginate(self, url: str, params: dict[str, Any]) -> Iterable[dict[str, Any]]:
        """Itera por todas as páginas de uma resposta Graph API."""
        next_url: Optional[str] = url
        next_params: Optional[dict[str, Any]] = params
        while next_url:
            try:
                response = self.session.get(next_url, params=next_params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise MetaAdsAPIError("Não foi possível conectar à Meta Graph API.") from exc
            if not response.ok:
                self._raise_response_error(response)
            payload = response.json()
            if not payload.get("data"):
                logger.warning(
                    "[DEBUG] Meta API URL: %s | response: %s",
                    self._redact_access_token(response.url),
                    self._redact_access_token(json.dumps(payload, ensure_ascii=False)),
                )
            yield from payload.get("data", [])
            next_url = payload.get("paging", {}).get("next")
            next_params = None  # A URL de paginação já inclui os parâmetros necessários.

    @staticmethod
    def _raise_response_error(response: requests.Response) -> None:
        try:
            error = response.json().get("error", {})
            detail = error.get("message", response.text)
            code = error.get("code")
            subcode = error.get("error_subcode")
            suffix = f" (code {code}{f', subcode {subcode}' if subcode else ''})" if code else ""
        except ValueError:
            detail, suffix = response.text, ""
        raise MetaAdsAPIError(f"Meta Graph API ({response.status_code}){suffix}: {detail}")

    @staticmethod
    def _redact_access_token(value: str) -> str:
        """Remove tokens de URLs e JSONs antes de qualquer registro de depuração."""
        return re.sub(r"(access_token=)[^&\s\"\\]+", r"\1<redacted>", value)

    @staticmethod
    def _normalize_account_id(account_id: str) -> str:
        return account_id if account_id.startswith("act_") else f"act_{account_id}"

    @staticmethod
    def _summarize_account_insights(rows: list[dict[str, Any]]) -> dict[str, float | int]:
        spend = round(sum(float(row.get("spend", 0) or 0) for row in rows), 2)
        impressions = sum(int(row.get("impressions", 0) or 0) for row in rows)
        reach = sum(int(row.get("reach", 0) or 0) for row in rows)
        clicks = sum(int(row.get("clicks", 0) or 0) for row in rows)
        conversions = sum(float(row.get("conversions", 0) or 0) for row in rows)
        message_conversations = sum(float(row.get("message_conversations", 0) or 0) for row in rows)
        conversion_value = sum(float(row.get("conversion_value", 0) or 0) for row in rows)
        return {
            "spend": spend,
            "impressions": impressions,
            "reach": reach,
            "clicks": clicks,
            "conversions": conversions,
            "message_conversations": message_conversations,
            "conversion_value": conversion_value,
            "cost_per_result": round(spend / conversions, 2) if conversions else 0.0,
            "cost_per_message": round(spend / conversions, 2) if conversions else 0.0,
            "cpa": round(spend / conversions, 2) if conversions else 0.0,
            "roas": round(conversion_value / spend, 2) if spend else 0.0,
            "ctr": round((clicks / impressions) * 100, 2) if impressions else 0.0,
        }

    @classmethod
    def _campaign_metrics(cls, rows: list[dict[str, Any]], campaigns: dict[str, Campaign]) -> list[dict[str, Any]]:
        """Agrupa os insights diários para a tabela comparativa de campanhas."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            campaign_id = row.get("meta_campaign_id")
            if campaign_id:
                grouped.setdefault(campaign_id, []).append(row)
        result = []
        for campaign_id, campaign_rows in grouped.items():
            campaign = campaigns.get(campaign_id)
            result.append({
                "id": campaign.id if campaign else None,
                "meta_campaign_id": campaign_id,
                "name": campaign.name if campaign else campaign_id,
                **cls._summarize_account_insights(campaign_rows),
            })
        return sorted(result, key=lambda item: float(item["spend"]), reverse=True)

    @staticmethod
    def _action_total(actions: list[dict[str, Any]], suffix: str) -> float:
        """Soma ações Meta de um tipo, inclusive variações com prefixo técnico."""
        return sum(
            float(action.get("value", 0) or 0)
            for action in actions
            if action.get("action_type", "").lower().endswith(suffix)
        )

    @staticmethod
    def _action_value(actions: list[dict[str, Any]], suffix: str) -> float:
        """Obtém um custo por tipo de ação retornado pela Meta."""
        for action in actions:
            if action.get("action_type", "").lower().endswith(suffix):
                return float(action.get("value", 0) or 0)
        return 0.0

    @classmethod
    def _result_total(cls, actions: list[dict[str, Any]]) -> float:
        """Retorna o resultado principal, sem somar cliques/engajamentos genéricos.

        Em campanhas de mensagens a conversa iniciada é o resultado. Quando ela não
        existe, mantém eventos de conversão diretos e, por último, engajamento de
        post para campanhas que não são de mensagens.
        """
        messages = cls._action_total(actions, "messaging_conversation_started_7d")
        if messages:
            return messages
        direct_conversions = cls._action_total(actions, "purchase") + cls._action_total(actions, "lead")
        if direct_conversions:
            return direct_conversions
        return cls._action_total(actions, "inline_post_engagement")

    @classmethod
    def _primary_result(cls, actions: list[dict[str, Any]], inline_link_clicks: int, preference: Optional[str]) -> tuple[float, str]:
        """Seleciona o resultado pela otimização oficial do conjunto de anúncios."""
        normalized_preference = (preference or "").upper()
        if normalized_preference in {"LINK_CLICKS", "LANDING_PAGE_VIEWS"}:
            return float(inline_link_clicks or cls._action_total(actions, "link_click")), "link_click"
        if normalized_preference in {"CONVERSATIONS", "MESSAGING_CONVERSATIONS"}:
            return cls._action_total(actions, "messaging_conversation_started_7d"), "messaging_conversation_started_7d"
        if normalized_preference in {"LEAD_GENERATION", "LEADS"}:
            return cls._action_total(actions, "lead"), "lead"
        if normalized_preference in {"OFFSITE_CONVERSIONS", "VALUE"}:
            return cls._action_total(actions, "purchase"), "purchase"
        if normalized_preference in {"POST_ENGAGEMENT", "PAGE_ENGAGEMENT"}:
            return cls._action_total(actions, "post_engagement"), "post_engagement"
        # Sem objetivo disponível, prioriza o indicador padronizado de cliques no link.
        if inline_link_clicks:
            return float(inline_link_clicks), "link_click"
        messages = cls._action_total(actions, "messaging_conversation_started_7d")
        if messages:
            return messages, "messaging_conversation_started_7d"
        return cls._result_total(actions), "result"

    def _normalize_insight(self, row: dict[str, Any], level: str, result_preference: Optional[str] = None) -> dict[str, Any]:
        actions = row.get("actions", [])
        action_values = row.get("action_values", [])
        costs_per_action = row.get("cost_per_action_type", [])
        inline_link_clicks = row.get("inline_link_clicks", row.get("clicks", 0))
        message_conversations = self._action_total(actions, "messaging_conversation_started_7d")
        spend = round(float(row.get("spend", 0) or 0), 2)
        meta_cost_per_message = self._action_value(costs_per_action, "messaging_conversation_started_7d")
        # Em algumas contas a Meta retorna apenas cost_per_action_type. Nesse caso,
        # recuperamos a quantidade de conversas pelo valor usado/custo informado.
        if not message_conversations and meta_cost_per_message and spend:
            message_conversations = spend / meta_cost_per_message
        conversions, result_type = self._primary_result(actions, int(inline_link_clicks or 0), result_preference)
        return {
            "level": level,
            "date": row["date_start"],
            "meta_campaign_id": row.get("campaign_id"),
            "meta_ad_id": row.get("ad_id"),
            "spend": spend,
            "impressions": int(row.get("impressions", 0) or 0),
            "reach": int(row.get("reach", 0) or 0),
            "clicks": int(inline_link_clicks or 0),
            "inline_link_clicks": int(inline_link_clicks or 0),
            "conversions": conversions,
            "message_conversations": message_conversations,
            "result_type": result_type,
            "cost_per_result": round(spend / conversions, 2) if conversions else 0.0,
            "cost_per_message": round(spend / conversions, 2) if conversions else 0.0,
            "conversion_value": self._action_total(action_values, "purchase") + self._action_total(action_values, "lead"),
        }

    @staticmethod
    def _upsert_campaign(client_id: int, payload: dict[str, Any], db: Session) -> Campaign:
        campaign = db.scalar(select(Campaign).where(Campaign.meta_campaign_id == payload["id"]))
        if not campaign:
            campaign = Campaign(client_id=client_id, meta_campaign_id=payload["id"], name=payload["name"])
            db.add(campaign)
        campaign.name = payload["name"]
        campaign.objective = payload.get("objective")
        campaign.status = payload.get("effective_status", payload.get("status", "ACTIVE"))
        return campaign

    @staticmethod
    def _upsert_ad(campaign: Campaign, payload: dict[str, Any], db: Session) -> Ad:
        ad = db.scalar(select(Ad).where(Ad.meta_ad_id == payload["id"]))
        if not ad:
            ad = Ad(campaign=campaign, meta_ad_id=payload["id"], name=payload["name"])
            db.add(ad)
        creative = payload.get("creative") or {}
        ad.campaign = campaign
        ad.name = payload["name"]
        ad.thumbnail_url = creative.get("thumbnail_url")
        ad.copy_text = creative.get("body")
        return ad

    @staticmethod
    def _sync_metrics(client_id: int, insights: dict[str, list[dict[str, Any]]], db: Session) -> int:
        campaign_ids = {row["meta_campaign_id"] for row in insights["campaign"] + insights["ad"] if row["meta_campaign_id"]}
        ad_ids = {row["meta_ad_id"] for row in insights["ad"] if row["meta_ad_id"]}
        campaigns = {
            item.meta_campaign_id: item
            for item in db.scalars(select(Campaign).where(Campaign.meta_campaign_id.in_(campaign_ids))).all()
        } if campaign_ids else {}
        ads = {
            item.meta_ad_id: item
            for item in db.scalars(select(Ad).where(Ad.meta_ad_id.in_(ad_ids))).all()
        } if ad_ids else {}

        count = 0
        for level in ("account", "campaign", "ad"):
            rows = insights.get(level, [])
            for row in rows:
                campaign = campaigns.get(row["meta_campaign_id"])
                ad = ads.get(row["meta_ad_id"])
                conditions = [MetricDaily.client_id == client_id, MetricDaily.date == date.fromisoformat(row["date"])]
                conditions.append(MetricDaily.campaign_id.is_(None) if not campaign else MetricDaily.campaign_id == campaign.id)
                conditions.append(MetricDaily.ad_id.is_(None) if not ad else MetricDaily.ad_id == ad.id)
                metric = db.scalar(select(MetricDaily).where(*conditions))
                if not metric:
                    metric = MetricDaily(client_id=client_id, date=date.fromisoformat(row["date"]), campaign=campaign, ad=ad)
                    db.add(metric)
                metric.spend = row["spend"]
                metric.impressions = row["impressions"]
                metric.clicks = row["clicks"]
                metric.conversions = row["conversions"]
                metric.conversion_value = row["conversion_value"]
                count += 1
        return count
