export default function AiSummaryBox({ summary, onChange }) {
  return <section className="rounded-2xl border border-violet-200 bg-gradient-to-br from-lavender to-white p-6 shadow-soft">
    <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-brand font-bold text-white">AI</span><div><h2 className="font-semibold">Análise Estratégica</h2><p className="text-sm text-slate-500">Resumo Executivo gerado por IA</p></div></div>
    <textarea value={summary} onChange={(event) => onChange(event.target.value)} placeholder="Gere um relatório para preencher a análise ou escreva sua revisão aqui." className="mt-5 min-h-40 w-full resize-y rounded-xl border border-violet-200 bg-white/80 p-4 text-sm leading-7 text-slate-700 outline-none focus:border-brand focus:ring-4 focus:ring-violet-100" />
  </section>
}
