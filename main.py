"""Servidor FastAPI da plataforma Zeplin Lab Digital."""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import dotenv_values, load_dotenv
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Campaign, Client, MetricDaily, Report
from services.ai_summary import generate_executive_summary
from services.meta_api import MetaAdsAPIError, MetaAdsService
from services.pdf_generator import generate_pdf_report


ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"
REPORTS_DIR = ROOT_DIR / "storage" / "relatorios"
CREATIVES_DIR = Path(__file__).resolve().parent / "uploaded_creatives"
logger = logging.getLogger("zeplin.meta")

app = FastAPI(title="Zeplin Lab Digital API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def create_tables() -> None:
    _load_environment()
    Base.metadata.create_all(bind=engine)
    _ensure_report_columns()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CREATIVES_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_report_columns() -> None:
    """Aplica colunas aditivas ao SQLite existente para reedição de relatórios."""
    required_columns = {
        "campanha_id": "INTEGER",
        "campanha_nome": "VARCHAR(255)",
        "plano_acao": "TEXT",
        "criativos_json": "TEXT",
        "campanhas_json": "TEXT",
        "metricas_json": "TEXT",
    }
    existing = {column["name"] for column in inspect(engine).get_columns("relatorios")}
    with engine.begin() as connection:
        for name, definition in required_columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE relatorios ADD COLUMN {name} {definition}"))


def _env_meta_token() -> Optional[str]:
    """Obtém o token global, relendo o .env se o processo não o tiver em memória."""
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        token = dotenv_values(ENV_FILE.resolve()).get("META_ACCESS_TOKEN") or _read_env_value("META_ACCESS_TOKEN")
    if not token:
        return None
    normalized = token.strip().strip('"').strip("'")
    if normalized:
        os.environ["META_ACCESS_TOKEN"] = normalized
        return normalized
    return None


def _load_environment() -> None:
    """Carrega e normaliza as credenciais, inclusive em .env com formatação incomum."""
    load_dotenv(dotenv_path=ENV_FILE.resolve(), override=True)
    parsed_values = dotenv_values(ENV_FILE.resolve())
    for key in ("META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"):
        value = os.getenv(key) or parsed_values.get(key) or _read_env_value(key)
        if value:
            os.environ[key] = value.strip().strip('"').strip("'")

    token = _env_meta_token()
    if token:
        logger.warning("META_ACCESS_TOKEN carregado com sucesso: %s...", token[:10])
    else:
        logger.warning("META_ACCESS_TOKEN não foi encontrado no arquivo .env.")


def _read_env_value(key: str) -> Optional[str]:
    """Fallback para ler uma chave diretamente, removendo BOM e espaços laterais."""
    try:
        for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip()
    except OSError:
        return None
    return None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    meta_account_id: str = Field(min_length=1, max_length=255)
    meta_access_token: Optional[str] = None


class ClientResponse(BaseModel):
    id: int
    name: str
    meta_account_id: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@app.post("/api/v1/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> Client:
    existing = db.scalar(select(Client).where(Client.meta_account_id == payload.meta_account_id))
    if existing:
        raise HTTPException(status_code=409, detail="Já existe um cliente com esta conta Meta.")
    client_data = payload.model_dump()
    client_data["meta_access_token"] = payload.meta_access_token or _env_meta_token()
    client = Client(**client_data)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.get("/api/v1/clients", response_model=list[ClientResponse])
def list_clients(db: Session = Depends(get_db)) -> list[Client]:
    return list(db.scalars(select(Client).order_by(Client.created_at.desc())).all())


@app.get("/api/v1/clients/{client_id}/campaigns")
def list_client_campaigns(client_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Lista as campanhas já sincronizadas para alimentar o filtro do dashboard."""
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    campaigns = db.scalars(
        select(Campaign)
        .where(Campaign.client_id == client_id)
        .order_by(Campaign.name.asc())
    ).all()
    return [
        {
            "id": campaign.id,
            "meta_campaign_id": campaign.meta_campaign_id,
            "name": campaign.name,
            "objective": campaign.objective,
            "status": campaign.status,
        }
        for campaign in campaigns
    ]


@app.post("/api/v1/clients/{client_id}/sync")
def sync_client(
    client_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    campaign_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    # Recarrega explicitamente a credencial global antes de cada chamada real.
    _load_environment()
    default_token = _env_meta_token()
    if not default_token:
        raise HTTPException(status_code=503, detail="META_ACCESS_TOKEN não está configurado no arquivo .env.")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior ou igual à data final.")
    campaign = None
    if campaign_id is not None:
        campaign = db.get(Campaign, campaign_id)
        if not campaign or campaign.client_id != client.id:
            raise HTTPException(status_code=404, detail="Campanha não encontrada para este cliente.")
    if client.meta_access_token != default_token:
        client.meta_access_token = default_token
        db.commit()
    try:
        service = MetaAdsService()
        service.validate_access_token(client.meta_access_token)
        result = service.sync_campaigns_and_ads(
            client_id,
            db,
            start_date=start_date,
            end_date=end_date,
            campaign_meta_id=campaign.meta_campaign_id if campaign else None,
        )
    except (MetaAdsAPIError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result["executive_summary"] = _generate_ai_summary(
        result["metrics"],
        client.name,
        campaign_name=campaign.name if campaign else None,
        campaign_objective=campaign.objective if campaign else None,
    )
    if campaign:
        result["campaign"] = {"id": campaign.id, "name": campaign.name, "objective": campaign.objective}
    return {"message": "Sincronização concluída.", **result}


@app.post("/api/v1/reports/generate", status_code=status.HTTP_201_CREATED)
async def generate_report(
    client_id: int = Form(...),
    campaign_id: Optional[int] = Form(None),
    start_date: date = Form(...),
    end_date: date = Form(...),
    executive_summary: Optional[str] = Form(None),
    action_plan: Optional[str] = Form(None),
    metrics_snapshot: str = Form(""),
    creatives: str = Form("[]"),
    creative_images: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior ou igual à data final.")
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    campaign = None
    if campaign_id is not None:
        campaign = db.get(Campaign, campaign_id)
        if not campaign or campaign.client_id != client.id:
            raise HTTPException(status_code=404, detail="Campanha não encontrada para este cliente.")

    try:
        report_creatives = await _store_creatives(creatives, creative_images)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not client.meta_access_token or client.meta_access_token == "MOCK_TOKEN":
        raise HTTPException(status_code=503, detail="Sincronize uma conta Meta com META_ACCESS_TOKEN válido antes de gerar o relatório.")
    try:
        metrics = _parse_metrics_snapshot(metrics_snapshot) if metrics_snapshot.strip() else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    period = (MetricDaily.date >= start_date, MetricDaily.date <= end_date)
    metrics_scope = (
        (MetricDaily.campaign_id == campaign.id, MetricDaily.ad_id.is_(None))
        if campaign
        else (MetricDaily.campaign_id.is_(None), MetricDaily.ad_id.is_(None))
    )
    if metrics is None:
        totals = db.execute(
            select(
                func.coalesce(func.sum(MetricDaily.spend), 0),
                func.coalesce(func.sum(MetricDaily.impressions), 0),
                func.coalesce(func.sum(MetricDaily.clicks), 0),
                func.coalesce(func.sum(MetricDaily.conversions), 0),
                func.coalesce(func.sum(MetricDaily.conversion_value), 0),
            ).where(MetricDaily.client_id == client.id, *period, *metrics_scope)
        ).one()
        metrics = _metrics_dict(*totals)

    campaign_rows = db.execute(
        select(
            Campaign.id,
            Campaign.name,
            func.coalesce(func.sum(MetricDaily.spend), 0),
            func.coalesce(func.sum(MetricDaily.impressions), 0),
            func.coalesce(func.sum(MetricDaily.clicks), 0),
            func.coalesce(func.sum(MetricDaily.conversions), 0),
            func.coalesce(func.sum(MetricDaily.conversion_value), 0),
        )
        .join(MetricDaily, MetricDaily.campaign_id == Campaign.id)
        .where(
            Campaign.client_id == client.id,
            *period,
            MetricDaily.ad_id.is_(None),
            *([Campaign.id == campaign.id] if campaign else []),
        )
        .group_by(Campaign.id, Campaign.name)
        .order_by(func.sum(MetricDaily.spend).desc())
    ).all()
    campaigns = [
        {"id": row[0], "name": row[1], **_metrics_dict(*row[2:])}
        for row in campaign_rows
    ]
    ai_summary = _generate_ai_summary(
        metrics,
        client.name,
        campaign_name=campaign.name if campaign else None,
        campaign_objective=campaign.objective if campaign else None,
    )
    final_summary = executive_summary.strip() if executive_summary and executive_summary.strip() else ai_summary
    final_action_plan = (action_plan or "").strip() or _default_action_plan()

    filename = f"report_{client.id}_{start_date}_{end_date}_{uuid4().hex}.pdf"
    pdf_path = REPORTS_DIR / filename
    report_data = {
        "client_name": client.name,
        "campaign_name": campaign.name if campaign else "Todas as campanhas (Visão Geral)",
        "start_date": start_date.strftime("%d/%m/%Y"),
        "end_date": end_date.strftime("%d/%m/%Y"),
        "metrics": metrics,
        "campaigns": campaigns,
        "executive_summary": final_summary,
        "action_plan": final_action_plan,
        "creatives": report_creatives,
    }
    try:
        generate_pdf_report(report_data, pdf_path)
        report = Report(
            client_id=client.id,
            campaign_id=campaign.id if campaign else None,
            campaign_name=campaign.name if campaign else "Todas as campanhas (Visão Geral)",
            start_date=start_date,
            end_date=end_date,
            spend=metrics["spend"],
            conversions=metrics["conversions"],
            cpa=metrics["cpa"],
            roas=metrics["roas"],
            executive_summary=final_summary,
            action_plan=final_action_plan,
            creatives_json=json.dumps(report_creatives, ensure_ascii=False),
            campaigns_json=json.dumps(campaigns, ensure_ascii=False),
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            status="completed",
            pdf_path=str(pdf_path),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Não foi possível gerar o PDF: {exc}") from exc

    return {
        "id": report.id,
        "status": report.status,
        "pdf_url": f"/api/v1/reports/{report.id}/pdf",
        "metrics": metrics,
        "campaigns": campaigns,
        "executive_summary": final_summary,
        "action_plan": final_action_plan,
        "creatives": report_creatives,
    }


@app.get("/api/v1/reports")
def list_reports(
    client_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Lista relatórios com filtros opcionais de cliente e período."""
    statement = select(Report, Client.name).join(Client, Report.client_id == Client.id)
    if client_id:
        statement = statement.where(Report.client_id == client_id)
    if start_date:
        statement = statement.where(Report.start_date >= start_date)
    if end_date:
        statement = statement.where(Report.end_date <= end_date)
    rows = db.execute(statement.order_by(Report.created_at.desc())).all()
    return [
        {
            "id": report.id,
            "client_id": report.client_id,
            "client_name": client_name,
            "start_date": report.start_date,
            "end_date": report.end_date,
            "spend": report.spend,
            "conversions": report.conversions,
            "cpa": report.cpa,
            "roas": report.roas,
            "campaign_id": report.campaign_id,
            "campaign_name": report.campaign_name or "Todas as campanhas (Visão Geral)",
            "status": report.status,
            "created_at": report.created_at,
            "pdf_url": f"/api/v1/reports/{report.id}/pdf",
        }
        for report, client_name in rows
    ]


@app.get("/api/v1/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Recupera o conteúdo salvo para reabrir um relatório no editor."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    campaign_metrics = _load_json_list(report.campaigns_json) or _report_campaign_metrics(db, report)
    return {
        "id": report.id,
        "client_id": report.client_id,
        "campaign_id": report.campaign_id,
        "campaign_name": report.campaign_name or "Todas as campanhas (Visão Geral)",
        "start_date": report.start_date,
        "end_date": report.end_date,
        "has_metrics_snapshot": bool(report.metrics_json),
        "metrics": _load_json_object(report.metrics_json) or _metrics_dict(report.spend, 0, 0, report.conversions, 0),
        "campaign_metrics": campaign_metrics,
        "executive_summary": report.executive_summary or "",
        "action_plan": report.action_plan or "",
        "creatives": _load_json_list(report.creatives_json),
    }


@app.get("/api/v1/reports/{report_id}/pdf")
def download_report_pdf(report_id: int, db: Session = Depends(get_db)) -> FileResponse:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    if not report.pdf_path or not Path(report.pdf_path).is_file():
        raise HTTPException(status_code=404, detail="Arquivo PDF não encontrado.")
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=Path(report.pdf_path).name)


@app.delete("/api/v1/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Exclui o registro do relatório e seu PDF, quando este estiver no armazenamento da aplicação."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    pdf_deleted = False
    if report.pdf_path:
        pdf_path = Path(report.pdf_path).resolve()
        try:
            pdf_path.relative_to(REPORTS_DIR.resolve())
        except ValueError:
            logger.warning("O PDF do relatório %s está fora do diretório de relatórios; arquivo preservado.", report_id)
        else:
            try:
                if pdf_path.is_file():
                    pdf_path.unlink()
                    pdf_deleted = True
            except OSError as exc:
                raise HTTPException(status_code=500, detail="Não foi possível remover o arquivo PDF do relatório.") from exc

    db.delete(report)
    db.commit()
    return {"id": report_id, "deleted": True, "pdf_deleted": pdf_deleted}


def _metrics_dict(spend: float, impressions: int, clicks: int, conversions: float, conversion_value: float) -> dict[str, float | int]:
    spend = float(spend or 0)
    impressions = int(impressions or 0)
    clicks = int(clicks or 0)
    conversions = float(conversions or 0)
    conversion_value = float(conversion_value or 0)
    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "conversion_value": conversion_value,
        "cpa": round(spend / conversions, 2) if conversions else 0.0,
        "roas": round(conversion_value / spend, 2) if spend else 0.0,
        "ctr": round((clicks / impressions) * 100, 2) if impressions else 0.0,
        "reach": 0,
        "message_conversations": conversions,
        "cost_per_result": round(spend / conversions, 2) if conversions else 0.0,
        "cost_per_message": round(spend / conversions, 2) if conversions else 0.0,
    }


def _parse_metrics_snapshot(raw_snapshot: str) -> dict[str, float | int]:
    """Normaliza o snapshot que alimenta os cards para o PDF usar exatamente o mesmo escopo."""
    try:
        payload = json.loads(raw_snapshot)
    except json.JSONDecodeError as exc:
        raise ValueError("O snapshot de métricas enviado é inválido.") from exc
    if not isinstance(payload, dict):
        raise ValueError("O snapshot de métricas deve ser um objeto.")

    def number(name: str, default: float = 0.0) -> float:
        try:
            return float(payload.get(name, default) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"A métrica {name} é inválida.") from exc

    spend = number("spend")
    impressions = int(number("impressions"))
    reach = int(number("reach"))
    clicks = int(number("clicks"))
    conversions = number("conversions")
    messages = number("message_conversations", conversions)
    conversion_value = number("conversion_value")
    cost_per_result = round(spend / conversions, 2) if conversions else 0.0
    cost_per_message = cost_per_result
    return {
        "spend": spend,
        "impressions": impressions,
        "reach": reach,
        "clicks": clicks,
        "conversions": conversions,
        "message_conversations": messages,
        "conversion_value": conversion_value,
        "cost_per_result": cost_per_result,
        "cost_per_message": cost_per_message,
        "cpa": cost_per_result,
        "roas": round(conversion_value / spend, 2) if spend else 0.0,
        "ctr": round((clicks / impressions) * 100, 2) if impressions else 0.0,
    }


def _load_json_object(raw_value: Optional[str]) -> Optional[dict[str, object]]:
    try:
        decoded = json.loads(raw_value or "")
        return decoded if isinstance(decoded, dict) else None
    except (TypeError, json.JSONDecodeError):
        return None


def _load_json_list(raw_value: Optional[str]) -> list[dict[str, object]]:
    try:
        decoded = json.loads(raw_value or "[]")
        return decoded if isinstance(decoded, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _report_campaign_metrics(db: Session, report: Report) -> list[dict[str, object]]:
    """Reconstrói a tabela de campanhas para relatórios gerados antes do snapshot."""
    rows = db.execute(
        select(
            Campaign.id,
            Campaign.name,
            func.coalesce(func.sum(MetricDaily.spend), 0),
            func.coalesce(func.sum(MetricDaily.impressions), 0),
            func.coalesce(func.sum(MetricDaily.clicks), 0),
            func.coalesce(func.sum(MetricDaily.conversions), 0),
            func.coalesce(func.sum(MetricDaily.conversion_value), 0),
        )
        .join(MetricDaily, MetricDaily.campaign_id == Campaign.id)
        .where(
            Campaign.client_id == report.client_id,
            MetricDaily.date >= report.start_date,
            MetricDaily.date <= report.end_date,
            MetricDaily.ad_id.is_(None),
        )
        .group_by(Campaign.id, Campaign.name)
        .order_by(func.sum(MetricDaily.spend).desc())
    ).all()
    return [{"id": row[0], "name": row[1], **_metrics_dict(*row[2:])} for row in rows]


def _generate_ai_summary(
    metrics: dict[str, float | int],
    client_name: str,
    campaign_name: Optional[str] = None,
    campaign_objective: Optional[str] = None,
) -> str:
    """Chama a IA em toda sincronização/geração e mantém a tela preenchida se ela falhar."""
    try:
        return generate_executive_summary(metrics, client_name, campaign_name, campaign_objective)
    except Exception as exc:
        logger.warning("Não foi possível gerar a análise OpenAI: %s", exc)
        scope = f"na campanha {campaign_name}" if campaign_name else "na visão geral da conta"
        return (
            f"No período, {client_name} investiu R$ {float(metrics['spend']):,.2f} e registrou "
            f"{float(metrics['conversions']):,.0f} resultados de mensagens e engajamento. "
            f"O CPA atual é R$ {float(metrics['cpa']):,.2f} e o CTR é {float(metrics['ctr']):,.2f}% {scope}.\n\n"
            "Os resultados devem ser analisados por campanha e criativo, distinguindo conversas iniciadas, "
            "cliques no link e eventos de conversão para preservar a qualidade dos leads.\n\n"
            "A próxima ação recomendada é ampliar os conjuntos mais eficientes e testar novas mensagens, "
            "monitorando semanalmente CPA, CTR e o volume de conversas qualificadas."
        )


def _mock_metrics() -> dict[str, float | int]:
    """Conjunto estável para demonstrações sem credenciais da Meta."""
    return {
        "spend": 4500.0,
        "impressions": 100000,
        "clicks": 2100,
        "conversions": 180.0,
        "conversion_value": 18900.0,
        "cpa": 25.0,
        "roas": 4.2,
        "ctr": 2.1,
    }


def _mock_summary(client_name: str, fallback: bool = False) -> str:
    origin = "A IA está temporariamente indisponível; " if fallback else ""
    return (
        f"{origin}No período analisado, {client_name} alcançou 180 conversões com investimento de R$ 4.500,00, "
        "mantendo ROAS de 4,2x e CTR de 2,1%. O resultado indica boa aderência entre a oferta e o público impactado.\n\n"
        "O principal ponto de atenção é preservar a eficiência à medida que o volume aumenta: o CPA de R$ 25,00 "
        "deve ser acompanhado por conjunto de anúncios, posicionamento e criativo para evitar concentração de investimento.\n\n"
        "A próxima ação recomendada é ampliar gradualmente os conjuntos com melhor retorno e testar dois novos "
        "criativos orientados à conversão, realocando orçamento semanalmente de acordo com CPA e ROAS."
    )


def _default_action_plan() -> str:
    return (
        "Ampliar gradualmente os conjuntos com melhor ROAS e CPA.\n\n"
        "Testar novos criativos com mensagens orientadas à conversão e revisar os resultados semanalmente."
    )


async def _store_creatives(raw_creatives: str, uploads: list[UploadFile]) -> list[dict[str, str]]:
    """Valida até cinco criativos, salva as imagens e prepara o contexto do PDF."""
    try:
        creatives = json.loads(raw_creatives)
    except json.JSONDecodeError as exc:
        raise ValueError("A lista de criativos enviada é inválida.") from exc
    if not isinstance(creatives, list) or len(creatives) > 5 or len(uploads) > 5:
        raise ValueError("Envie entre zero e cinco criativos.")

    upload_dir = CREATIVES_DIR / uuid4().hex
    result: list[dict[str, str]] = []
    for position, creative in enumerate(creatives, start=1):
        if not isinstance(creative, dict):
            raise ValueError("Cada criativo deve conter seus dados em formato válido.")
        image_url = ""
        image_index = creative.get("image_index")
        if image_index is not None:
            if not isinstance(image_index, int) or not 0 <= image_index < len(uploads):
                raise ValueError("A imagem associada ao criativo é inválida.")
            upload = uploads[image_index]
            if upload.content_type and not upload.content_type.startswith("image/"):
                raise ValueError("Os arquivos dos criativos devem ser imagens.")
            extension = Path(upload.filename or "").suffix.lower()
            if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                extension = ".png"
            content = await upload.read()
            if not content:
                raise ValueError("Uma das imagens enviadas está vazia.")
            upload_dir.mkdir(parents=True, exist_ok=True)
            image_path = upload_dir / f"creative_{position}{extension}"
            image_path.write_bytes(content)
            image_url = image_path.resolve().as_uri()
        elif creative.get("existing_image_url"):
            image_url = _existing_creative_image(str(creative["existing_image_url"]))
        result.append({
            "title": str(creative.get("title") or f"Criativo #{position}"),
            "performance": str(creative.get("performance") or ""),
            "observation": str(creative.get("observation") or ""),
            "image_url": image_url,
        })
    return result


def _existing_creative_image(image_url: str) -> str:
    """Preserva uma imagem já salva apenas se ela pertencer ao armazenamento de criativos."""
    parsed = urlparse(image_url)
    if parsed.scheme != "file":
        raise ValueError("A referência da imagem existente é inválida.")
    image_path = Path(url2pathname(unquote(parsed.path))).resolve()
    try:
        image_path.relative_to(CREATIVES_DIR.resolve())
    except ValueError as exc:
        raise ValueError("A imagem existente não pertence ao armazenamento permitido.") from exc
    if not image_path.is_file():
        raise ValueError("A imagem existente não foi encontrada no servidor.")
    return image_path.as_uri()


def _sync_mock_data(client: Client, db: Session, message: str) -> dict[str, object]:
    """Salva métricas mock para manter dashboard e relatórios funcionais."""
    today = date.today()
    campaign = db.scalar(select(Campaign).where(Campaign.client_id == client.id, Campaign.meta_campaign_id == f"mock-{client.id}"))
    if not campaign:
        campaign = Campaign(
            client_id=client.id,
            meta_campaign_id=f"mock-{client.id}",
            name="Campanha de Conversão - Demonstração",
            objective="OUTCOME_SALES",
            status="ACTIVE",
        )
        db.add(campaign)
        db.flush()
    metrics = _mock_metrics()
    for campaign_id in (None, campaign.id):
        metric = db.scalar(select(MetricDaily).where(
            MetricDaily.client_id == client.id,
            MetricDaily.date == today,
            MetricDaily.campaign_id.is_(None) if campaign_id is None else MetricDaily.campaign_id == campaign_id,
            MetricDaily.ad_id.is_(None),
        ))
        if not metric:
            metric = MetricDaily(client_id=client.id, campaign_id=campaign_id, date=today)
            db.add(metric)
        metric.spend = metrics["spend"]
        metric.impressions = metrics["impressions"]
        metric.clicks = metrics["clicks"]
        metric.conversions = metrics["conversions"]
        metric.conversion_value = metrics["conversion_value"]
    db.commit()
    return {
        "message": message,
        "campaigns": 1,
        "ads": 0,
        "metrics_synced": 2,
        "metrics": metrics,
        "executive_summary": _mock_summary(client.name),
        "mock_mode": True,
    }
