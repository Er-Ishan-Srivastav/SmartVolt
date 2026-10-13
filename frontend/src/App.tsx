import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  BatteryCharging,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Home,
  LayoutDashboard,
  Leaf,
  LoaderCircle,
  LogOut,
  Plus,
  Power,
  ReceiptText,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Wallet,
  Zap,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type Meter = {
  id: number
  room_id: number
  current_balance: string
  power_status: boolean
  tariff_per_kwh: string
  created_at: string
}
type DailyUsage = { date: string; units_used: string; cost: string }
type UsageReport = {
  meter_id: number
  period: '1d' | '7d' | '30d'
  total_units: string
  total_cost: string
  reading_count: number
  daily: DailyUsage[]
}
type Recharge = {
  id: number
  user_id: number
  amount: string
  status: string
  created_at: string
}
type ApiError = { detail?: string }

const money = (amount: string | number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(amount))
const shortDate = (date: string) =>
  new Date(`${date}T00:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export default function App() {
  const [meters, setMeters] = useState<Meter[]>([])
  const [meter, setMeter] = useState<Meter | null>(null)
  const [report, setReport] = useState<UsageReport | null>(null)
  const [recharges, setRecharges] = useState<Recharge[]>([])
  const [period, setPeriod] = useState<'1d' | '7d' | '30d'>('7d')
  const [page, setPage] = useState('Overview')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [showRecharge, setShowRecharge] = useState(false)
  const [rechargeAmount, setRechargeAmount] = useState('200')
  const [userId, setUserId] = useState('2')
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadMeters = useCallback(async () => {
    setLoading(true)
    try {
      const items = await api<Meter[]>('/meters')
      setMeters(items)
      setMeter((current) => items.find((item) => item.id === current?.id) ?? items[0] ?? null)
      if (!items.length) setNotice({ type: 'error', text: 'No meters found. Run migrations, then seed the demo data.' })
      else setNotice(null)
    } catch (error) {
      setNotice({ type: 'error', text: `${(error as Error).message}. Is the FastAPI server running?` })
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetails = useCallback(async (meterId: number, selectedPeriod: '1d' | '7d' | '30d') => {
    const [freshMeter, freshReport, history] = await Promise.all([
      api<Meter>(`/meters/${meterId}`),
      api<UsageReport>(`/meters/${meterId}/report?period=${selectedPeriod}`),
      api<Recharge[]>(`/meters/${meterId}/recharges?limit=5`),
    ])
    setMeter(freshMeter)
    setReport(freshReport)
    setRecharges(history)
  }, [])

  useEffect(() => { void loadMeters() }, [loadMeters])

  useEffect(() => {
    if (!meter?.id) return
    let live = true
    loadDetails(meter.id, period).catch((error: Error) => {
      if (live) setNotice({ type: 'error', text: error.message })
    })
    return () => { live = false }
  }, [meter?.id, period, loadDetails])

  const chartData = useMemo(() => (report?.daily ?? []).map((item) => ({
    date: shortDate(item.date),
    units: Number(item.units_used),
    cost: Number(item.cost),
  })), [report])
  const averageDaily = report && chartData.length ? Number(report.total_units) / chartData.length : 0

  async function refresh() {
    if (!meter) return
    await loadDetails(meter.id, period)
  }

  async function togglePower() {
    if (!meter) return
    setBusy(true)
    setNotice(null)
    try {
      const updated = await api<Meter>(`/meters/${meter.id}/power`, {
        method: 'PATCH', body: JSON.stringify({ power_status: !meter.power_status }),
      })
      setMeter(updated)
      setNotice({ type: 'success', text: `Room power turned ${updated.power_status ? 'on' : 'off'}.` })
    } catch (error) {
      setNotice({ type: 'error', text: (error as Error).message })
    } finally {
      setBusy(false)
    }
  }

  async function submitRecharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!meter) return
    setBusy(true)
    setNotice(null)
    try {
      await api<Recharge>(`/meters/${meter.id}/recharges`, {
        method: 'POST',
        body: JSON.stringify({ user_id: Number(userId), amount: rechargeAmount, idempotency_key: crypto.randomUUID() }),
      })
      setShowRecharge(false)
      setNotice({ type: 'success', text: 'Demo recharge added to the meter wallet.' })
      await refresh()
    } catch (error) {
      setNotice({ type: 'error', text: (error as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const navItems = [
    { label: 'Overview', icon: LayoutDashboard, target: 'overview-top' },
    { label: 'Usage history', icon: Activity, target: 'usage-panel' },
    { label: 'Transactions', icon: ReceiptText, target: 'transactions-panel' },
    { label: 'Room details', icon: Home, target: 'power-panel' },
  ]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" onClick={() => setPage('Overview')}>
          <span className="brand-mark"><Zap size={21} fill="currentColor" /></span>
          <span><strong>smartvolt</strong><small>ENERGY, MADE CLEAR</small></span>
        </a>
        <div className="side-caption">WORKSPACE</div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon, target }) => (
            <button key={label} className={`nav-item ${page === label ? 'active' : ''}`} onClick={() => { setPage(label); document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {label === 'Transactions' && <span className="nav-count">{recharges.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="savings-card">
          <div className="savings-icon"><Leaf size={18} /></div>
          <strong>Small changes add up.</strong>
          <p>Keep an eye on your usage and make every unit count.</p>
          <div className="saving-dots"><i /><i /><i /><i /><i /><i /><i /></div>
        </div>
        <div className="nav-bottom">
          <button className="nav-item" onClick={() => setNotice({ type: 'success', text: 'Settings will be available after authentication is added.' })}><Settings size={18} /><span>Settings</span></button>
          <button className="nav-item" onClick={() => setNotice({ type: 'success', text: 'Support tickets API is available in /docs.' })}><CircleHelp size={18} /><span>Help & support</span></button>
        </div>
        <div className="profile-row">
          <div className="avatar">IS</div>
          <div className="profile-copy"><strong>Ishan Srivastav</strong><small>Resident · Demo account</small></div>
          <button aria-label="Account actions" className="icon-ghost" onClick={() => setNotice({ type: 'success', text: 'Demo profile. Authentication is not wired up yet.' })}><LogOut size={16} /></button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{page}</strong></div>
          <div className="topbar-right">
            <span className="system-status"><i /> API connected</span>
            <span className="topbar-date"><Clock3 size={15} /> {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
            <button className="avatar mini" aria-label="Profile">IS</button>
          </div>
        </header>

        <div className="page-content">
          {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.type === 'success' ? <Check size={17} /> : <CircleHelp size={17} />}{notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}
          <section className="welcome-row" id="overview-top">
            <div>
              <div className="eyebrow"><Sparkles size={14} /> YOUR ENERGY OVERVIEW</div>
              <h1>{page === 'Overview' ? 'Good evening, Ishan' : page}</h1>
              <p className="subheading">Here’s what’s happening with your room’s electricity today.</p>
            </div>
            <div className="header-actions">
              <label className="meter-select"><span>Meter</span><select value={meter?.id ?? ''} onChange={(event) => setMeter(meters.find((item) => item.id === Number(event.target.value)) ?? null)} aria-label="Select meter">
                {meters.map((item) => <option value={item.id} key={item.id}>Room {item.room_id} · #{item.id}</option>)}
              </select><ChevronDown size={14} /></label>
              <button className="button primary" onClick={() => setShowRecharge(true)} disabled={!meter}><Plus size={17} /> Add money</button>
            </div>
          </section>

          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={24} /> Connecting to SmartVolt API…</div> : !meter ? <div className="empty-state"><BatteryCharging size={28} /><h2>No meter connected yet</h2><p>Seed the local database to create the demo room and meter.</p><code>python -m app.db.seed</code></div> : <>
            <section className="metric-grid" aria-label="Energy summary">
              <article className="metric-card balance-card">
                <div className="card-top"><span className="metric-label">Available balance</span><span className="metric-icon mint"><Wallet size={18} /></span></div>
                <div className="balance-number">{money(meter.current_balance)}</div>
                <div className="metric-foot"><span className={`tiny-pill ${Number(meter.current_balance) > 0 ? 'good' : 'warning'}`}><i />{Number(meter.current_balance) > 0 ? 'Balance available' : 'Recharge needed'}</span><span>Room {meter.room_id}</span></div>
                <div className="balance-spark"><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /></div>
              </article>
              <article className="metric-card">
                <div className="card-top"><span className="metric-label">Energy consumed</span><span className="metric-icon lilac"><Zap size={18} /></span></div>
                <div className="metric-number">{Number(report?.total_units ?? 0).toFixed(2)} <small>kWh</small></div>
                <div className="metric-foot"><span className="muted-foot">Selected {period === '1d' ? 'day' : period === '7d' ? '7 days' : '30 days'}</span><span className="trend"><TrendingUp size={13} /> Usage</span></div>
              </article>
              <article className="metric-card">
                <div className="card-top"><span className="metric-label">Estimated cost</span><span className="metric-icon peach"><ReceiptText size={18} /></span></div>
                <div className="metric-number">{money(report?.total_cost ?? 0)}</div>
                <div className="metric-foot"><span className="muted-foot">At current tariff</span><span className="rate-text">{money(meter.tariff_per_kwh)}/kWh</span></div>
              </article>
              <article className="metric-card power-card">
                <div className="card-top"><span className="metric-label">Room power</span><span className={`metric-icon ${meter.power_status ? 'mint' : 'peach'}`}><Power size={18} /></span></div>
                <div className="power-state"><span className={`power-dot ${meter.power_status ? 'on' : ''}`} />{meter.power_status ? 'On' : 'Off'}</div>
                <div className="metric-foot"><span className="muted-foot">Simulated relay control</span><button className={`toggle ${meter.power_status ? 'on' : ''}`} onClick={togglePower} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)} aria-label="Toggle room power"><span /></button></div>
              </article>
            </section>

            <section className="content-grid">
              <article className="panel usage-panel" id="usage-panel">
                <div className="panel-header">
                  <div><h2>Consumption analytics</h2><p>Track your electricity patterns over time.</p></div>
                  <div className="period-control" role="group" aria-label="Report period">
                    {(['1d', '7d', '30d'] as const).map((item) => <button key={item} title={item === '1d' ? 'Current UTC calendar day' : undefined} className={period === item ? 'selected' : ''} onClick={() => setPeriod(item)}>{item === '1d' ? 'Today' : item === '7d' ? '7 days' : '30 days'}</button>)}
                  </div>
                </div>
                <div className="chart-summary"><div><span className="chart-legend"><i /> Energy used</span><strong>{Number(report?.total_units ?? 0).toFixed(2)} <small>kWh</small></strong></div><span className="chart-average">Daily avg. {averageDaily.toFixed(2)} kWh</span></div>
                <div className="chart-wrap">
                  {chartData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 12, right: 8, left: -19, bottom: 0 }} barCategoryGap="32%">
                    <CartesianGrid vertical={false} stroke="#e9edf3" strokeDasharray="4 6" />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#8b96a7', fontSize: 11 }} dy={8} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#8b96a7', fontSize: 11 }} />
                    <Tooltip cursor={{ fill: '#f2f7f5' }} formatter={(value) => [`${Number(value).toFixed(3)} kWh`, 'Energy used']} contentStyle={{ border: '1px solid #e8edf2', borderRadius: 12, fontSize: 12 }} />
                    <Bar dataKey="units" fill="#27aa84" radius={[5, 5, 1, 1]} maxBarSize={34} />
                  </BarChart></ResponsiveContainer> : <div className="chart-empty"><Activity size={25} /><span>No consumption readings in this period yet.</span><small>Use the simulator worker or the API to record readings.</small></div>}
                </div>
                <div className="chart-footer"><span><ShieldCheck size={15} /> Readings stored by SmartVolt</span><button className="text-button" onClick={() => setPage('Usage history')}>View detailed history <ArrowUpRight size={14} /></button></div>
              </article>

              <article className="panel power-panel" id="power-panel">
                <div className="panel-header"><div><h2>Meter status</h2><p>Software relay state</p></div><span className="live-label"><i /> SIMULATED</span></div>
                <div className="meter-illustration"><div className="meter-ring"><div className="meter-core"><Zap size={30} fill="currentColor" /><small>SMART METER</small><strong>#{meter.id.toString().padStart(3, '0')}</strong></div></div><div className="meter-decoration dot-one" /><div className="meter-decoration dot-two" /><div className="meter-decoration ring-small" /></div>
                <div className="status-list">
                  <div><span><i className="status-check"><Check size={11} /></i> Connection</span><strong>Connected</strong></div>
                  <div><span><i className={`status-circle ${meter.power_status ? 'green' : 'gray'}`} />Power relay</span><strong>{meter.power_status ? 'Enabled' : 'Disabled'}</strong></div>
                  <div><span><i className="status-circle green" />Meter tariff</span><strong>{money(meter.tariff_per_kwh)} / kWh</strong></div>
                </div>
                <button className="button secondary full-width" onClick={togglePower} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)}><Power size={16} /> Turn power {meter.power_status ? 'off' : 'on'}</button>
                <p className="panel-note">This is a software simulation. No physical electrical relay is connected.</p>
              </article>
            </section>

            <section className="bottom-grid">
              <article className="panel transactions-panel" id="transactions-panel">
                <div className="panel-header"><div><h2>Recent transactions</h2><p>Your latest wallet recharges.</p></div><button className="text-button" onClick={() => setPage('Transactions')}>See all <ArrowUpRight size={14} /></button></div>
                {recharges.length ? <div className="transaction-list">{recharges.map((item) => <div className="transaction-row" key={item.id}><div className="transaction-icon"><ArrowDownLeft size={17} /></div><div className="transaction-main"><strong>Wallet recharge</strong><small>{new Date(item.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} · User #{item.user_id}</small></div><div className="transaction-amount"><strong>+{money(item.amount)}</strong><small className="transaction-success"><i />{item.status.toLowerCase()}</small></div></div>)}</div> : <div className="mini-empty"><Wallet size={22} /><span>No recharges yet</span><button onClick={() => setShowRecharge(true)}>Add your first recharge</button></div>}
              </article>
              <article className="impact-card"><div className="impact-top"><span className="impact-icon"><Leaf size={19} /></span><span className="impact-label">YOUR FOOTPRINT</span></div><h2>Every unit<br />makes a difference.</h2><p>Energy awareness is the first step toward a more efficient home.</p><div className="impact-bottom"><span><Sparkles size={15} /> {Number(report?.total_units ?? 0).toFixed(2)} kWh tracked</span><span className="impact-decoration"><i /><i /><i /><i /><i /></span></div><small className="impact-disclaimer">Environmental conversion factors will be configurable in a later milestone.</small></article>
            </section>
          </>}
          <footer className="page-footer"><span>© 2026 SmartVolt · Prepaid energy, simplified</span><span><i /> API-connected demo</span></footer>
        </div>
      </main>

      {showRecharge && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setShowRecharge(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="recharge-title"><div className="modal-heading"><div className="modal-icon"><Wallet size={20} /></div><button className="close-modal" onClick={() => setShowRecharge(false)} aria-label="Close">×</button></div><h2 id="recharge-title">Top up your meter</h2><p>This adds demo credit to room {meter?.room_id}. No real payment is processed.</p><form onSubmit={submitRecharge}><label htmlFor="recharge-amount">Recharge amount (₹)</label><div className="amount-input"><span>₹</span><input id="recharge-amount" inputMode="decimal" type="number" min="1" step="0.01" required value={rechargeAmount} onChange={(event) => setRechargeAmount(event.target.value)} /></div><label htmlFor="user-id">Resident user ID</label><input id="user-id" className="form-input" type="number" min="1" required value={userId} onChange={(event) => setUserId(event.target.value)} /><div className="amount-presets">{['100', '200', '500'].map((amount) => <button type="button" key={amount} className={rechargeAmount === amount ? 'picked' : ''} onClick={() => setRechargeAmount(amount)}>₹{amount}</button>)}</div><button className="button primary full-width submit-recharge" type="submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Plus size={17} />} Confirm demo recharge</button><div className="secure-note"><ShieldCheck size={14} /> Simulated transaction · No payment gateway connected</div></form></section></div>}
    </div>
  )
}
