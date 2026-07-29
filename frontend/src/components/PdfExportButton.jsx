export default function PdfExportButton({ onGenerate, loading, disabled }) {
  return <button onClick={onGenerate} disabled={disabled || loading} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50">
    {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
    {loading ? 'Gerando relatório...' : 'Gerar e abrir PDF'}
  </button>
}
