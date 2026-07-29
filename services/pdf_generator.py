"""Renderização do template HTML Zeplin em PDF via xhtml2pdf."""

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "Template_relatório"
TEMPLATE_NAME = "modelo_relatorio_a4_com_logo.html"
LOGO_PATH = TEMPLATE_DIR / "logo.png"


def _currency(value: float | int | None) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _number(value: float | int | None) -> str:
    number = float(value or 0)
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")


def generate_pdf_report(report_data: dict[str, Any], output_path: str | Path) -> Path:
    """Renderiza o template HTML UTF-8 e grava o PDF no caminho informado."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    html = render_report_html(report_data)

    with destination.open("wb") as pdf_file:
        result = pisa.CreatePDF(
            src=html,
            dest=pdf_file,
            encoding="utf-8",
            link_callback=_resolve_local_asset,
        )
    if result.err:
        raise RuntimeError("xhtml2pdf não conseguiu renderizar o template do relatório.")
    return destination


def render_report_html(report_data: dict[str, Any]) -> str:
    """Aplica o contexto do relatório e a URL absoluta da logo ao template Jinja."""
    template_path = TEMPLATE_DIR / TEMPLATE_NAME
    if not template_path.is_file():
        raise RuntimeError(f"Template de relatório não encontrado: {template_path}")
    if not LOGO_PATH.is_file():
        raise RuntimeError(f"Logo não encontrada: {LOGO_PATH}")

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    environment.filters["currency"] = _currency
    environment.filters["number"] = _number
    summary = str(report_data.get("executive_summary", ""))
    return environment.get_template(TEMPLATE_NAME).render(
        report=report_data,
        logo_url=LOGO_PATH.resolve().as_uri(),
        summary_paragraphs=[paragraph.strip() for paragraph in summary.split("\n\n") if paragraph.strip()]
        or ["Resumo indisponível para este período."],
    )


def _resolve_local_asset(uri: str, relative_path: str | None) -> str:
    """Resolve ``file:///`` e arquivos relativos para o diretório do template."""
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return url2pathname(unquote(parsed.path))
    if not parsed.scheme:
        candidate = (TEMPLATE_DIR / unquote(uri)).resolve()
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(f"Recurso local não encontrado no template: {uri}")
