export default function Navbar() {
  return (
    <header className="border-b border-white/10 bg-ink text-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 lg:px-8">
        <div>
          <p className="text-lg font-bold tracking-tight">Zeplin Lab Digital</p>
          <p className="text-sm text-violet-200">Gestão de Tráfego</p>
        </div>
        <div className="hidden rounded-full border border-violet-400/30 bg-violet-400/10 px-4 py-2 text-xs font-medium text-violet-100 sm:block">Meta Ads Intelligence</div>
      </div>
    </header>
  )
}
