const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 })
const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })

const cards = [
  ['Valor usado', 'spend', currency],
  ['Resultados', 'conversions', number],
  ['Custo por resultado', 'cost_per_result', currency],
  ['Custo por mensagem', 'cost_per_message', currency],
  ['Impressões', 'impressions', number],
  ['Alcance', 'reach', number],
]

export default function MetricsCards({ metrics }) {
  return <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    {cards.map(([label, key, formatter]) => <article key={key} className="rounded-2xl border border-violet-100 bg-white p-5 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-bold tracking-tight text-ink">{formatter.format(Number(metrics?.[key]) || 0)}</p>
    </article>)}
  </section>
}
