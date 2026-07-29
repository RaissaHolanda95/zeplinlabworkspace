const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-brand focus:ring-4 focus:ring-violet-100 disabled:bg-slate-50'

export default function CampaignSelector({ campaigns, selectedCampaignId, onSelect, loading, disabled }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div>
        <h2 className="font-semibold">Campanha</h2>
        <p className="mt-1 text-sm text-slate-500">Refine a análise para uma campanha ou mantenha a visão geral da conta.</p>
      </div>
      <select value={selectedCampaignId || ''} disabled={disabled || loading} onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : null)} className={`${inputClass} mt-4`}>
        <option value="">Todas as campanhas (Visão Geral)</option>
        {campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}{campaign.objective ? ` · ${campaign.objective}` : ''}</option>)}
      </select>
      {!loading && !disabled && campaigns.length === 0 && <p className="mt-2 text-xs text-slate-500">Sincronize a conta para carregar as campanhas disponíveis.</p>}
    </section>
  )
}
