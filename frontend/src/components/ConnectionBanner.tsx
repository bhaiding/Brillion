export function ConnectionBanner({ status }: { status: string }) {
  if (status === 'connected') return null
  return (
    <div className="fixed inset-x-0 top-0 z-50 bg-ink px-4 py-2 text-center text-sm font-bold text-white" role="status">
      {status === 'offline' ? 'You are offline. We’ll reconnect when your network returns.' : 'Reconnecting to the game…'}
    </div>
  )
}

