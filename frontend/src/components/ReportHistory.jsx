import { useEffect, useState } from 'react'
import { deleteReport, getApiError, getReportPdfUrl, getReports } from '../services/api'

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export default function ReportHistory({ clientId, dates, refreshKey, onEdit }) {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    getReports({ client_id: clientId || undefined, start_date: dates.start_date || undefined, end_date: dates.end_date || undefined })
      .then((data) => active && setReports(data))
      .catch((err) => active && setError(getApiError(err)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [clientId, dates.start_date, dates.end_date, refreshKey])
  async function handleDelete(report) {
    if (!window.confirm(`Tem certeza de que deseja excluir o relatório de ${report.client_name}?`)) return
    setDeletingId(report.id)
    setError('')
    try {
      await deleteReport(report.id)
      setReports((current) => current.filter((item) => item.id !== report.id))
    } catch (err) {
      setError(getApiError(err))
    } finally {
      setDeletingId(null)
    }
  }
  async function handleEdit(report) {
    setEditingId(report.id)
    setError('')
    try { await onEdit(report.id) }
    catch (err) { setError(getApiError(err)) }
    finally { setEditingId(null) }
  }
  return <section className="rounded-2xl bg-white p-6 shadow-soft">
    <div><h2 className="font-semibold">Histórico de Relatórios</h2><p className="mt-1 text-sm text-slate-500">Filtrado pelo cliente e período selecionados acima.</p></div>
    {loading && <p className="mt-5 text-sm text-slate-500">Carregando histórico...</p>}
    {error && <p className="mt-5 text-sm text-red-600">{error}</p>}
    {!loading && !error && <div className="mt-5 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b text-xs uppercase tracking-wide text-slate-500"><tr><th className="pb-3 pr-4">Cliente</th><th className="pb-3 pr-4">Período</th><th className="pb-3 pr-4">Investimento</th><th className="pb-3 pr-4">ROAS</th><th className="pb-3 pr-4">PDF</th><th className="pb-3 text-right">Ações</th></tr></thead><tbody>{reports.map((report) => <tr key={report.id} className="border-b border-slate-100"><td className="py-3 pr-4 font-medium">{report.client_name}</td><td className="py-3 pr-4">{new Date(`${report.start_date}T00:00:00`).toLocaleDateString('pt-BR')} – {new Date(`${report.end_date}T00:00:00`).toLocaleDateString('pt-BR')}</td><td className="py-3 pr-4">{currency.format(report.spend)}</td><td className="py-3 pr-4">{Number(report.roas).toFixed(2)}x</td><td className="py-3 pr-4"><a className="font-semibold text-brand hover:underline" href={getReportPdfUrl(report.id)} target="_blank" rel="noreferrer">Baixar PDF</a></td><td className="flex justify-end gap-1 py-3 text-right"><button type="button" onClick={() => handleEdit(report)} disabled={editingId === report.id || deletingId === report.id} className="rounded-lg px-3 py-1.5 font-semibold text-brand transition hover:bg-lavender disabled:cursor-wait disabled:opacity-60">{editingId === report.id ? 'Carregando...' : 'Editar'}</button><button type="button" onClick={() => handleDelete(report)} disabled={deletingId === report.id || editingId === report.id} className="rounded-lg px-3 py-1.5 font-semibold text-red-600 transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-60" aria-label={`Excluir relatório ${report.id}`}>{deletingId === report.id ? 'Excluindo...' : 'Excluir'}</button></td></tr>)}{reports.length === 0 && <tr><td className="py-5 text-slate-500" colSpan="6">Nenhum relatório encontrado para estes filtros.</td></tr>}</tbody></table></div>}
  </section>
}
