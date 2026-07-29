"""Modelos ORM da aplicação."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Client(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column("nome", String(255), nullable=False)
    meta_account_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    meta_access_token: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column("criado_em", DateTime, nullable=False, default=datetime.utcnow)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    metrics: Mapped[list["MetricDaily"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    client: Mapped["Client"] = relationship(back_populates="campaigns")
    ads: Mapped[list["Ad"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    metrics: Mapped[list["MetricDaily"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    meta_ad_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)
    copy_text: Mapped[Optional[str]] = mapped_column(Text)

    campaign: Mapped["Campaign"] = relationship(back_populates="ads")
    metrics: Mapped[list["MetricDaily"]] = relationship(back_populates="ad", cascade="all, delete-orphan")


class MetricDaily(Base):
    __tablename__ = "metrics_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), index=True)
    ad_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ads.id"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    spend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conversion_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    video_views_3s: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    client: Mapped["Client"] = relationship(back_populates="metrics")
    campaign: Mapped[Optional["Campaign"]] = relationship(back_populates="metrics")
    ad: Mapped[Optional["Ad"]] = relationship(back_populates="metrics")


class Report(Base):
    __tablename__ = "relatorios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column("cliente_id", ForeignKey("clientes.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column("campanha_id", Integer, nullable=True, index=True)
    campaign_name: Mapped[Optional[str]] = mapped_column("campanha_nome", String(255))
    start_date: Mapped[date] = mapped_column("data_inicio", Date, nullable=False)
    end_date: Mapped[date] = mapped_column("data_fim", Date, nullable=False)
    spend: Mapped[float] = mapped_column("investimento", Float, nullable=False, default=0.0)
    conversions: Mapped[float] = mapped_column("conversoes", Float, nullable=False, default=0.0)
    cpa: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    roas: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    action_plan: Mapped[Optional[str]] = mapped_column("plano_acao", Text)
    creatives_json: Mapped[Optional[str]] = mapped_column("criativos_json", Text)
    campaigns_json: Mapped[Optional[str]] = mapped_column("campanhas_json", Text)
    metrics_json: Mapped[Optional[str]] = mapped_column("metricas_json", Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    pdf_path: Mapped[Optional[str]] = mapped_column("caminho_pdf", Text)
    created_at: Mapped[datetime] = mapped_column("criado_em", DateTime, nullable=False, default=datetime.utcnow)

    client: Mapped["Client"] = relationship(back_populates="reports")
