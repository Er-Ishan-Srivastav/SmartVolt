import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Activity, ArrowDownLeft, ArrowRight, ArrowUpRight,
  BatteryCharging, Bell, Check, ChevronDown, CircleHelp, Clock3,
  CreditCard, Download, FileClock, Filter, Gauge, Home, LayoutDashboard, Leaf,
  LifeBuoy, LoaderCircle, Menu, Moon, Plus, Power, ReceiptText, Search,
  Settings, ShieldCheck, Sparkles, Sun, TrendingUp,
  Wallet, X, Zap, type LucideIcon,
} from 'lucide-react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

type Meter = {
  id: number; room_id: number; current_balance: string; power_status: boolean;
  tariff_per_kwh: string; created_at: string
}
type DailyUsage = { date: string; units_used: string; cost: string }
type UsageReport = {
  meter_id: number; period: '1d' | '7d' | '30d'; total_units: string;
  total_cost: string; reading_count: number; daily: DailyUsage[]
}
type Recharge = {
  id: number; meter_id?: number; user_id: number; amount: string;
  status: string; created_at: string
}
type Reading = { id: number; meter_id: number; units_used: string; cost: string; balance_after: string; created_at: string }
type Ticket = { id: number; user_id: number; issue_type: string; description: string; status: string; created_at: string }
type ApiError = { detail?: string }
type PageKey = 'overview' | 'usage' | 'transactions' | 'rooms' | 'settings' | 'support'
type Theme = 'dark' | 'light'
type Notice = { type: 'success' | 'error' | 'info'; text: string }

const pageMeta: Record<PageKey, { label: string; title: string; description: string; icon: LucideIcon }> = {
  overview: { label: 'Overview', title: 'Your energy, at a glance', description: 'A live look at your prepaid meter and room consumption.', icon: LayoutDashboard },
  usage: { label: 'Usage history', title: 'Consumption analytics', description: 'Explore patterns, compare time ranges, and inspect meter readings.', icon: Activity },
  transactions: { label: 'Transactions', title: 'Wallet & transactions', description: 'A clear ledger of the credits added to your meter.', icon: ReceiptText },
  rooms: { label: 'Room details', title: 'Your room & meter', description: 'Review room details, tariff information, and simulated relay status.', icon: Home },
  settings: { label: 'Settings', title: 'Workspace preferences', description: 'Personalize the SmartVolt experience on this device.', icon: Settings },
  support: { label: 'Help & support', title: 'How can we help?', description: 'Raise a support ticket and keep track of your requests.', icon: LifeBuoy },
}
const routeByPath: Record<string, PageKey> = {
  '/': 'overview', '/overview': 'overview', '/usage': 'usage', '/transactions': 'transactions',
  '/rooms': 'rooms', '/settings': 'settings', '/support': 'support',
}
const routeForPage: Record<PageKey, string> = {
  overview: '/overview', usage: '/usage', transactions: '/transactions', rooms: '/rooms', settings: '/settings', support: '/support',
}
const money = (value: string | number) => new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 2,
}).format(Number(value || 0))
const dateShort = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
const dateTime = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const greeting = () => {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

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

function pageFromLocation(): PageKey {
  return routeByPath[window.location.pathname.replace(/\/$/, '') || '/'] ?? 'overview'
}

function Metric({ label, value, detail, icon: Icon, tone, trend }: {
  label: string; value: string; detail: string; icon: LucideIcon; tone: string; trend?: 'up' | 'down'
}) {
  return <article className="metric-card surface-card">
    <div className="metric-head"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={18} /></span></div>
    <div className="metric-value">{value}</div>
    <div className="metric-detail">{trend && <span className={`trend-chip ${trend}`}><TrendingUp size={12} /> {trend === 'up' ? 'Live' : 'Tracked'}</span>}{detail}</div>
  </article>
}

function SectionHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>
}

function EmptyState({ icon: Icon, title, description, action }: { icon: LucideIcon; title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Icon size={23} /></span><h3>{title}</h3><p>{description}</p>{action}</div>
}

export default function App() {
  const [page, setPage] = useState<PageKey>(() => pageFromLocation())
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('smartvolt:theme') as Theme) || 'dark')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [meters, setMeters] = useState<Meter[]>([])
  const [meter, setMeter] = useState<Meter | null>(null)
  const [report, setReport] = useState<UsageReport | null>(null)
  const [recharges, setRecharges] = useState<Recharge[]>([])
  const [readings, setReadings] = useState<Reading[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [period, setPeriod] = useState<'1d' | '7d' | '30d'>('7d')
  const [chartMetric, setChartMetric] = useState<'units' | 'cost'>('units')
  const [loading, setLoading] = useState(true)
  const [apiConnected, setApiConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showRecharge, setShowRecharge] = useState(false)
  const [rechargeAmount, setRechargeAmount] = useState('200')
  const [userId, setUserId] = useState(() => localStorage.getItem('smartvolt:userId') || '2')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [transactionSearch, setTransactionSearch] = useState('')
  const [transactionFilter, setTransactionFilter] = useState('ALL')
  const [ticketType, setTicketType] = useState('Meter or power issue')
  const [ticketDescription, setTicketDescription] = useState('')
  const [submittingTicket, setSubmittingTicket] = useState(false)
  const [lowBalanceAlert, setLowBalanceAlert] = useState(() => localStorage.getItem('smartvolt:lowBalance') !== 'false')

  const navigate = useCallback((nextPage: PageKey) => {
    const nextPath = routeForPage[nextPage]
    if (window.location.pathname !== nextPath) window.history.pushState({}, '', nextPath)
    setPage(nextPage)
    setMobileNavOpen(false)
    setNotice(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const onPopState = () => { setPage(pageFromLocation()); setMobileNavOpen(false) }
    window.addEventListener('popstate', onPopState)
    if (window.location.pathname === '/') window.history.replaceState({}, '', '/overview')
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    localStorage.setItem('smartvolt:theme', theme)
    document.documentElement.dataset.theme = theme
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    if (themeColor) themeColor.content = theme === 'dark' ? '#0a111c' : '#f3f6fa'
  }, [theme])

  useEffect(() => { localStorage.setItem('smartvolt:userId', userId) }, [userId])
  useEffect(() => { localStorage.setItem('smartvolt:lowBalance', String(lowBalanceAlert)) }, [lowBalanceAlert])

  const loadMeters = useCallback(async () => {
    setLoading(true)
    try {
      const items = await api<Meter[]>('/meters')
      setMeters(items)
      setMeter((current) => items.find((item) => item.id === current?.id) ?? items[0] ?? null)
      setApiConnected(true)
      if (!items.length) setNotice({ type: 'info', text: 'No meters found. Apply migrations and seed the demo data.' })
    } catch (error) {
      setApiConnected(false)
      setNotice({ type: 'error', text: `${(error as Error).message}. Start the FastAPI service and try again.` })
    } finally { setLoading(false) }
  }, [])

  const loadDetails = useCallback(async (meterId: number, selectedPeriod: '1d' | '7d' | '30d') => {
    const [freshMeter, freshReport, history, meterReadings] = await Promise.all([
      api<Meter>(`/meters/${meterId}`),
      api<UsageReport>(`/meters/${meterId}/report?period=${selectedPeriod}`),
      api<Recharge[]>(`/meters/${meterId}/recharges?limit=200`),
      api<Reading[]>(`/meters/${meterId}/readings?limit=200`),
    ])
    setMeter(freshMeter); setReport(freshReport); setRecharges(history); setReadings(meterReadings); setApiConnected(true)
  }, [])

  const loadTickets = useCallback(async () => {
    try { setTickets(await api<Ticket[]>(`/users/${Number(userId)}/tickets?limit=100`)) }
    catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
  }, [userId])

  useEffect(() => { void loadMeters() }, [loadMeters])
  useEffect(() => {
    if (!meter?.id) return
    let active = true
    loadDetails(meter.id, period).catch((error: Error) => {
      if (active) { setApiConnected(false); setNotice({ type: 'error', text: error.message }) }
    })
    return () => { active = false }
  }, [meter?.id, period, loadDetails])
  useEffect(() => { if (page === 'support' && userId) void loadTickets() }, [page, userId, loadTickets])

  const chartData = useMemo(() => (report?.daily ?? []).map((item) => ({
    date: dateShort(item.date), units: Number(item.units_used), cost: Number(item.cost),
  })), [report])
  const averageDaily = report && chartData.length ? Number(report.total_units) / chartData.length : 0
  const filteredTransactions = useMemo(() => recharges.filter((item) => {
    const matchesFilter = transactionFilter === 'ALL' || item.status.toUpperCase() === transactionFilter
    const term = transactionSearch.trim().toLowerCase()
    return matchesFilter && (!term || `wallet recharge ${item.id} ${item.user_id} ${item.status} ${item.amount}`.toLowerCase().includes(term))
  }), [recharges, transactionFilter, transactionSearch])
  const totalRecharge = useMemo(() => recharges.filter((item) => item.status.toUpperCase() === 'SUCCESSFUL').reduce((sum, item) => sum + Number(item.amount), 0), [recharges])

  async function refresh() {
    if (!meter) return
    try { await loadDetails(meter.id, period) }
    catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
  }

  async function togglePower() {
    if (!meter) return
    setBusy(true); setNotice(null)
    try {
      const updated = await api<Meter>(`/meters/${meter.id}/power`, { method: 'PATCH', body: JSON.stringify({ power_status: !meter.power_status }) })
      setMeter(updated); setNotice({ type: 'success', text: `Room power turned ${updated.power_status ? 'on' : 'off'}.` })
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setBusy(false) }
  }

  async function submitRecharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!meter) return
    setBusy(true); setNotice(null)
    try {
      await api<Recharge>(`/meters/${meter.id}/recharges`, {
        method: 'POST', body: JSON.stringify({ user_id: Number(userId), amount: rechargeAmount, idempotency_key: crypto.randomUUID() }),
      })
      setShowRecharge(false); setNotice({ type: 'success', text: 'Demo recharge added to the meter wallet.' }); await refresh()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setBusy(false) }
  }

  async function submitTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSubmittingTicket(true); setNotice(null)
    try {
      await api<Ticket>('/tickets', { method: 'POST', body: JSON.stringify({ user_id: Number(userId), issue_type: ticketType, description: ticketDescription }) })
      setTicketDescription(''); setNotice({ type: 'success', text: 'Support ticket created. Your request is now in the ticket list.' }); await loadTickets()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSubmittingTicket(false) }
  }

  const navGroups: { title: string; items: PageKey[] }[] = [
    { title: 'Workspace', items: ['overview', 'usage', 'transactions', 'rooms'] },
    { title: 'Manage', items: ['settings', 'support'] },
  ]
  const activeMeta = pageMeta[page]

  const pageIntro = (eyebrow: string, title: string, description: string, actions?: ReactNode) => <div className="page-intro">
    <div className="intro-copy"><div className="eyebrow"><Sparkles size={14} /> {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
    {actions && <div className="intro-actions">{actions}</div>}
  </div>


  return <div className="app-shell" data-theme={theme}>
    <aside className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
      <a className="brand" href="/overview" onClick={(event) => { event.preventDefault(); navigate('overview') }}>
        <span className="brand-mark"><Zap size={22} fill="currentColor" /></span><span className="brand-copy"><strong>smartvolt<span>.</span></strong><small>ENERGY, MADE CLEAR</small></span>
      </a>
      <div className="workspace-switcher"><span className="workspace-avatar">S</span><span><strong>Resident workspace</strong><small>Personal meter</small></span><ChevronDown size={15} /></div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        {navGroups.map((group) => <div className="nav-group" key={group.title}><span className="side-caption">{group.title}</span>{group.items.map((key) => {
          const item = pageMeta[key]; const Icon = item.icon
          return <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => navigate(key)} aria-current={page === key ? 'page' : undefined}>
            <Icon size={18} strokeWidth={1.9} /><span>{item.label}</span>{key === 'transactions' && recharges.length > 0 && <span className="nav-count">{Math.min(recharges.length, 99)}</span>}
          </button>
        })}</div>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="eco-promo"><span className="eco-promo-icon"><Leaf size={18} /></span><strong>Make energy count</strong><p>Small changes create a more efficient home.</p><div className="eco-chart" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/></div><button onClick={() => navigate('usage')}>Explore your usage <ArrowRight size={13} /></button></div>
      <div className="sidebar-bottom"><div className="sidebar-divider" /><button className="nav-item" onClick={() => navigate('support')}><CircleHelp size={18}/><span>Help center</span></button><div className="profile-row"><div className="avatar">IS</div><div className="profile-copy"><strong>Ishan Srivastav</strong><small>Resident · Demo account</small></div><button className="icon-ghost" aria-label="Open settings" onClick={() => navigate('settings')}><Settings size={16}/></button></div></div>
    </aside>
    {mobileNavOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}

    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileNavOpen(true)}><Menu size={19}/></button><div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{activeMeta.label}</strong></div></div>
        <div className="topbar-right"><span className={`system-status ${apiConnected ? 'connected' : 'disconnected'}`}><i />{apiConnected ? 'API connected' : 'API offline'}</span><span className="topbar-date"><Clock3 size={15}/>{new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span><button className="theme-toggle" onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'day' : 'night'} mode`} title={`Switch to ${theme === 'dark' ? 'day' : 'night'} mode`}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}<span>{theme === 'dark' ? 'Day mode' : 'Night mode'}</span></button><button className="avatar mini" aria-label="Account settings" onClick={() => navigate('settings')}>IS</button></div>
      </header>

      <div className="page-content page-enter" key={page}>
        {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.type === 'success' ? <Check size={17}/> : notice.type === 'error' ? <CircleHelp size={17}/> : <Bell size={17}/>} {notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={15}/></button></div>}

        {page === 'overview' && <>
          {pageIntro('YOUR ENERGY OVERVIEW', `${greeting()}, Ishan`, 'Here’s your room’s electricity snapshot for today.', <><label className="meter-select"><span>Meter</span><select value={meter?.id ?? ''} onChange={(event) => setMeter(meters.find((item) => item.id === Number(event.target.value)) ?? null)} aria-label="Select meter">{meters.map((item) => <option value={item.id} key={item.id}>Room {item.room_id} · #{item.id}</option>)}</select><ChevronDown size={14}/></label><button className="button primary" onClick={() => setShowRecharge(true)} disabled={!meter}><Plus size={16}/> Add money</button></>)}
          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={23}/> Connecting to SmartVolt…</div> : !meter ? <EmptyState icon={BatteryCharging} title="No meter connected yet" description="Seed the local database to create the demo room and meter." action={<code>python -m app.db.seed</code>}/> : <>
            {lowBalanceAlert && Number(meter.current_balance) < 150 && <div className="inline-alert"><span className="alert-icon"><Bell size={16}/></span><span><strong>Balance running low</strong><small>Your balance is below ₹150. Top up now to avoid an unexpected power cut.</small></span><button className="text-button" onClick={() => setShowRecharge(true)}>Recharge <ArrowRight size={14}/></button><button className="alert-close" onClick={() => setLowBalanceAlert(false)} aria-label="Dismiss"><X size={15}/></button></div>}
            <section className="metric-grid"><Metric label="Available balance" value={money(meter.current_balance)} detail={Number(meter.current_balance) > 0 ? 'Ready for consumption' : 'Recharge required'} icon={Wallet} tone="mint"/><Metric label="Energy consumed" value={`${Number(report?.total_units ?? 0).toFixed(2)} kWh`} detail={`${report?.reading_count ?? 0} readings · ${period === '1d' ? 'Today' : period === '7d' ? 'Last 7 days' : 'Last 30 days'}`} icon={Zap} tone="violet" trend="up"/><Metric label="Estimated cost" value={money(report?.total_cost ?? 0)} detail={`${money(meter.tariff_per_kwh)} per kWh`} icon={ReceiptText} tone="amber"/><Metric label="Room power" value={meter.power_status ? 'Enabled' : 'Disabled'} detail="Software relay simulation" icon={Power} tone={meter.power_status ? 'mint' : 'rose'}/></section>
            <section className="dashboard-grid"><article className="panel surface-card analytics-panel"><SectionHeading title="Consumption analytics" description="Understand where your energy goes." action={<PeriodControl period={period} setPeriod={setPeriod}/>}/><div className="chart-summary"><div><span className="chart-legend"><i/> Energy used</span><strong>{Number(report?.total_units ?? 0).toFixed(2)} <small>kWh</small></strong></div><span className="chart-average">Daily avg. {averageDaily.toFixed(2)} kWh</span></div><div className="chart-wrap">{chartData.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 10, right: 8, left: -20, bottom: 0 }}><defs><linearGradient id="usageFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={0.24}/><stop offset="100%" stopColor="var(--accent)" stopOpacity={0.015}/></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="4 6"/><XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} dy={8}/><YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }}/><Tooltip formatter={(value) => [`${Number(value).toFixed(3)} kWh`, 'Energy used']} contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--border)', borderRadius: 12, color: 'var(--text)' }}/><Area type="monotone" dataKey="units" stroke="var(--accent)" strokeWidth={2.5} fill="url(#usageFill)" activeDot={{ r: 5, strokeWidth: 0 }}/></AreaChart></ResponsiveContainer> : <div className="chart-empty"><Activity size={25}/><span>No consumption readings in this period yet.</span><small>Record a simulated reading to see the trend.</small></div>}</div><div className="chart-footer"><span><ShieldCheck size={15}/> Stored in the database</span><button className="text-button" onClick={() => navigate('usage')}>Full usage report <ArrowUpRight size={14}/></button></div></article>
              <MeterStatusCard meter={meter} busy={busy} onToggle={togglePower}/></section>
            <section className="bottom-grid"><article className="panel surface-card"><SectionHeading title="Recent transactions" description="Your latest wallet activity." action={<button className="text-button" onClick={() => navigate('transactions')}>View all <ArrowUpRight size={14}/></button>}/>{recharges.length ? <TransactionList items={recharges.slice(0, 4)}/> : <div className="mini-empty"><Wallet size={22}/><span>No recharges yet</span><button onClick={() => setShowRecharge(true)}>Add your first recharge</button></div>}</article><article className="impact-card"><div className="impact-orb"/><div className="impact-top"><span className="impact-icon"><Leaf size={19}/></span><span className="impact-label">YOUR FOOTPRINT</span></div><h2>Better habits.<br/>Lighter footprint.</h2><p>Awareness is the first step toward a more efficient home. Keep tracking every unit.</p><div className="impact-bottom"><span><Sparkles size={15}/> {Number(report?.total_units ?? 0).toFixed(2)} kWh tracked</span><span className="impact-decoration"><i/><i/><i/><i/><i/></span></div><small className="impact-disclaimer">Environmental factors are a future configuration.</small></article></section>
          </>}
        </>}

        {page === 'usage' && <>
          {pageIntro('ENERGY INTELLIGENCE', 'Consumption analytics', 'Explore your energy history across daily, weekly, and monthly periods.', <PeriodControl period={period} setPeriod={setPeriod}/>)}
          {!meter ? <EmptyState icon={Gauge} title="No meter available" description="Connect a meter to start collecting energy history."/> : <>
            <section className="metric-grid three-metrics"><Metric label="Total consumption" value={`${Number(report?.total_units ?? 0).toFixed(3)} kWh`} detail={`${report?.reading_count ?? 0} readings in period`} icon={Zap} tone="violet"/><Metric label="Estimated spend" value={money(report?.total_cost ?? 0)} detail={`Tariff: ${money(meter.tariff_per_kwh)}/kWh`} icon={CreditCard} tone="mint"/><Metric label="Daily average" value={`${averageDaily.toFixed(3)} kWh`} detail="Average for days with data" icon={TrendingUp} tone="amber"/></section>
            <article className="panel surface-card usage-detail-panel"><SectionHeading title="Energy over time" description="Switch between consumption and estimated cost." action={<div className="view-toggle"><button className={chartMetric === 'units' ? 'active' : ''} onClick={() => setChartMetric('units')}>Units (kWh)</button><button className={chartMetric === 'cost' ? 'active' : ''} onClick={() => setChartMetric('cost')}>Cost (₹)</button></div>}/><div className="usage-chart-summary"><div><span className="chart-legend"><i/>{chartMetric === 'units' ? 'Daily consumption' : 'Daily estimated cost'}</span><strong>{chartMetric === 'units' ? `${Number(report?.total_units ?? 0).toFixed(3)} kWh` : money(report?.total_cost ?? 0)}</strong></div><span className="period-pill">{period === '1d' ? 'Today' : period === '7d' ? 'Last 7 days' : 'Last 30 days'}</span></div><div className="usage-chart">{chartData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 12, right: 12, left: -14, bottom: 0 }} barCategoryGap="34%"><CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="4 6"/><XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} dy={9}/><YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }}/><Tooltip formatter={(value) => chartMetric === 'units' ? [`${Number(value).toFixed(3)} kWh`, 'Consumption'] : [money(Number(value)), 'Estimated cost']} contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--border)', borderRadius: 12, color: 'var(--text)' }}/><Bar dataKey={chartMetric} fill="var(--accent)" radius={[6, 6, 2, 2]} maxBarSize={38}/></BarChart></ResponsiveContainer> : <div className="chart-empty"><Activity size={25}/><span>Not enough data to display a trend yet.</span><small>Use the simulator worker or record readings through the API.</small></div>}</div></article>
            <article className="panel surface-card table-panel"><SectionHeading title="Latest meter readings" description="Individual usage events recorded by the simulator." action={<span className="count-label">{readings.length} records loaded</span>}/>{readings.length ? <div className="table-scroll"><table><thead><tr><th>Reading</th><th>Timestamp</th><th>Units used</th><th>Cost</th><th>Balance after</th></tr></thead><tbody>{readings.slice(0, 20).map((reading) => <tr key={reading.id}><td><span className="record-id">#{String(reading.id).padStart(4, '0')}</span></td><td>{dateTime(reading.created_at)}</td><td>{Number(reading.units_used).toFixed(3)} kWh</td><td>{money(reading.cost)}</td><td className="strong-cell">{money(reading.balance_after)}</td></tr>)}</tbody></table></div> : <EmptyState icon={FileClock} title="No readings recorded" description="Once the simulator records consumption, individual meter events will appear here."/>}</article>
          </>}
        </>}

        {page === 'transactions' && <>
          {pageIntro('WALLET ACTIVITY', 'Wallet & transactions', 'Review every simulated recharge and keep your wallet history transparent.', <button className="button primary" onClick={() => setShowRecharge(true)} disabled={!meter}><Plus size={16}/> Add money</button>)}
          <section className="metric-grid three-metrics"><Metric label="Current balance" value={money(meter?.current_balance ?? 0)} detail="Available to consume" icon={Wallet} tone="mint"/><Metric label="Successful credits" value={money(totalRecharge)} detail="Across loaded history" icon={ArrowDownLeft} tone="violet"/><Metric label="Recharge count" value={String(recharges.length)} detail={`${recharges.filter((item) => item.status.toUpperCase() === 'SUCCESSFUL').length} successful`} icon={ReceiptText} tone="amber"/></section>
          <article className="panel surface-card table-panel transaction-table-panel"><SectionHeading title="Transaction history" description="Search by transaction ID, resident, or status." action={<button className="button secondary" onClick={() => { const rows = [['Transaction ID','Date','Resident ID','Amount','Status'], ...filteredTransactions.map((item) => [String(item.id), dateTime(item.created_at), String(item.user_id), item.amount, item.status])]; const csv = rows.map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n'); const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' })); link.download = 'smartvolt-transactions.csv'; link.click(); URL.revokeObjectURL(link.href) }}><Download size={15}/> Export CSV</button>}/><div className="table-toolbar"><label className="search-field"><Search size={16}/><input placeholder="Search transactions…" value={transactionSearch} onChange={(event) => setTransactionSearch(event.target.value)}/></label><label className="filter-select"><Filter size={15}/><select value={transactionFilter} onChange={(event) => setTransactionFilter(event.target.value)} aria-label="Filter transaction status"><option value="ALL">All statuses</option><option value="SUCCESSFUL">Successful</option><option value="FAILED">Failed</option></select><ChevronDown size={14}/></label></div>
            {filteredTransactions.length ? <div className="table-scroll"><table><thead><tr><th>Transaction</th><th>Date & time</th><th>Resident</th><th>Amount</th><th>Status</th></tr></thead><tbody>{filteredTransactions.map((item) => <tr key={item.id}><td><div className="table-title-cell"><span className="table-icon"><ArrowDownLeft size={16}/></span><span><strong>Wallet recharge</strong><small>TXN-{String(item.id).padStart(5, '0')}</small></span></div></td><td>{dateTime(item.created_at)}</td><td><span className="resident-pill">IS</span> User #{item.user_id}</td><td className="amount-positive">+{money(item.amount)}</td><td><span className={`status-badge ${item.status.toLowerCase()}`}><i/>{item.status.toLowerCase()}</span></td></tr>)}</tbody></table></div> : <EmptyState icon={ReceiptText} title="No matching transactions" description={recharges.length ? 'Try changing your search or status filter.' : 'Your wallet activity will appear after your first demo recharge.'} action={!recharges.length ? <button className="button primary" onClick={() => setShowRecharge(true)}><Plus size={15}/> Add money</button> : undefined}/>}
            <div className="table-footer"><span>Showing <strong>{filteredTransactions.length}</strong> of <strong>{recharges.length}</strong> loaded transactions</span><span><ShieldCheck size={14}/> Simulated payments only</span></div>
          </article>
        </>}

        {page === 'rooms' && <>
          {pageIntro('ROOM CONFIGURATION', 'Your room & meter', 'Control your simulated relay and review the meter currently assigned to your room.', <button className="button secondary" onClick={() => void loadMeters()}><Activity size={15}/> Refresh meters</button>)}
          {!meter ? <EmptyState icon={Home} title="No room linked" description="Seed the database to create the demo room and meter."/> : <>
            <div className="room-hero surface-card"><div className="room-hero-copy"><span className="room-tag"><Home size={13}/> RESIDENT SPACE</span><h2>Room {meter.room_id}</h2><p>Your room is linked to SmartVolt meter <strong>#{String(meter.id).padStart(3, '0')}</strong>. Power changes on this page are simulated in software.</p><div className="room-hero-meta"><span><i className="online-dot"/> Meter {apiConnected ? 'connected' : 'offline'}</span><span><ShieldCheck size={14}/> Prepaid meter</span></div></div><div className={`room-power-visual ${meter.power_status ? 'powered' : 'unpowered'}`}><div className="power-orbit orbit-a"/><div className="power-orbit orbit-b"/><div className="power-visual-core"><Zap size={36} fill="currentColor"/><small>SMART METER</small><strong>#{String(meter.id).padStart(3, '0')}</strong></div><span className="power-visual-state"><i/>{meter.power_status ? 'Power enabled' : 'Power disabled'}</span></div></div>
            <section className="room-detail-grid"><article className="panel surface-card"><SectionHeading title="Meter details" description="Current meter configuration."/><div className="detail-list"><DetailRow icon={Gauge} label="Meter ID" value={`SV-${String(meter.id).padStart(4, '0')}`}/><DetailRow icon={Home} label="Assigned room" value={`Room ${meter.room_id}`}/><DetailRow icon={CreditCard} label="Energy tariff" value={`${money(meter.tariff_per_kwh)} / kWh`}/><DetailRow icon={Wallet} label="Available balance" value={money(meter.current_balance)}/><DetailRow icon={Clock3} label="Created on" value={dateTime(meter.created_at)}/></div></article><article className="panel surface-card relay-panel"><SectionHeading title="Power relay" description="A digital representation of room power."/><div className={`relay-status-banner ${meter.power_status ? 'enabled' : 'disabled'}`}><span className="relay-status-icon"><Power size={20}/></span><div><strong>{meter.power_status ? 'Power is enabled' : 'Power is disabled'}</strong><small>{meter.power_status ? 'Your simulated room relay is currently on.' : 'The simulated relay is off. Turn it on when ready.'}</small></div><span className="relay-led"><i/></span></div><div className="relay-large-control"><span className={`relay-switch ${meter.power_status ? 'on' : ''}`}><i/></span><div className="relay-control-copy"><strong>Room power</strong><small>{meter.power_status ? 'Currently on' : 'Currently off'}</small></div><button className={`button ${meter.power_status ? 'danger-quiet' : 'primary'}`} onClick={togglePower} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)}>{busy ? <LoaderCircle size={15} className="spin"/> : <Power size={15}/>} Turn {meter.power_status ? 'off' : 'on'}</button></div><p className="disclaimer-note"><ShieldCheck size={14}/> Software simulation only. No physical electrical relay is connected.</p></article></section>
            <article className="panel surface-card room-activity"><SectionHeading title="Recent room activity" description="Latest events recorded against this meter." action={<button className="text-button" onClick={() => navigate('usage')}>Usage history <ArrowUpRight size={14}/></button>}/><div className="activity-list"><div className="activity-item"><span className="activity-icon mint"><Check size={16}/></span><span><strong>Meter initialized</strong><small>{dateTime(meter.created_at)}</small></span><span className="activity-status">Registered</span></div>{readings.slice(0, 4).map((reading) => <div className="activity-item" key={reading.id}><span className="activity-icon violet"><Zap size={16}/></span><span><strong>Energy consumption recorded</strong><small>{dateTime(reading.created_at)} · {Number(reading.units_used).toFixed(3)} kWh</small></span><span className="activity-status">-{money(reading.cost)}</span></div>)}{recharges.slice(0, 3).map((item) => <div className="activity-item" key={`r-${item.id}`}><span className="activity-icon amber"><ArrowDownLeft size={16}/></span><span><strong>Wallet recharged</strong><small>{dateTime(item.created_at)} · User #{item.user_id}</small></span><span className="activity-status positive">+{money(item.amount)}</span></div>)}</div></article>
          </>}
        </>}

        {page === 'settings' && <>
          {pageIntro('PREFERENCES', 'Workspace preferences', 'Adjust how SmartVolt looks and how it keeps you informed.', <span className="saved-indicator"><Check size={14}/> Preferences save automatically</span>)}
          <div className="settings-layout"><div className="settings-main"><article className="panel surface-card settings-panel"><SectionHeading title="Appearance" description="Choose an interface that works best for you."/><div className="theme-options"><button className={`theme-option ${theme === 'light' ? 'selected' : ''}`} onClick={() => setTheme('light')}><span className="theme-preview light-preview"><i/><i/><i/><b/></span><span><strong>Day mode</strong><small>Clean, bright workspace</small></span><span className="radio-dot"/></button><button className={`theme-option ${theme === 'dark' ? 'selected' : ''}`} onClick={() => setTheme('dark')}><span className="theme-preview dark-preview"><i/><i/><i/><b/></span><span><strong>Night mode</strong><small>Low-light, focused workspace</small></span><span className="radio-dot"/></button></div></article><article className="panel surface-card settings-panel"><SectionHeading title="Notifications" description="Choose which in-app reminders you want to see."/><div className="setting-row"><span className="setting-icon amber"><Bell size={17}/></span><span className="setting-copy"><strong>Low balance warning</strong><small>Show a reminder when the meter balance drops below ₹150.</small></span><button className={`switch-control ${lowBalanceAlert ? 'on' : ''}`} role="switch" aria-checked={lowBalanceAlert} aria-label="Low balance warning" onClick={() => setLowBalanceAlert((value) => !value)}><i/></button></div><div className="setting-row"><span className="setting-icon mint"><Activity size={17}/></span><span className="setting-copy"><strong>Live API status</strong><small>Display the connection state in the top navigation.</small></span><span className={`status-badge ${apiConnected ? 'successful' : 'failed'}`}><i/>{apiConnected ? 'Enabled' : 'Offline'}</span></div></article></div><aside className="settings-aside"><article className="panel surface-card account-card"><span className="account-avatar">IS</span><span className="account-type">DEMO ACCOUNT</span><h3>Ishan Srivastav</h3><p>Resident workspace</p><div className="account-divider"/><label htmlFor="resident-id">Resident user ID</label><input id="resident-id" className="field-input" type="number" min="1" value={userId} onChange={(event) => setUserId(event.target.value)}/><small className="field-help">Used to associate recharges and support tickets in this demo.</small><button className="button secondary full-width" onClick={() => navigate('support')}><LifeBuoy size={15}/> Get support</button></article><div className="settings-note"><ShieldCheck size={17}/><span><strong>Privacy by design</strong><small>Visual preferences are saved only in this browser. This app is still a simulation and is not connected to a physical meter.</small></span></div></aside></div>
        </>}

        {page === 'support' && <>
          {pageIntro('SUPPORT CENTER', 'How can we help?', 'Let us know what is going on with your meter. Your requests are saved in the demo database.', <span className="support-hours"><i/> Ticketing API available</span>)}
          <div className="support-layout"><article className="panel surface-card ticket-form-panel"><SectionHeading title="Raise a ticket" description="Share a few details and we’ll log the request."/><form className="support-form" onSubmit={submitTicket}><label htmlFor="ticket-type">Issue category</label><div className="select-wrap"><select id="ticket-type" value={ticketType} onChange={(event) => setTicketType(event.target.value)}><option>Meter or power issue</option><option>Balance or recharge</option><option>Incorrect usage data</option><option>Room details</option><option>Other</option></select><ChevronDown size={15}/></div><label htmlFor="ticket-description">Describe the issue</label><textarea id="ticket-description" rows={5} required minLength={5} maxLength={5000} placeholder="Tell us what happened and when you first noticed it…" value={ticketDescription} onChange={(event) => setTicketDescription(event.target.value)}/><div className="form-helper"><span>{ticketDescription.length}/5000 characters</span><span><ShieldCheck size={13}/> Saved to the demo database</span></div><button className="button primary full-width" type="submit" disabled={submittingTicket || !ticketDescription.trim()}>{submittingTicket ? <LoaderCircle size={16} className="spin"/> : <Plus size={16}/>} Submit support ticket</button></form></article><aside className="support-aside"><div className="support-help-card"><span className="support-illustration"><LifeBuoy size={26}/></span><h3>Need a hand?</h3><p>Include the affected meter ID and any relevant details so the issue is easy to understand.</p><div><span><Clock3 size={15}/> Ticket ID generated automatically</span><span><ShieldCheck size={15}/> Tracked in your workspace</span></div></div><article className="panel surface-card support-stat"><div><span>YOUR REQUESTS</span><strong>{tickets.length}</strong><small>Total support tickets</small></div><span className="metric-icon violet"><FileClock size={19}/></span></article></aside></div>
          <article className="panel surface-card table-panel support-tickets-panel"><SectionHeading title="Your support tickets" description="Requests associated with the resident ID in Settings." action={<button className="button secondary" onClick={() => void loadTickets()}><Activity size={15}/> Refresh</button>}/>{tickets.length ? <div className="ticket-list">{tickets.map((ticket) => <div className="ticket-row" key={ticket.id}><span className="ticket-type-icon"><LifeBuoy size={17}/></span><span className="ticket-copy"><strong>{ticket.issue_type}</strong><small>Ticket #{String(ticket.id).padStart(4, '0')} · {dateTime(ticket.created_at)}</small><p>{ticket.description}</p></span><span className={`status-badge ${ticket.status.toLowerCase()}`}><i/>{ticket.status.toLowerCase()}</span></div>)}</div> : <EmptyState icon={FileClock} title="No support tickets yet" description="Anything you submit through the form will appear here."/>}</article>
        </>}

        <footer className="page-footer"><span>© 2026 SmartVolt <span className="footer-separator">·</span> Prepaid energy, simplified</span><span><i className={apiConnected ? 'connected' : ''}/> {apiConnected ? 'Connected to your demo API' : 'Waiting for API connection'}</span></footer>
      </div>
    </main>

    {showRecharge && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setShowRecharge(false)}><section className="modal surface-card" role="dialog" aria-modal="true" aria-labelledby="recharge-title"><div className="modal-heading"><div className="modal-icon"><Wallet size={21}/></div><button className="close-modal icon-button" onClick={() => setShowRecharge(false)} aria-label="Close"><X size={18}/></button></div><span className="modal-kicker">METER WALLET</span><h2 id="recharge-title">Top up your meter</h2><p>This adds simulated credit to room {meter?.room_id}. No real payment is processed.</p><form onSubmit={submitRecharge}><label htmlFor="recharge-amount">Recharge amount</label><div className="amount-input"><span>₹</span><input id="recharge-amount" inputMode="decimal" type="number" min="1" max="100000" step="0.01" required value={rechargeAmount} onChange={(event) => setRechargeAmount(event.target.value)}/></div><div className="amount-presets">{['100','200','500','1000'].map((amount) => <button type="button" key={amount} className={rechargeAmount === amount ? 'picked' : ''} onClick={() => setRechargeAmount(amount)}>₹{amount}</button>)}</div><label htmlFor="modal-user-id">Resident user ID</label><input id="modal-user-id" className="field-input modal-user-input" type="number" min="1" required value={userId} onChange={(event) => setUserId(event.target.value)}/><button className="button primary full-width submit-recharge" type="submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <Plus size={17}/>} Confirm demo recharge <ArrowRight size={15}/></button><div className="secure-note"><ShieldCheck size={14}/> Simulated transaction · No payment gateway connected</div></form></section></div>}
  </div>
}

function PeriodControl({ period, setPeriod }: { period: '1d' | '7d' | '30d'; setPeriod: (value: '1d' | '7d' | '30d') => void }) {
  return <div className="period-control" role="group" aria-label="Report period">{(['1d','7d','30d'] as const).map((item) => <button key={item} className={period === item ? 'selected' : ''} onClick={() => setPeriod(item)}>{item === '1d' ? 'Today' : item === '7d' ? '7 days' : '30 days'}</button>)}</div>
}

function MeterStatusCard({ meter, busy, onToggle }: { meter: Meter; busy: boolean; onToggle: () => void }) {
  return <article className="panel surface-card meter-status-panel"><SectionHeading title="Meter status" description="Software relay overview." action={<span className="live-label"><i/> SIMULATED</span>}/><div className={`meter-illustration ${meter.power_status ? 'is-on' : 'is-off'}`}><div className="meter-glow"/><div className="meter-ring"><div className="meter-core"><Zap size={31} fill="currentColor"/><small>SMART METER</small><strong>#{String(meter.id).padStart(3,'0')}</strong></div></div><span className="meter-decoration dot-one"/><span className="meter-decoration dot-two"/><span className="meter-decoration ring-small"/></div><div className="status-list"><div><span><i className="status-check"><Check size={11}/></i> Connection</span><strong>Connected</strong></div><div><span><i className={`status-circle ${meter.power_status ? 'green' : 'gray'}`}/>Power relay</span><strong>{meter.power_status ? 'Enabled' : 'Disabled'}</strong></div><div><span><i className="status-circle green"/>Meter tariff</span><strong>{money(meter.tariff_per_kwh)} / kWh</strong></div></div><button className={`button ${meter.power_status ? 'secondary' : 'primary'} full-width`} onClick={onToggle} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)}>{busy ? <LoaderCircle size={15} className="spin"/> : <Power size={15}/>} Turn power {meter.power_status ? 'off' : 'on'}</button><p className="panel-note">No physical electrical relay is connected.</p></article>
}

function TransactionList({ items }: { items: Recharge[] }) {
  return <div className="transaction-list">{items.map((item) => <div className="transaction-row" key={item.id}><div className="transaction-icon"><ArrowDownLeft size={17}/></div><div className="transaction-main"><strong>Wallet recharge</strong><small>{dateTime(item.created_at)} · User #{item.user_id}</small></div><div className="transaction-amount"><strong>+{money(item.amount)}</strong><small className={`transaction-status ${item.status.toLowerCase()}`}><i/>{item.status.toLowerCase()}</small></div></div>)}</div>
}

function DetailRow({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return <div className="detail-row"><span className="detail-icon"><Icon size={16}/></span><span className="detail-label">{label}</span><strong>{value}</strong></div>
}
