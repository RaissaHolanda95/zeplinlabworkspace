import { useState } from 'react'

const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-brand focus:ring-4 focus:ring-violet-100'

export default function ClientSelector({ clients, selectedClientId, onSelect, onCreate, loading }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', meta_account_id: '', meta_access_token: '' })
  const [saving, setSaving] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    try {
      await onCreate(form)
      setForm({ name: '', meta_account_id: '', meta_access_token: '' })
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="font-semibold">Cliente e conta de anúncios</h2><p className="mt-1 text-sm text-slate-500">Escolha uma conta para analisar os resultados.</p></div>
        <button onClick={() => setOpen(!open)} className="rounded-xl border border-brand px-4 py-2 text-sm font-semibold text-brand hover:bg-lavender">{open ? 'Cancelar' : '+ Novo cliente'}</button>
      </div>
      <select value={selectedClientId || ''} disabled={loading} onChange={(event) => onSelect(Number(event.target.value))} className={`${inputClass} mt-4`}>
        <option value="">{loading ? 'Carregando clientes...' : 'Selecione um cliente'}</option>
        {clients.map((client) => <option key={client.id} value={client.id}>{client.name} · {client.meta_account_id}</option>)}
      </select>
      {open && <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-3">
        <input required className={inputClass} placeholder="Nome do cliente" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input required className={inputClass} placeholder="Meta Account ID" value={form.meta_account_id} onChange={(e) => setForm({ ...form, meta_account_id: e.target.value })} />
        <input type="password" className={inputClass} placeholder="Access token (opcional: modo demonstração)" value={form.meta_access_token} onChange={(e) => setForm({ ...form, meta_access_token: e.target.value })} />
        <button disabled={saving} className="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60 md:col-span-3">{saving ? 'Cadastrando...' : 'Cadastrar cliente'}</button>
      </form>}
    </section>
  )
}
