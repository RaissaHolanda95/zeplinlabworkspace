export default function SyncButton({ onSync, loading, disabled }) {
  return <button onClick={onSync} disabled={disabled || loading} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50">
    {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
    {loading ? 'Sincronizando Meta Ads...' : 'Sincronizar dados reais'}
  </button>
}
