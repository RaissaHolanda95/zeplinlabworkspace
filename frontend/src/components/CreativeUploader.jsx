const emptyCreative = () => ({ id: crypto.randomUUID(), image: null, title: '', performance: '', observation: '' })

export default function CreativeUploader({ creatives, onChange }) {
  function update(id, changes) { onChange(creatives.map((creative) => creative.id === id ? { ...creative, ...changes } : creative)) }
  function add() { if (creatives.length < 5) onChange([...creatives, emptyCreative()]) }
  function remove(id) { onChange(creatives.filter((creative) => creative.id !== id)) }
  return <section className="rounded-2xl bg-white p-6 shadow-soft">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Criativos para o relatório</h2><p className="mt-1 text-sm text-slate-500">Adicione apenas os anúncios que deseja destacar (até 5).</p></div><button type="button" onClick={add} disabled={creatives.length >= 5} className="rounded-xl border border-brand px-4 py-2 text-sm font-semibold text-brand disabled:opacity-50">+ Adicionar criativo</button></div>
    <div className="mt-5 grid gap-4 md:grid-cols-2">
      {creatives.map((creative, index) => <article key={creative.id} className="rounded-xl border border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between"><strong className="text-sm">Criativo #{index + 1}</strong><button type="button" onClick={() => remove(creative.id)} className="text-sm font-medium text-red-600">Remover</button></div>
        <label className="mb-3 block text-sm font-medium">Imagem / Print<input type="file" accept="image/*" onChange={(e) => update(creative.id, { image: e.target.files?.[0] || null })} className="mt-1 block w-full text-sm" /></label>
        {creative.image && <p className="mb-3 truncate text-xs text-slate-500">{creative.image.name}</p>}
        {!creative.image && creative.existing_image_url && <p className="mb-3 text-xs text-emerald-700">Imagem anterior será mantida no PDF.</p>}
        <input value={creative.title} onChange={(e) => update(creative.id, { title: e.target.value })} placeholder="Título do criativo" className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
        <input value={creative.performance} onChange={(e) => update(creative.id, { performance: e.target.value })} placeholder="Performance: 84 leads | CPL R$ 2,60" className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
        <textarea value={creative.observation} onChange={(e) => update(creative.id, { observation: e.target.value })} placeholder="Observação / análise" className="min-h-20 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
      </article>)}
    </div>
  </section>
}
