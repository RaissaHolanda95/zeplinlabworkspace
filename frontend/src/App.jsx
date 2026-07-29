import { useEffect, useMemo, useRef, useState } from 'react'
import AiSummaryBox from './components/AiSummaryBox'
import CampaignMetricsTable from './components/CampaignMetricsTable'
import CampaignSelector from './components/CampaignSelector'
import ClientSelector from './components/ClientSelector'
import CreativeUploader from './components/CreativeUploader'
import MetricsCards from './components/MetricsCards'
import Navbar from './components/Navbar'
import PdfExportButton from './components/PdfExportButton'
import ReportHistory from './components/ReportHistory'
import SyncButton from './components/SyncButton'
import { createClient, generateReport, getApiError, getCampaigns, getClients, getReport, getReportPdfUrl, syncClient } from './services/api'

const today = new Date().toISOString().slice(0, 10)
const firstDay = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
const DRAFT_KEY = 'zeplin-lab:report-draft:v1'

const asNumber = (value) => Number.isFinite(Number(value)) ? Number(value) : 0

function savedCampaignRows(report) {
  if (Array.isArray(report.campaign_metrics)) return report.campaign_metrics
  if (Array.isArray(report.campaigns)) return report.campaigns
  return []
}

function rebuildMetrics(savedMetrics, campaignRows) {
  const source = savedMetrics && typeof savedMetrics === 'object' ? savedMetrics : {}
  const totals = campaignRows.reduce((sum, row) => ({
    spend: sum.spend + asNumber(row.spend), impressions: sum.impressions + asNumber(row.impressions),
    reach: sum.reach + asNumber(row.reach), clicks: sum.clicks + asNumber(row.clicks),
    conversions: sum.conversions + asNumber(row.conversions), message_conversations: sum.message_conversations + asNumber(row.message_conversations || row.conversions),
    conversion_value: sum.conversion_value + asNumber(row.conversion_value),
  }), { spend: 0, impressions: 0, reach: 0, clicks: 0, conversions: 0, message_conversations: 0, conversion_value: 0 })
  const value = (key) => asNumber(source[key]) || asNumber(totals[key])
  const spend = value('spend')
  const conversions = value('conversions')
  const messages = value('message_conversations') || conversions
  const impressions = value('impressions')
  return {
    spend, impressions, reach: value('reach'), clicks: value('clicks'), conversions, message_conversations: messages,
    conversion_value: value('conversion_value'),
    cost_per_result: conversions ? Math.round((spend / conversions) * 100) / 100 : 0,
    cost_per_message: conversions ? Math.round((spend / conversions) * 100) / 100 : 0,
    cpa: conversions ? Math.round((spend / conversions) * 100) / 100 : 0,
    roas: spend ? Math.round((value('conversion_value') / spend) * 100) / 100 : 0,
    ctr: impressions ? Math.round((value('clicks') / impressions) * 10000) / 100 : 0,
  }
}

function metricsForCampaignFilter(selectedCampaignId, campaignRows, fallbackMetrics) {
  if (!campaignRows.length) return selectedCampaignId ? rebuildMetrics({}, []) : (fallbackMetrics || rebuildMetrics({}, []))
  const filteredRows = selectedCampaignId
    ? campaignRows.filter((campaign) => Number(campaign.id) === Number(selectedCampaignId))
    : campaignRows
  // Se uma campanha sem dados for selecionada, os cards devem refletir zero — nunca o total da conta.
  const aggregated = rebuildMetrics({}, filteredRows)
  // Na visão geral, alcance é um usuário único no período e vem do nível conta da Meta,
  // não da soma dos alcances das campanhas.
  return !selectedCampaignId && fallbackMetrics?.reach !== undefined
    ? { ...aggregated, reach: asNumber(fallbackMetrics.reach) }
    : aggregated
}

function resolveSavedCampaignId(report, campaignRows, availableCampaigns) {
  const overview = report.campaign_name === 'Todas as campanhas (Visão Geral)'
  const byId = availableCampaigns.find((campaign) => Number(campaign.id) === Number(report.campaign_id))
  if (byId) return byId.id
  if (overview && campaignRows.length !== 1) return null
  const savedName = overview ? campaignRows[0]?.name : (report.campaign_name || (campaignRows.length === 1 ? campaignRows[0]?.name : ''))
  const byName = availableCampaigns.find((campaign) => campaign.name === savedName)
  if (byName) return byName.id
  const firstSaved = campaignRows[0]
  const bySavedId = availableCampaigns.find((campaign) => Number(campaign.id) === Number(firstSaved?.id))
  return bySavedId?.id || null
}

function loadDraft() {
  try {
    const draft = JSON.parse(window.localStorage.getItem(DRAFT_KEY) || '{}')
    return {
      summary: typeof draft.summary === 'string' ? draft.summary : '',
      actionPlan: typeof draft.actionPlan === 'string' ? draft.actionPlan : '',
      creatives: Array.isArray(draft.creatives)
        ? draft.creatives.slice(0, 5).map((creative) => ({
          id: creative.id || crypto.randomUUID(), image: null,
          title: String(creative.title || ''), performance: String(creative.performance || ''), observation: String(creative.observation || ''),
        }))
        : [],
    }
  } catch { return { summary: '', actionPlan: '', creatives: [] } }
}

export default function App() {
  const [draft] = useState(loadDraft)
  const skipDraftSave = useRef(false)
  const restoringReportRef = useRef(false)
  const restoredMetricsRef = useRef(null)
  const restoredCampaignIdRef = useRef(null)
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [campaignMetrics, setCampaignMetrics] = useState([])
  const [campaignId, setCampaignId] = useState(null)
  const [dates, setDates] = useState({ start_date: firstDay, end_date: today })
  const [metrics, setMetrics] = useState(null)
  const [summary, setSummary] = useState(() => draft.summary)
  const [actionPlan, setActionPlan] = useState(() => draft.actionPlan)
  const [creatives, setCreatives] = useState(() => draft.creatives)
  const [loadingClients, setLoadingClients] = useState(true)
  const [loadingCampaigns, setLoadingCampaigns] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [isEditingReport, setIsEditingReport] = useState(false)
  const [notice, setNotice] = useState(null)
  const [historyVersion, setHistoryVersion] = useState(0)
  const dashboardMetrics = useMemo(
    () => metricsForCampaignFilter(campaignId, campaignMetrics, metrics),
    [campaignId, campaignMetrics, metrics],
  )

  useEffect(() => { loadClients() }, [])
  useEffect(() => {
    if (skipDraftSave.current) {
      skipDraftSave.current = false
      return
    }
    const textCreatives = creatives.map(({ id, title, performance, observation }) => ({ id, title, performance, observation }))
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ summary, actionPlan, creatives: textCreatives }))
  }, [summary, actionPlan, creatives])
  useEffect(() => {
    // Ao reabrir um relatório, o filtro salvo é aplicado pelo carregamento e não
    // deve ser sobrescrito por esta limpeza normal de troca de cliente.
    if (!restoringReportRef.current && !isEditingReport) setCampaignId(null)
    setCampaigns([])
    if (!restoringReportRef.current && !isEditingReport) setCampaignMetrics([])
    if (clientId) loadCampaigns(clientId)
  }, [clientId])
  async function loadClients() {
    setLoadingClients(true)
    try { const data = await getClients(); setClients(data); if (data.length) setClientId((current) => current || data[0].id) }
    catch (error) { setNotice({ type: 'error', text: getApiError(error) }) }
    finally { setLoadingClients(false) }
  }
  async function loadCampaigns(id = clientId) {
    if (!id) return
    setLoadingCampaigns(true)
    try { setCampaigns(await getCampaigns(id)) }
    catch (error) { console.error('Falha ao carregar campanhas:', error?.response?.data || error); setCampaigns([]) }
    finally { setLoadingCampaigns(false) }
  }
  async function handleCreate(form) {
    const payload = { ...form, name: form.name.trim(), meta_account_id: form.meta_account_id.trim() }
    if (!form.meta_access_token.trim()) delete payload.meta_access_token
    try { const client = await createClient(payload); setClients((items) => [client, ...items]); setClientId(client.id); setNotice({ type: 'success', text: 'Cliente cadastrado com sucesso.' }) }
    catch (error) { console.error('Falha ao cadastrar cliente:', error?.response?.data || error); setNotice({ type: 'error', text: `Falha ao cadastrar cliente: ${getApiError(error)}` }); throw error }
  }
  async function handleSync({ manual = false } = {}) {
    // A Meta/IA só pode ser acionada por uma intenção explícita do botão.
    if (!manual) return
    setSyncing(true); setNotice(null)
    try { const result = await syncClient(clientId, { ...dates, ...(campaignId ? { campaign_id: campaignId } : {}) }); if (typeof result.metrics === 'object') setMetrics(result.metrics); if (Array.isArray(result.campaign_metrics)) setCampaignMetrics(result.campaign_metrics); if (result.executive_summary) setSummary(result.executive_summary); setIsEditingReport(false); await loadCampaigns(); setNotice({ type: 'success', text: result.message || `Sincronização concluída: ${result.campaigns} campanhas e ${result.ads} anúncios.` }) }
    catch (error) { console.error('Falha ao sincronizar:', error?.response?.data || error); setNotice({ type: 'error', text: getApiError(error) }) }
    finally { setSyncing(false) }
  }
  function handleCampaignSelect(nextCampaignId) {
    setCampaignId(nextCampaignId)
    const cachedMetrics = campaignMetrics.find((campaign) => Number(campaign.id) === Number(nextCampaignId))
    if (cachedMetrics) {
      setMetrics(cachedMetrics)
      return
    }
    if (Number(nextCampaignId) === Number(restoredCampaignIdRef.current) && restoredMetricsRef.current) {
      setMetrics(restoredMetricsRef.current)
      return
    }
    // Não mantém os números da campanha anterior enquanto a nova ainda não foi sincronizada.
    setMetrics(null)
  }
  async function handleGenerate() {
    setGenerating(true); setNotice(null)
    try {
      const formData = new FormData()
      formData.append('client_id', clientId)
      if (campaignId) formData.append('campaign_id', campaignId)
      formData.append('start_date', dates.start_date)
      formData.append('end_date', dates.end_date)
      formData.append('executive_summary', summary)
      formData.append('action_plan', actionPlan)
      formData.append('metrics_snapshot', JSON.stringify(dashboardMetrics))
      const creativePayload = creatives.map((creative) => {
        const item = { title: creative.title, performance: creative.performance, observation: creative.observation }
        if (creative.image) { item.image_index = formData.getAll('creative_images').length; formData.append('creative_images', creative.image) }
        else if (creative.existing_image_url) item.existing_image_url = creative.existing_image_url
        return item
      })
      formData.append('creatives', JSON.stringify(creativePayload))
      const report = await generateReport(formData)
      skipDraftSave.current = true
      window.localStorage.removeItem(DRAFT_KEY)
      window.open(getReportPdfUrl(report.id), '_blank', 'noopener,noreferrer')
      resetReportForm()
      setNotice({ type: 'success', text: 'Relatório gerado com sucesso. O formulário foi preparado para um novo relatório.' }); setHistoryVersion((value) => value + 1)
    } catch (error) { setNotice({ type: 'error', text: getApiError(error) }) }
    finally { setGenerating(false) }
  }
  function resetReportForm() {
    restoringReportRef.current = false
    restoredCampaignIdRef.current = null
    restoredMetricsRef.current = null
    setIsEditingReport(false)
    setCampaignId(null)
    setDates({ start_date: firstDay, end_date: today })
    setMetrics(null)
    setCampaignMetrics([])
    setSummary('')
    setActionPlan('')
    setCreatives([])
  }
  async function handleEditReport(reportId) {
    setNotice(null)
    try {
      const report = await getReport(reportId)
      const campaignRows = savedCampaignRows(report)
      const restoredMetrics = report.has_metrics_snapshot ? report.metrics : rebuildMetrics(report.metrics, campaignRows)
      restoringReportRef.current = true
      setIsEditingReport(true)
      setClientId(report.client_id)
      setDates({ start_date: report.start_date, end_date: report.end_date })
      setMetrics(restoredMetrics)
      setSummary(report.executive_summary || '')
      setActionPlan(report.action_plan || '')
      setCreatives((report.creatives || []).map((creative) => ({
        id: crypto.randomUUID(), image: null, existing_image_url: creative.image_url || '',
        title: creative.title || '', performance: creative.performance || '', observation: creative.observation || '',
      })))
      const availableCampaigns = await getCampaigns(report.client_id)
      const hydratedCampaignRows = campaignRows.map((row) => ({
        ...row,
        id: row.id || availableCampaigns.find((campaign) => campaign.name === row.name)?.id || null,
      }))
      const resolvedCampaignId = resolveSavedCampaignId(report, hydratedCampaignRows, availableCampaigns)
      restoredCampaignIdRef.current = resolvedCampaignId
      restoredMetricsRef.current = restoredMetrics
      setCampaigns(availableCampaigns)
      setCampaignId(resolvedCampaignId)
      setCampaignMetrics(hydratedCampaignRows.length ? hydratedCampaignRows : (resolvedCampaignId ? [{ id: resolvedCampaignId, name: report.campaign_name, ...restoredMetrics }] : []))
      restoringReportRef.current = false
      setNotice({ type: 'success', text: 'Relatório carregado para edição. Sincronize novamente se quiser atualizar as métricas antes de gerar o novo PDF.' })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (error) {
      setIsEditingReport(false)
      setNotice({ type: 'error', text: getApiError(error) })
    }
  }
  function handleClientSelect(nextClientId) {
    setIsEditingReport(false)
    restoredCampaignIdRef.current = null
    restoredMetricsRef.current = null
    setClientId(nextClientId)
  }
  const disabled = !clientId || !dates.start_date || !dates.end_date
  return <><Navbar /><main className="mx-auto max-w-7xl space-y-6 px-5 py-7 lg:px-8">
    <div><p className="text-sm font-semibold text-brand">DASHBOARD</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Resultados de mídia paga</h1><p className="mt-2 text-slate-500">Sincronize sua conta Meta Ads e gere relatórios executivos.</p></div>
    {notice && <div className={`rounded-xl border px-4 py-3 text-sm ${notice.type === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{notice.text}</div>}
    <ClientSelector clients={clients} selectedClientId={clientId} onSelect={handleClientSelect} onCreate={handleCreate} loading={loadingClients} />
    <CampaignSelector campaigns={campaigns} selectedCampaignId={campaignId} onSelect={handleCampaignSelect} loading={loadingCampaigns} disabled={!clientId} />
    <section className="grid gap-4 rounded-2xl bg-white p-5 shadow-soft md:grid-cols-[1fr_1fr_auto_auto] md:items-end"><label className="text-sm font-medium">Data inicial<input type="date" value={dates.start_date} onChange={(e) => setDates({ ...dates, start_date: e.target.value })} className="mt-2 block w-full rounded-xl border border-slate-200 px-3 py-2.5" /></label><label className="text-sm font-medium">Data final<input type="date" value={dates.end_date} onChange={(e) => setDates({ ...dates, end_date: e.target.value })} className="mt-2 block w-full rounded-xl border border-slate-200 px-3 py-2.5" /></label><SyncButton onSync={() => handleSync({ manual: true })} loading={syncing} disabled={disabled} /><PdfExportButton onGenerate={handleGenerate} loading={generating} disabled={disabled} /></section>
    <MetricsCards metrics={dashboardMetrics} />
    <CampaignMetricsTable campaigns={campaignMetrics} />
    <AiSummaryBox summary={summary} onChange={setSummary} />
    <section className="rounded-2xl bg-white p-6 shadow-soft"><h2 className="font-semibold">Plano de Ação / Recomendações</h2><p className="mt-1 text-sm text-slate-500">Edite as próximas ações que serão incluídas no relatório.</p><textarea value={actionPlan} onChange={(event) => setActionPlan(event.target.value)} placeholder="Descreva as ações recomendadas para o próximo período." className="mt-4 min-h-32 w-full resize-y rounded-xl border border-slate-200 p-4 text-sm leading-7 outline-none focus:border-brand focus:ring-4 focus:ring-violet-100" /></section>
    <CreativeUploader creatives={creatives} onChange={setCreatives} />
    <ReportHistory clientId={clientId} dates={dates} refreshKey={historyVersion} onEdit={handleEditReport} />
  </main></>
}
