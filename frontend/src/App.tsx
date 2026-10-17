import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Activity, ArrowDownLeft, ArrowRight, ArrowUpRight,
  BatteryCharging, Bell, Check, ChevronDown, CircleHelp, Clock3, Cpu,
  CreditCard, Download, FileClock, Filter, Gauge, Home, LayoutDashboard, Leaf, LockKeyhole,
  LifeBuoy, LoaderCircle, LogIn, LogOut, Menu, Moon, Plus, Power, ReceiptText, Search, Users,
  Settings, ShieldCheck, Sparkles, Sun, TrendingUp,
  Wallet, X, Zap, type LucideIcon,
} from 'lucide-react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import AdminPage from './components/AdminPage'
import LoadLabPage from './components/LoadLabPage'

type Meter = {
  id: number; meter_code: string; is_active: boolean; room_id: number; current_balance: string; power_status: boolean;
  tariff_per_kwh: string; created_at: string
}
type DailyUsage = { date: string; units_used: string; cost: string }
type HourlyUsage = { hour: number; label: string; units_used: string; cost: string; reading_count: number }
type UsageReport = {
  meter_id: number; period: '1d' | '7d' | '30d'; total_units: string;
  total_cost: string; reading_count: number; daily: DailyUsage[];
  granularity?: 'daily' | 'hourly'; timezone?: string; selected_date?: string | null;
  hourly?: HourlyUsage[]; unallocated_units?: string; unallocated_cost?: string;
  unallocated_reading_count?: number; hourly_data_quality?: 'RESOLVED' | 'COARSE_LEGACY' | 'MIXED' | 'NO_DATA'
  estimated_co2_kg?: string; co2_factor_kg_per_kwh?: string; co2_factor_source?: string
  co2_factor_source_url?: string; tree_years_equivalent?: string; tree_absorption_kg_per_year?: string
  environmental_estimate_note?: string
}
type Recharge = {
  id: number; recharge_code?: string; meter_id?: number; user_id?: number | null; actor_user_id?: number | null; amount: string;
  status: string; created_at: string
}
type Reading = { id: number; meter_id: number; units_used: string; cost: string; balance_after: string; created_at: string }
type BillingStatement = {
  meter_id: number; meter_code: string; room_code: string; room_no: string; month: string
  period_start: string; period_end: string; timezone: string; current_tariff_per_kwh: string
  total_units: string; total_energy_cost: string; total_recharge_amount: string
  reading_count: number; recharge_count: number; opening_balance: string | null; closing_balance: string | null
  estimated_co2_kg: string; co2_factor_kg_per_kwh: string; co2_factor_source: string
  co2_factor_source_url: string; statement_note: string
}
type TicketMessage = { id: number; ticket_id: number; author_user_id: number | null; author_name: string; author_role: 'ADMIN' | 'RESIDENT'; message: string; created_at: string }
type TicketStatus = 'OPEN' | 'IN_PROGRESS' | 'AWAITING_RESIDENT' | 'RESOLVED' | 'CLOSED'
type Ticket = { id: number; ticket_code: string; user_id: number; room_id: number | null; room_code_snapshot: string | null; room_no_snapshot: string | null; visibility: 'ROOM' | 'PRIVATE'; issue_type: string; description: string; status: TicketStatus; priority: 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'; created_at: string; updated_at: string; messages: TicketMessage[]; requester_name?: string; requester_username?: string | null; room_no?: string | null }
type ApiError = { detail?: string }
type PageKey = 'overview' | 'usage' | 'transactions' | 'rooms' | 'simulation' | 'admin' | 'settings' | 'support'
type Account = { id: number; name: string; username: string; role: 'ADMIN' | 'RESIDENT'; room_id: number | null; tenant_code?: string | null; phone?: string | null }
type RoomDirectoryItem = { id: number; room_code: string; is_active: boolean; room_no: string; created_at: string; meter: Meter | null; tenants: Array<{ id: number; tenant_code?: string | null; name: string; username: string | null; phone: string | null; room_id: number | null; role: string; is_active: boolean }> }
type Theme = 'dark' | 'light'
type Notice = { type: 'success' | 'error' | 'info'; text: string }

const pageMeta: Record<PageKey, { label: string; title: string; description: string; icon: LucideIcon }> = {
  overview: { label: 'Overview', title: 'Your energy, at a glance', description: 'A live look at your prepaid meter and room consumption.', icon: LayoutDashboard },
  usage: { label: 'Usage history', title: 'Consumption analytics', description: 'Explore patterns, compare time ranges, and inspect meter readings.', icon: Activity },
  transactions: { label: 'Transactions', title: 'Wallet & transactions', description: 'A clear ledger of the credits added to your meter.', icon: ReceiptText },
  rooms: { label: 'Room details', title: 'Your room & meter', description: 'Review room details, tariff information, and simulated relay status.', icon: Home },
  simulation: { label: 'Load Lab', title: 'Appliance simulation', description: 'Build realistic daily load profiles and watch the prepaid meter respond.', icon: Cpu },
  admin: { label: 'Admin console', title: 'Rooms & residents', description: 'Create rooms, issue tenant accounts, and manage hostel meters.', icon: Users },
  settings: { label: 'Settings', title: 'Workspace preferences', description: 'Personalize the SmartVolt experience on this device.', icon: Settings },
  support: { label: 'Help & support', title: 'How can we help?', description: 'Raise a support ticket and keep track of your requests.', icon: LifeBuoy },
}
const routeByPath: Record<string, PageKey> = {
  '/': 'overview', '/overview': 'overview', '/usage': 'usage', '/transactions': 'transactions',
  '/rooms': 'rooms', '/simulation': 'simulation', '/admin': 'admin', '/settings': 'settings', '/support': 'support',
}
const routeForPage: Record<PageKey, string> = {
  overview: '/overview', usage: '/usage', transactions: '/transactions', rooms: '/rooms', simulation: '/simulation', admin: '/admin', settings: '/settings', support: '/support',
}
const money = (value: string | number) => new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 2,
}).format(Number(value || 0))
const dateShort = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
const dateTime = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const indiaDateString = () => {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}
const indiaMonthString = () => indiaDateString().slice(0, 7)
const escapeHtml = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char] ?? char))
const greeting = () => {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem('smartvolt:accessToken')
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError
    if (response.status === 401 && token && path !== '/auth/login') {
      sessionStorage.removeItem('smartvolt:accessToken')
      sessionStorage.removeItem('smartvolt:account')
      window.dispatchEvent(new Event('smartvolt:auth-expired'))
    }
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

function pageFromLocation(): PageKey {
  return routeByPath[window.location.pathname.replace(/\/$/, '') || '/'] ?? 'overview'
}

function LoginScreen({ busy, error, onSubmit, theme, onThemeChange }: { busy: boolean; error: string; onSubmit: (username: string, password: string) => Promise<void>; theme: Theme; onThemeChange: (theme: Theme) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void onSubmit(username, password)
  }
  return <div className={`auth-screen ${theme === 'light' ? 'auth-screen-light' : ''}`}>
    <div className="auth-screen-top"><a className="brand auth-brand" href="/overview"><span className="brand-mark"><Zap size={25} fill="currentColor"/></span><span><strong>smartvolt.</strong><small>ENERGY, MADE CLEAR.</small></span></a><button className="theme-toggle" onClick={() => onThemeChange(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={16}/> : <Moon size={16}/>}<span>{theme === 'dark' ? 'Day mode' : 'Night mode'}</span></button></div>
    <div className="auth-content"><div className="auth-copy"><div className="eyebrow"><ShieldCheck size={14}/> SECURE ENERGY WORKSPACE</div><h1>Power your space.<br/><span>Stay in control.</span></h1><p>Sign in to your SmartVolt account to view meter usage, manage prepaid credit, and run appliance simulations.</p><div className="auth-benefits"><span><Check size={15}/> Personal room-level access</span><span><Check size={15}/> Verified role permissions</span><span><Check size={15}/> Server-managed sessions</span></div></div>
      <section className="auth-card surface-card"><div className="auth-card-icon"><LockKeyhole size={22}/></div><span className="modal-kicker">WELCOME BACK</span><h2>Sign in to SmartVolt</h2><p>Use the credentials issued by your administrator.</p><form onSubmit={submit} className="auth-form"><label htmlFor="login-username">Username</label><input id="login-username" autoComplete="username" autoFocus required maxLength={60} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Enter your username"/><label htmlFor="login-password">Password</label><div className="auth-password-wrap"><input id="login-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required maxLength={200} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password"/><button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? 'Hide' : 'Show'}</button></div>{error && <div className="auth-error" role="alert">{error}</div>}<button className="button primary full-width auth-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <LogIn size={17}/>} {busy ? 'Verifying credentials…' : 'Sign in securely'}<ArrowRight size={16}/></button></form><div className="auth-card-foot"><ShieldCheck size={14}/><span>Sessions expire after 8 hours. Sign out to revoke the session immediately.</span></div></section>
    </div><footer className="auth-footer">© 2026 SmartVolt <span>·</span> Prepaid energy, simplified</footer>
  </div>
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
  const [accountLabel, setAccountLabel] = useState<Account | null>(null)
  const [authState, setAuthState] = useState<'checking' | 'signedOut' | 'signedIn'>('checking')
  const [loginBusy, setLoginBusy] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('smartvolt:theme') as Theme) || 'dark')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [meters, setMeters] = useState<Meter[]>([])
  const [meter, setMeter] = useState<Meter | null>(null)
  const [report, setReport] = useState<UsageReport | null>(null)
  const [hourlyReport, setHourlyReport] = useState<UsageReport | null>(null)
  const [recharges, setRecharges] = useState<Recharge[]>([])
  const [readings, setReadings] = useState<Reading[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [ticketBucket, setTicketBucket] = useState<'PENDING' | 'CLOSED'>('PENDING')
  const [ticketCounts, setTicketCounts] = useState({ pending: 0, closed: 0 })
  const [roomDirectory, setRoomDirectory] = useState<RoomDirectoryItem[]>([])
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const [profileName, setProfileName] = useState('')
  const [profilePhone, setProfilePhone] = useState('')
  const [profileBusy, setProfileBusy] = useState(false)
  const [passwordCurrent, setPasswordCurrent] = useState('')
  const [passwordNew, setPasswordNew] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [period, setPeriod] = useState<'1d' | '7d' | '30d'>('7d')
  const [usageGranularity, setUsageGranularity] = useState<'daily' | 'hourly'>('daily')
  const [usageDate, setUsageDate] = useState(() => indiaDateString())
  const [chartMetric, setChartMetric] = useState<'units' | 'cost'>('units')
  const [exportStartDate, setExportStartDate] = useState(() => `${indiaMonthString()}-01`)
  const [exportEndDate, setExportEndDate] = useState(() => indiaDateString())
  const [statementMonth, setStatementMonth] = useState(() => indiaMonthString())
  const [exportBusy, setExportBusy] = useState(false)
  const [statementBusy, setStatementBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [apiConnected, setApiConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showRecharge, setShowRecharge] = useState(false)
  const [rechargeAmount, setRechargeAmount] = useState('200')
  const [userId, setUserId] = useState(() => sessionStorage.getItem('smartvolt:userId') || '')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [transactionSearch, setTransactionSearch] = useState('')
  const [transactionFilter, setTransactionFilter] = useState('ALL')
  const [ticketType, setTicketType] = useState('Meter or power issue')
  const [ticketDescription, setTicketDescription] = useState('')
  const [ticketVisibility, setTicketVisibility] = useState<'ROOM' | 'PRIVATE'>('ROOM')
  const [ticketReplies, setTicketReplies] = useState<Record<number, string>>({})
  const [ticketActionBusy, setTicketActionBusy] = useState<number | null>(null)
  const [submittingTicket, setSubmittingTicket] = useState(false)
  const [lowBalanceAlert, setLowBalanceAlert] = useState(() => localStorage.getItem('smartvolt:lowBalance') !== 'false')

  const navigate = useCallback((nextPage: PageKey) => {
    const nextPath = routeForPage[nextPage]
    if (window.location.pathname !== nextPath) window.history.pushState({}, '', nextPath)
    setPage(nextPage)
    setMobileNavOpen(false)
    setAccountMenuOpen(false)
    setNotice(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    let active = true
    // Remove credentials left by older builds that stored shared browser-wide auth in localStorage.
    localStorage.removeItem('smartvolt:accessToken')
    localStorage.removeItem('smartvolt:account')
    localStorage.removeItem('smartvolt:userId')
    const clearClientSession = () => {
      setAccountLabel(null); setAuthState('signedOut'); setMeters([]); setMeter(null); setReport(null); setHourlyReport(null); setRoomDirectory([])
      setRecharges([]); setReadings([]); setTickets([]); setUserId(''); sessionStorage.removeItem('smartvolt:userId')
    }
    const onAuthChanged = () => {
      const token = sessionStorage.getItem('smartvolt:accessToken')
      try {
        const saved = JSON.parse(sessionStorage.getItem('smartvolt:account') ?? 'null') as Account | null
        if (token && saved) {
          setAccountLabel(saved); setAuthState('signedIn')
          if (saved.role === 'RESIDENT') setUserId(String(saved.id))
        } else clearClientSession()
      } catch { clearClientSession() }
    }
    const onAuthExpired = () => { clearClientSession(); setLoginError('Your session expired or was signed out. Please sign in again.') }
    window.addEventListener('smartvolt:auth-changed', onAuthChanged)
    window.addEventListener('smartvolt:auth-expired', onAuthExpired)
    const token = sessionStorage.getItem('smartvolt:accessToken')
    if (!token) {
      sessionStorage.removeItem('smartvolt:account')
      clearClientSession()
    } else {
      api<Account>('/auth/me').then((account) => {
        if (!active) return
        sessionStorage.setItem('smartvolt:account', JSON.stringify(account))
        setAccountLabel(account); setAuthState('signedIn')
        if (account.role === 'RESIDENT') { setUserId(String(account.id)); sessionStorage.setItem('smartvolt:userId', String(account.id)) }
      }).catch(() => { if (active) clearClientSession() })
    }
    return () => {
      active = false
      window.removeEventListener('smartvolt:auth-changed', onAuthChanged)
      window.removeEventListener('smartvolt:auth-expired', onAuthExpired)
    }
  }, [])

  useEffect(() => {
    if (accountLabel) { setProfileName(accountLabel.name); setProfilePhone(accountLabel.phone ?? '') }
  }, [accountLabel?.id, accountLabel?.name, accountLabel?.phone])

  useEffect(() => {
    if (accountLabel?.role !== 'RESIDENT') return
    const assignedMeter = meters.find((item) => item.room_id === accountLabel.room_id)
    if (String(accountLabel.id) !== userId) setUserId(String(accountLabel.id))
    if (assignedMeter && assignedMeter.id !== meter?.id) setMeter(assignedMeter)
  }, [accountLabel, meters, meter?.id, userId])

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

  useEffect(() => { sessionStorage.setItem('smartvolt:userId', userId) }, [userId])
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

  const loadDetails = useCallback(async (meterId: number, selectedPeriod: '1d' | '7d' | '30d', selectedDate: string) => {
    const [freshMeter, freshReport, freshHourlyReport, history, meterReadings] = await Promise.all([
      api<Meter>(`/meters/${meterId}`),
      api<UsageReport>(`/meters/${meterId}/report?period=${selectedPeriod}`),
      api<UsageReport>(`/meters/${meterId}/report?granularity=hourly&date=${encodeURIComponent(selectedDate)}`),
      api<Recharge[]>(`/meters/${meterId}/recharges?limit=200`),
      api<Reading[]>(`/meters/${meterId}/readings?limit=200`),
    ])
    setMeter(freshMeter); setReport(freshReport); setHourlyReport(freshHourlyReport)
    setRecharges(history); setReadings(meterReadings); setApiConnected(true)
  }, [])

  const loadTickets = useCallback(async () => {
    if (!accountLabel) return
    try {
      if (accountLabel.role === 'ADMIN') {
        const [items, counts] = await Promise.all([
          api<Ticket[]>(`/admin/tickets?limit=200&bucket=${ticketBucket}`),
          api<{ pending: number; closed: number }>('/admin/tickets/summary'),
        ])
        setTickets(items); setTicketCounts(counts)
      } else {
        setTickets(await api<Ticket[]>(`/users/${accountLabel.id}/tickets?limit=100`))
      }
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
  }, [accountLabel, ticketBucket])

  useEffect(() => {
    if (authState === 'signedIn') void loadMeters()
    else { setMeters([]); setMeter(null); setLoading(false) }
  }, [authState, loadMeters])
  useEffect(() => {
    if (authState !== 'signedIn' || !meter?.id) return
    let active = true
    loadDetails(meter.id, period, usageDate).catch((error: Error) => {
      if (active) { setApiConnected(false); setNotice({ type: 'error', text: error.message }) }
    })
    return () => { active = false }
  }, [authState, meter?.id, period, usageDate, loadDetails])
  useEffect(() => { if (authState === 'signedIn' && page === 'support' && accountLabel) void loadTickets() }, [authState, page, accountLabel, loadTickets])
  useEffect(() => {
    if (authState !== 'signedIn' || accountLabel?.role !== 'ADMIN' || page !== 'rooms') return
    let active = true
    api<RoomDirectoryItem[]>('/admin/rooms').then((items) => { if (active) setRoomDirectory(items) })
      .catch((error) => { if (active) setNotice({ type: 'error', text: `Unable to load room directory: ${(error as Error).message}` }) })
    return () => { active = false }
  }, [authState, accountLabel?.role, page])

  const chartData = useMemo(() => (report?.daily ?? []).map((item) => ({
    axisLabel: dateShort(item.date), tooltipLabel: item.date, units: Number(item.units_used), cost: Number(item.cost), readingCount: 0,
  })), [report])
  const hourlyChartData = useMemo(() => (hourlyReport?.hourly ?? []).map((item) => ({
    axisLabel: `${String(item.hour).padStart(2, '0')}:00`, tooltipLabel: item.label,
    units: Number(item.units_used), cost: Number(item.cost), readingCount: item.reading_count,
  })), [hourlyReport])
  const usageChartData = usageGranularity === 'hourly' ? hourlyChartData : chartData
  const activeUsageReport = usageGranularity === 'hourly' ? hourlyReport : report
  const hourlyPeak = useMemo(() => hourlyChartData.reduce((best, item) => item.units > best.units ? item : best, {
    axisLabel: '--:--', tooltipLabel: 'No consumption', units: 0, cost: 0, readingCount: 0,
  }), [hourlyChartData])
  const chartBucketUnits = useMemo(() => usageChartData.reduce((sum, item) => sum + item.units, 0), [usageChartData])
  const chartBucketCost = useMemo(() => usageChartData.reduce((sum, item) => sum + item.cost, 0), [usageChartData])
  const averageDaily = report && chartData.length ? Number(report.total_units) / chartData.length : 0
  const filteredTransactions = useMemo(() => recharges.filter((item) => {
    const matchesFilter = transactionFilter === 'ALL' || item.status.toUpperCase() === transactionFilter
    const term = transactionSearch.trim().toLowerCase()
    return matchesFilter && (!term || `wallet recharge ${item.recharge_code ?? item.id} ${item.user_id ?? ''} ${item.status} ${item.amount}`.toLowerCase().includes(term))
  }), [recharges, transactionFilter, transactionSearch])
  const totalRecharge = useMemo(() => recharges.filter((item) => item.status.toUpperCase() === 'SUCCESSFUL').reduce((sum, item) => sum + Number(item.amount), 0), [recharges])
  const pendingTicketCount = ticketCounts.pending
  const closedTicketCount = ticketCounts.closed
  const visibleTickets = useMemo(() => accountLabel?.role !== 'ADMIN' ? tickets : tickets.filter((ticket) =>
    ticketBucket === 'PENDING' ? ['OPEN', 'IN_PROGRESS', 'AWAITING_RESIDENT'].includes(ticket.status) : ['RESOLVED', 'CLOSED'].includes(ticket.status)
  ), [accountLabel?.role, tickets, ticketBucket])
  const selectedRoomDetails = roomDirectory.find((room) => room.meter?.id === meter?.id) ?? null

  async function refresh() {
    if (!meter) return
    try { await loadDetails(meter.id, period, usageDate) }
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
    // The standard wallet modal is resident-only. Administrators must use the
    // dedicated multi-meter recharge workflow in Admin Console.
    if (!meter || accountLabel?.role !== 'RESIDENT') return
    setBusy(true); setNotice(null)
    try {
      await api<Recharge>(`/meters/${meter.id}/recharges`, {
        method: 'POST', body: JSON.stringify({ user_id: accountLabel.id, amount: rechargeAmount, idempotency_key: crypto.randomUUID() }),
      })
      setShowRecharge(false); setNotice({ type: 'success', text: 'Demo recharge added to your room meter.' }); await refresh()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setBusy(false) }
  }

  async function exportUsageCsv() {
    if (!meter) return
    if (!exportStartDate || !exportEndDate || exportEndDate < exportStartDate) {
      setNotice({ type: 'error', text: 'Choose a valid usage export date range.' })
      return
    }
    setExportBusy(true)
    try {
      const token = sessionStorage.getItem('smartvolt:accessToken')
      const query = new URLSearchParams({ start_date: exportStartDate, end_date: exportEndDate })
      const response = await fetch(`/api/v1/meters/${meter.id}/usage-export?${query.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as ApiError
        if (response.status === 401 && token) window.dispatchEvent(new Event('smartvolt:auth-expired'))
        throw new Error(body.detail ?? `Export failed (${response.status})`)
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') ?? ''
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? `smartvolt-usage-${meter.meter_code}.csv`
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove()
      URL.revokeObjectURL(url)
      setNotice({ type: 'success', text: `Usage CSV downloaded for ${exportStartDate} to ${exportEndDate}.` })
    } catch (error) {
      setNotice({ type: 'error', text: (error as Error).message })
    } finally { setExportBusy(false) }
  }

  async function printMonthlyStatement() {
    if (!meter) return
    if (!/^\d{4}-\d{2}$/.test(statementMonth)) {
      setNotice({ type: 'error', text: 'Choose a valid billing month.' })
      return
    }
    // Open synchronously during the user gesture so popup blockers do not discard the printable receipt.
    const receiptWindow = window.open('', '_blank')
    if (!receiptWindow) {
      setNotice({ type: 'error', text: 'Allow pop-ups for SmartVolt to open the monthly receipt.' })
      return
    }
    setStatementBusy(true)
    receiptWindow.document.write('<!doctype html><title>Preparing SmartVolt receipt…</title><p style="font:16px sans-serif;padding:24px">Preparing monthly statement…</p>')
    receiptWindow.document.close()
    try {
      const statement = await api<BillingStatement>(`/meters/${meter.id}/billing-statement?month=${encodeURIComponent(statementMonth)}`)
      const row = (label: string, value: unknown) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`
      receiptWindow.document.open()
      receiptWindow.document.write(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SmartVolt ${escapeHtml(statement.month)} monthly statement</title><style>
        body{font:14px/1.5 Arial,sans-serif;color:#182434;margin:32px auto;max-width:760px;padding:0 22px}header{border-bottom:2px solid #25b98b;padding-bottom:16px;margin-bottom:22px}h1{margin:0 0 4px;font-size:28px}p{color:#536273}.summary{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:22px 0}.tile{border:1px solid #dce4ec;border-radius:8px;padding:14px}.tile strong{display:block;font-size:22px;margin-top:6px}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border-bottom:1px solid #e1e7ee;padding:11px;text-align:left}th{width:48%;color:#566578}td{text-align:right;font-weight:600}.actions{margin:22px 0}button{background:#159d74;color:white;border:0;border-radius:7px;padding:10px 15px;font-weight:700;cursor:pointer}.small{font-size:11px;color:#64748b}.footer{margin-top:26px;border-top:1px solid #dce4ec;padding-top:12px}@media print{body{margin:0;max-width:none}.actions{display:none}}
      </style></head><body><header><h1>SmartVolt</h1><div>Monthly simulated electricity statement</div><p>${escapeHtml(statement.period_start)} through ${escapeHtml(statement.period_end)} · ${escapeHtml(statement.timezone)}</p></header>
        <div class="summary"><div class="tile">Energy consumed<strong>${Number(statement.total_units).toFixed(3)} kWh</strong></div><div class="tile">Recorded energy cost<strong>${money(statement.total_energy_cost)}</strong></div></div>
        <table>${row('Room', `${statement.room_no} (${statement.room_code})`)}${row('Meter ID', statement.meter_code)}${row('Billing month', statement.month)}${row('Reading events', statement.reading_count)}${row('Recharge credits in month', money(statement.total_recharge_amount))}${row('Recharge transactions', statement.recharge_count)}${row('Opening balance snapshot', statement.opening_balance == null ? 'Unavailable' : money(statement.opening_balance))}${row('Closing balance snapshot', statement.closing_balance == null ? 'Unavailable' : money(statement.closing_balance))}${row('Current tariff (reference only)', `${money(statement.current_tariff_per_kwh)} / kWh`)}${row('Estimated grid CO₂', `${Number(statement.estimated_co2_kg).toFixed(3)} kg`)}${row('Grid factor', `${statement.co2_factor_kg_per_kwh} kg CO₂/kWh`)}</table>
        <p class="small">${escapeHtml(statement.statement_note)}</p><p class="small">Environmental estimate uses a configurable grid factor and is indicative, not a verified emissions inventory or claim of trees saved. Source: <a href="${escapeHtml(statement.co2_factor_source_url)}">${escapeHtml(statement.co2_factor_source)}</a>.</p>
        <div class="actions"><button onclick="window.print()">Print / Save as PDF</button></div><div class="footer small">Generated by SmartVolt · This is a simulated-meter statement, not an electricity utility invoice or payment receipt.</div></body></html>`)
      receiptWindow.document.close()
      setNotice({ type: 'success', text: `Monthly statement opened for ${statement.month}. Use Print / Save as PDF in that tab.` })
    } catch (error) {
      receiptWindow.close()
      setNotice({ type: 'error', text: (error as Error).message })
    } finally { setStatementBusy(false) }
  }

  async function submitTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSubmittingTicket(true); setNotice(null)
    try {
      await api<Ticket>('/tickets', { method: 'POST', body: JSON.stringify({ user_id: accountLabel!.id, issue_type: ticketType, description: ticketDescription, visibility: ticketVisibility }) })
      setTicketDescription(''); setTicketVisibility('ROOM')
      setNotice({ type: 'success', text: 'Support ticket created. Authorized room members and administrators can now follow the conversation.' }); await loadTickets()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSubmittingTicket(false) }
  }

  async function replyToTicket(event: FormEvent<HTMLFormElement>, ticketId: number) {
    event.preventDefault()
    const message = (ticketReplies[ticketId] ?? '').trim()
    if (!message) return
    setTicketActionBusy(ticketId); setNotice(null)
    try {
      await api<TicketMessage>(`/tickets/${ticketId}/messages`, { method: 'POST', body: JSON.stringify({ message }) })
      setTicketReplies((current) => ({ ...current, [ticketId]: '' }))
      setNotice({ type: 'success', text: 'Reply added to the support conversation.' })
      await loadTickets()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setTicketActionBusy(null) }
  }

  async function updateTicket(ticketId: number, patch: { status?: TicketStatus; priority?: Ticket['priority'] }) {
    setTicketActionBusy(ticketId); setNotice(null)
    try {
      await api<Ticket>(`/admin/tickets/${ticketId}`, { method: 'PATCH', body: JSON.stringify(patch) })
      setNotice({ type: 'success', text: 'Support ticket updated.' })
      await loadTickets()
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setTicketActionBusy(null) }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setProfileBusy(true); setNotice(null)
    try {
      const updated = await api<Account>('/auth/profile', { method: 'PATCH', body: JSON.stringify({ name: profileName.trim(), phone: profilePhone.trim() || null }) })
      setAccountLabel(updated); sessionStorage.setItem('smartvolt:account', JSON.stringify(updated))
      setNotice({ type: 'success', text: 'Your profile has been updated.' })
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }) }
    finally { setProfileBusy(false) }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPasswordError(''); setNotice(null)
    if (passwordNew !== passwordConfirm) { setPasswordError('The new passwords do not match.'); return }
    if (passwordNew.length < 8) { setPasswordError('Use at least 8 characters for your new password.'); return }
    setPasswordBusy(true)
    try {
      await api<{ success: boolean; sessions_revoked: number }>('/auth/change-password', {
        method: 'POST', body: JSON.stringify({ current_password: passwordCurrent, new_password: passwordNew }),
      })
      sessionStorage.removeItem('smartvolt:accessToken'); sessionStorage.removeItem('smartvolt:account'); sessionStorage.removeItem('smartvolt:userId')
      setAccountLabel(null); setAuthState('signedOut'); setUserId(''); setMeters([]); setMeter(null); setReport(null); setHourlyReport(null)
      setRecharges([]); setReadings([]); setTickets([]); setPasswordCurrent(''); setPasswordNew(''); setPasswordConfirm('')
      setLoginError('Password changed successfully. Please sign in with your new password.')
      window.history.replaceState({}, '', '/overview')
      window.dispatchEvent(new Event('smartvolt:auth-changed'))
    } catch (error) { setPasswordError((error as Error).message) }
    finally { setPasswordBusy(false) }
  }

  async function signIn(username: string, password: string) {
    setLoginBusy(true); setLoginError('')
    try {
      const result = await api<{ access_token: string; account: Account }>('/auth/login', {
        method: 'POST', body: JSON.stringify({ username: username.trim(), password }),
      })
      sessionStorage.setItem('smartvolt:accessToken', result.access_token)
      const verified = await api<Account>('/auth/me')
      sessionStorage.setItem('smartvolt:account', JSON.stringify(verified))
      sessionStorage.setItem('smartvolt:userId', String(verified.id))
      setAccountLabel(verified); setAuthState('signedIn'); setUserId(String(verified.id)); setRoomDirectory([]); setAccountMenuOpen(false)
      setMeters([]); setMeter(null); setReport(null); setHourlyReport(null); setRecharges([]); setReadings([]); setTickets([])
      setPage('overview'); window.history.replaceState({}, '', '/overview')
      window.dispatchEvent(new Event('smartvolt:auth-changed'))
    } catch (error) {
      sessionStorage.removeItem('smartvolt:accessToken'); sessionStorage.removeItem('smartvolt:account')
      setAccountLabel(null); setAuthState('signedOut')
      setLoginError((error as Error).message || 'Unable to sign in. Please try again.')
    } finally { setLoginBusy(false) }
  }

  async function signOut() {
    try { if (sessionStorage.getItem('smartvolt:accessToken')) await api<{ success: boolean }>('/auth/logout', { method: 'POST' }) }
    catch { /* Client sign-out still completes if the server or session is unavailable. */ }
    sessionStorage.removeItem('smartvolt:accessToken'); sessionStorage.removeItem('smartvolt:account'); sessionStorage.removeItem('smartvolt:userId')
    setAccountLabel(null); setAuthState('signedOut'); setUserId(''); setMeters([]); setMeter(null); setReport(null); setHourlyReport(null); setRoomDirectory([]); setAccountMenuOpen(false)
    setRecharges([]); setReadings([]); setTickets([]); setNotice(null); setLoginError('You have been signed out.')
    window.history.replaceState({}, '', '/overview')
    window.dispatchEvent(new Event('smartvolt:auth-changed'))
  }

  const navGroups: { title: string; items: PageKey[] }[] = [
    { title: 'Workspace', items: ['overview', 'usage', 'transactions', 'rooms'] },
    { title: 'Simulation', items: ['simulation'] },
    { title: 'Manage', items: [...(accountLabel?.role === 'ADMIN' ? ['admin' as PageKey] : []), 'settings', 'support'] },
  ]
  const activeMeta = pageMeta[page]
  const visibleMeters = accountLabel?.role === 'RESIDENT'
    ? meters.filter((item) => item.room_id === accountLabel.room_id)
    : meters

  useEffect(() => {
    if (authState === 'signedIn' && accountLabel?.role === 'RESIDENT' && page === 'admin') {
      setPage('overview'); window.history.replaceState({}, '', '/overview')
      setNotice({ type: 'error', text: 'Administrator access is required for the Admin Console.' })
    }
  }, [authState, accountLabel?.role, page])

  const pageIntro = (eyebrow: string, title: string, description: string, actions?: ReactNode) => <div className="page-intro">
    <div className="intro-copy"><div className="eyebrow"><Sparkles size={14} /> {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
    {actions && <div className="intro-actions">{actions}</div>}
  </div>


  if (authState === 'checking') return <div className="auth-loading-screen"><div className="auth-loading-card"><span className="brand-mark"><Zap size={24}/></span><LoaderCircle className="spin" size={22}/><strong>Checking your SmartVolt session…</strong><p>Your account and permissions are being verified.</p></div></div>
  if (authState !== 'signedIn' || !accountLabel) return <LoginScreen busy={loginBusy} error={loginError} onSubmit={signIn} theme={theme} onThemeChange={setTheme}/>

  return <div className="app-shell" data-theme={theme}>
    <aside className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
      <a className="brand" href="/overview" onClick={(event) => { event.preventDefault(); navigate('overview') }}>
        <span className="brand-mark"><Zap size={22} fill="currentColor" /></span><span className="brand-copy"><strong>smartvolt<span>.</span></strong><small>ENERGY, MADE CLEAR</small></span>
      </a>
      <div className="workspace-switcher-container">
        <button type="button" className="workspace-switcher" aria-haspopup="menu" aria-expanded={accountMenuOpen} onClick={() => setAccountMenuOpen((open) => !open)}>
          <span className="workspace-avatar">S</span><span><strong>{accountLabel?.role === 'ADMIN' ? 'Administrator workspace' : 'Resident workspace'}</strong><small>{accountLabel ? `${accountLabel.role.toLowerCase()} · ${accountLabel.username}` : 'Demo meter workspace'}</small></span><ChevronDown size={15} />
        </button>
        {accountMenuOpen && <div className="workspace-menu" role="menu">
          <div className="workspace-menu-heading"><strong>{accountLabel.name}</strong><small>{accountLabel.role === 'ADMIN' ? 'Administrator account' : (accountLabel.tenant_code ?? 'Resident account')}</small></div>
          <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); navigate('settings') }}><Settings size={15}/> My profile & settings</button>
          {accountLabel.role === 'ADMIN' && <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); navigate('admin') }}><Users size={15}/> Admin Console</button>}
          <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); void signOut() }}><LogOut size={15}/> Switch account <small>Sign out and authenticate again</small></button>
        </div>}
      </div>
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
      <div className="sidebar-bottom"><div className="sidebar-divider" /><button className="nav-item" onClick={() => navigate('support')}><CircleHelp size={18}/><span>Help center</span></button><div className="profile-row"><div className="avatar">{(accountLabel?.name ?? 'Ishan Srivastav').split(/\s+/).map((part) => part[0]).slice(0,2).join('').toUpperCase()}</div><div className="profile-copy"><strong>{accountLabel?.name ?? 'Ishan Srivastav'}</strong><small>{accountLabel ? `${accountLabel.role.toLowerCase()} · ${accountLabel.username}` : 'Resident · Demo account'}</small></div><button className="icon-ghost" aria-label="Open settings" onClick={() => navigate('settings')}><Settings size={16}/></button></div></div>
    </aside>
    {mobileNavOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}

    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileNavOpen(true)}><Menu size={19}/></button><div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{activeMeta.label}</strong></div></div>
        <div className="topbar-right"><span className={`system-status ${apiConnected ? 'connected' : 'disconnected'}`}><i />{apiConnected ? 'API connected' : 'API offline'}</span><span className="topbar-date"><Clock3 size={15}/>{new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span><button className="theme-toggle" onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'day' : 'night'} mode`} title={`Switch to ${theme === 'dark' ? 'day' : 'night'} mode`}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}<span>{theme === 'dark' ? 'Day mode' : 'Night mode'}</span></button><button className="avatar mini" aria-label="Account settings" onClick={() => navigate(accountLabel.role === 'ADMIN' ? 'admin' : 'settings')}>{accountLabel.name.split(/\s+/).map((part) => part[0]).slice(0,2).join('').toUpperCase()}</button><button className="button secondary signout-button" onClick={() => void signOut()} title="Sign out of SmartVolt"><LogOut size={15}/><span>Sign out</span></button></div>
      </header>

      <div className="page-content page-enter" key={page}>
        {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.type === 'success' ? <Check size={17}/> : notice.type === 'error' ? <CircleHelp size={17}/> : <Bell size={17}/>} {notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={15}/></button></div>}

        {page === 'overview' && <>
          {pageIntro(accountLabel?.role === 'ADMIN' ? 'ADMIN OVERVIEW' : 'YOUR ENERGY OVERVIEW', `${greeting()}, ${(accountLabel?.name ?? 'Ishan').split(/\s+/)[0]}`, accountLabel?.role === 'ADMIN' ? 'Review the selected meter and simulated load activity across your workspace.' : 'Here’s your room’s electricity snapshot for today.', <><label className="meter-select"><span>Meter</span><select value={meter?.id ?? ''} onChange={(event) => setMeter(visibleMeters.find((item) => item.id === Number(event.target.value)) ?? null)} aria-label="Select meter" disabled={!visibleMeters.length}>{visibleMeters.map((item) => <option value={item.id} key={item.id}>Room {item.room_id} · #{item.id}</option>)}</select><ChevronDown size={14}/></label>{accountLabel?.role === 'RESIDENT' && <button className="button primary" onClick={() => setShowRecharge(true)} disabled={!meter}><Plus size={16}/> Add money</button>}</>)}
          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={23}/> Connecting to SmartVolt…</div> : !meter ? <EmptyState icon={BatteryCharging} title="No meter connected yet" description="Seed the local database to create the demo room and meter." action={<code>python -m app.db.seed</code>}/> : <>
            {lowBalanceAlert && Number(meter.current_balance) < 150 && <div className="inline-alert"><span className="alert-icon"><Bell size={16}/></span><span><strong>Balance running low</strong><small>{accountLabel?.role === 'ADMIN' ? 'This meter is below ₹150. Use Admin Console → Recharge any meter to add credit.' : 'Your balance is below ₹150. Top up now to avoid an unexpected power cut.'}</small></span>{accountLabel?.role === 'RESIDENT' && <button className="text-button" onClick={() => setShowRecharge(true)}>Recharge <ArrowRight size={14}/></button>}<button className="alert-close" onClick={() => setLowBalanceAlert(false)} aria-label="Dismiss"><X size={15}/></button></div>}
            <section className="metric-grid"><Metric label="Available balance" value={money(meter.current_balance)} detail={Number(meter.current_balance) > 0 ? 'Ready for consumption' : 'Recharge required'} icon={Wallet} tone="mint"/><Metric label="Energy consumed" value={`${Number(report?.total_units ?? 0).toFixed(2)} kWh`} detail={`${report?.reading_count ?? 0} readings · ${period === '1d' ? 'Today' : period === '7d' ? 'Last 7 days' : 'Last 30 days'}`} icon={Zap} tone="violet" trend="up"/><Metric label="Estimated cost" value={money(report?.total_cost ?? 0)} detail={`${money(meter.tariff_per_kwh)} per kWh`} icon={ReceiptText} tone="amber"/><Metric label="Room power" value={meter.power_status ? 'Enabled' : 'Disabled'} detail="Software relay simulation" icon={Power} tone={meter.power_status ? 'mint' : 'rose'}/></section>
            <section className="dashboard-grid"><article className="panel surface-card analytics-panel"><SectionHeading title="Consumption analytics" description="Understand where your energy goes." action={<PeriodControl period={period} setPeriod={setPeriod}/>}/><div className="chart-summary"><div><span className="chart-legend"><i/> Energy used</span><strong>{Number(report?.total_units ?? 0).toFixed(2)} <small>kWh</small></strong></div><span className="chart-average">Daily avg. {averageDaily.toFixed(2)} kWh</span></div><div className="chart-wrap">{chartData.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 10, right: 8, left: -20, bottom: 0 }}><defs><linearGradient id="usageFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={0.24}/><stop offset="100%" stopColor="var(--accent)" stopOpacity={0.015}/></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="4 6"/><XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} dy={8}/><YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }}/><Tooltip formatter={(value) => [`${Number(value).toFixed(3)} kWh`, 'Energy used']} contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--border)', borderRadius: 12, color: 'var(--text)' }}/><Area type="monotone" dataKey="units" stroke="var(--accent)" strokeWidth={2.5} fill="url(#usageFill)" activeDot={{ r: 5, strokeWidth: 0 }}/></AreaChart></ResponsiveContainer> : <div className="chart-empty"><Activity size={25}/><span>No consumption readings in this period yet.</span><small>Record a simulated reading to see the trend.</small></div>}</div><div className="chart-footer"><span><ShieldCheck size={15}/> Stored in the database</span><button className="text-button" onClick={() => navigate('usage')}>Full usage report <ArrowUpRight size={14}/></button></div></article>
              <MeterStatusCard meter={meter} busy={busy} onToggle={togglePower}/></section>
            <section className="bottom-grid"><article className="panel surface-card"><SectionHeading title="Recent transactions" description="Your latest wallet activity." action={<button className="text-button" onClick={() => navigate('transactions')}>View all <ArrowUpRight size={14}/></button>}/>{recharges.length ? <TransactionList items={recharges.slice(0, 4)}/> : <div className="mini-empty"><Wallet size={22}/><span>No recharges yet</span>{accountLabel?.role === 'RESIDENT' && <button onClick={() => setShowRecharge(true)}>Add your first recharge</button>}</div>}</article><article className="impact-card"><div className="impact-orb"/><div className="impact-top"><span className="impact-icon"><Leaf size={19}/></span><span className="impact-label">YOUR ENVIRONMENTAL IMPACT</span></div><h2>{Number(report?.estimated_co2_kg ?? 0).toFixed(2)} kg CO₂</h2><p>Estimated grid emissions associated with {Number(report?.total_units ?? 0).toFixed(2)} kWh of recorded consumption. Lower usage generally means lower estimated grid emissions.</p><div className="impact-bottom"><span><Sparkles size={15}/> {Number(report?.tree_years_equivalent ?? 0).toFixed(3)} tree-years equivalent</span><span className="impact-decoration"><i/><i/><i/><i/><i/></span></div><small className="impact-disclaimer">Factor: {report?.co2_factor_kg_per_kwh ?? '0.675'} kg CO₂/kWh. Tree-year value is illustrative, not verified trees saved. <a href={report?.co2_factor_source_url ?? 'https://cea.nic.in/cdm-co2-baseline-database/?lang=en'} target="_blank" rel="noreferrer">Source</a>.</small></article></section>
          </>}
        </>}

        {page === 'usage' && <>
          {pageIntro('ENERGY INTELLIGENCE', 'Consumption analytics', 'Inspect usage by hour in India local time or compare daily, weekly, and monthly trends.',
            <div className="analytics-controls">
              <div className="view-toggle" role="group" aria-label="Consumption interval">
                <button className={usageGranularity === 'daily' ? 'active' : ''} onClick={() => setUsageGranularity('daily')}>Daily</button>
                <button className={usageGranularity === 'hourly' ? 'active' : ''} onClick={() => setUsageGranularity('hourly')}>Hourly</button>
              </div>
              {usageGranularity === 'daily'
                ? <PeriodControl period={period} setPeriod={setPeriod}/>
                : <label className="date-picker-control"><span>Day (IST)</span><input aria-label="Hourly report date" type="date" max={indiaDateString()} value={usageDate} onChange={(event) => event.target.value && setUsageDate(event.target.value)}/></label>}
            </div>)}
          <section className="panel surface-card usage-export-panel"><div className="usage-export-copy"><strong>Usage export & monthly receipt</strong><small>Download itemized readings for a date range or open a printable monthly statement.</small></div><div className="usage-export-fields"><label>From (IST)<input type="date" value={exportStartDate} max={indiaDateString()} onChange={(event) => setExportStartDate(event.target.value)}/></label><label>To (IST)<input type="date" value={exportEndDate} max={indiaDateString()} min={exportStartDate} onChange={(event) => setExportEndDate(event.target.value)}/></label><button className="button secondary" disabled={!meter || exportBusy} onClick={() => void exportUsageCsv()}>{exportBusy ? <LoaderCircle size={15} className="spin"/> : <Download size={15}/>} Export CSV</button><label>Billing month<input type="month" value={statementMonth} max={indiaMonthString()} onChange={(event) => setStatementMonth(event.target.value)}/></label><button className="button primary" disabled={!meter || statementBusy} onClick={() => void printMonthlyStatement()}>{statementBusy ? <LoaderCircle size={15} className="spin"/> : <ReceiptText size={15}/>} Monthly receipt</button></div></section>
          {!meter ? <EmptyState icon={Gauge} title="No meter available" description="Connect a meter to start collecting energy history."/> : <>
            <section className="metric-grid three-metrics">
              <Metric label="Total consumption" value={`${Number(activeUsageReport?.total_units ?? 0).toFixed(3)} kWh`} detail={usageGranularity === 'hourly' ? `${hourlyReport?.reading_count ?? 0} readings · ${usageDate} IST` : `${report?.reading_count ?? 0} readings in period`} icon={Zap} tone="violet"/>
              <Metric label="Estimated spend" value={money(activeUsageReport?.total_cost ?? 0)} detail={`Tariff: ${money(meter.tariff_per_kwh)}/kWh`} icon={CreditCard} tone="mint"/>
              {usageGranularity === 'hourly'
                ? <Metric label="Peak usage hour" value={hourlyPeak.units > 0 ? hourlyPeak.axisLabel : 'No usage'} detail={`${hourlyPeak.units.toFixed(3)} kWh · ${hourlyPeak.tooltipLabel}`} icon={TrendingUp} tone="amber"/>
                : <Metric label="Daily average" value={`${averageDaily.toFixed(3)} kWh`} detail="Average for days with data" icon={TrendingUp} tone="amber"/>}
            </section>
            <article className="panel surface-card environmental-panel"><div className="environmental-panel-icon"><Leaf size={20}/></div><div className="environmental-panel-main"><span className="overline">ESTIMATED GRID EMISSIONS</span><strong>{Number(activeUsageReport?.estimated_co2_kg ?? 0).toFixed(3)} kg CO₂</strong><p>{Number(activeUsageReport?.total_units ?? 0).toFixed(3)} kWh × {Number(activeUsageReport?.co2_factor_kg_per_kwh ?? 0.675).toFixed(3)} kg CO₂/kWh</p><small>{activeUsageReport?.co2_factor_source ?? 'CEA India grid emission factor'} · <a href={activeUsageReport?.co2_factor_source_url ?? 'https://cea.nic.in/cdm-co2-baseline-database/?lang=en'} target="_blank" rel="noreferrer">Factor source</a></small></div><div className="environmental-panel-tree"><span>Tree-year equivalent</span><strong>{Number(activeUsageReport?.tree_years_equivalent ?? 0).toFixed(4)}</strong><small>Illustrative annual absorption equivalent, not actual trees saved.</small></div></article>
            {usageGranularity === 'hourly' && Number(hourlyReport?.unallocated_units ?? 0) > 0 && <div className="analytics-data-note"><ShieldCheck size={16}/><span><strong>Some historical scenario data has no hourly detail.</strong> {Number(hourlyReport?.unallocated_units ?? 0).toFixed(3)} kWh ({money(hourlyReport?.unallocated_cost ?? 0)}) from {hourlyReport?.unallocated_reading_count ?? 0} older block-based records is included in the day's total above but shown separately—not assigned to a specific hour. New scenario history is now split by hour.</span></div>}
            <article className="panel surface-card usage-detail-panel">
              <SectionHeading title={usageGranularity === 'hourly' ? 'Energy by hour' : 'Energy over time'} description={usageGranularity === 'hourly' ? '24 local-time intervals from midnight to midnight (Asia/Kolkata).' : 'Switch between consumption and estimated cost.'} action={<div className="view-toggle"><button className={chartMetric === 'units' ? 'active' : ''} onClick={() => setChartMetric('units')}>Units (kWh)</button><button className={chartMetric === 'cost' ? 'active' : ''} onClick={() => setChartMetric('cost')}>Cost (₹)</button></div>}/>
              <div className="usage-chart-summary"><div><span className="chart-legend"><i/>{usageGranularity === 'hourly' ? (chartMetric === 'units' ? 'Hourly-resolved consumption' : 'Hourly-resolved cost') : (chartMetric === 'units' ? 'Daily consumption' : 'Daily estimated cost')}</span><strong>{chartMetric === 'units' ? `${chartBucketUnits.toFixed(3)} kWh` : money(chartBucketCost)}</strong></div><span className="period-pill">{usageGranularity === 'hourly' ? `${usageDate} · IST` : period === '1d' ? 'Today' : period === '7d' ? 'Last 7 days' : 'Last 30 days'}</span></div>
              <div className={`usage-chart ${usageGranularity === 'hourly' ? 'hourly-usage-chart' : ''}`}>
                {usageChartData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={usageChartData} margin={{ top: 12, right: 12, left: -14, bottom: usageGranularity === 'hourly' ? 22 : 0 }} barCategoryGap={usageGranularity === 'hourly' ? '18%' : '34%'}>
                  <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="4 6"/>
                  <XAxis dataKey="axisLabel" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: usageGranularity === 'hourly' ? 9 : 11 }} interval={usageGranularity === 'hourly' ? 1 : 0} angle={usageGranularity === 'hourly' ? -45 : 0} textAnchor={usageGranularity === 'hourly' ? 'end' : 'middle'} height={usageGranularity === 'hourly' ? 48 : 30} dy={usageGranularity === 'hourly' ? 8 : 9}/>
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }}/>
                  <Tooltip labelFormatter={(label) => usageGranularity === 'hourly' ? (hourlyChartData.find((item) => item.axisLabel === String(label))?.tooltipLabel ?? label) : label} formatter={(value) => chartMetric === 'units' ? [`${Number(value).toFixed(3)} kWh`, 'Consumption'] : [money(Number(value)), 'Estimated cost']} contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--border)', borderRadius: 12, color: 'var(--text)' }}/>
                  <Bar dataKey={chartMetric} fill="var(--accent)" radius={[6, 6, 2, 2]} maxBarSize={usageGranularity === 'hourly' ? 24 : 38}/>
                </BarChart></ResponsiveContainer> : <div className="chart-empty"><Activity size={25}/><span>No consumption readings in this period yet.</span><small>Record a simulated reading to see the trend.</small></div>}
              </div>
            </article>
            {usageGranularity === 'hourly' && hourlyReport && <article className="panel surface-card table-panel"><SectionHeading title="Hourly breakdown" description="All 24 intervals, including hours with zero consumption."/><div className="table-scroll"><table><thead><tr><th>Hour (IST)</th><th>Consumption</th><th>Estimated cost</th><th>Readings</th></tr></thead><tbody>{hourlyReport.hourly?.map((item) => <tr key={item.hour}><td>{item.label}</td><td>{Number(item.units_used).toFixed(4)} kWh</td><td>{money(item.cost)}</td><td>{item.reading_count}</td></tr>)}</tbody><tfoot><tr><th>Hourly-resolved total</th><th>{chartBucketUnits.toFixed(4)} kWh</th><th>{money(chartBucketCost)}</th><th>{hourlyReport.hourly?.reduce((sum, item) => sum + item.reading_count, 0) ?? 0}</th></tr></tfoot></table></div></article>}
            <article className="panel surface-card table-panel"><SectionHeading title="Latest meter readings" description="Individual usage events recorded by the simulator." action={<span className="count-label">{readings.length} records loaded</span>}/>{readings.length ? <div className="table-scroll"><table><thead><tr><th>Reading</th><th>Timestamp</th><th>Units used</th><th>Cost</th><th>Balance after</th></tr></thead><tbody>{readings.slice(0, 20).map((reading) => <tr key={reading.id}><td><span className="record-id">#{String(reading.id).padStart(4, '0')}</span></td><td>{dateTime(reading.created_at)}</td><td>{Number(reading.units_used).toFixed(3)} kWh</td><td>{money(reading.cost)}</td><td className="strong-cell">{money(reading.balance_after)}</td></tr>)}</tbody></table></div> : <EmptyState icon={FileClock} title="No readings recorded" description="Once the simulator records consumption, individual meter events will appear here."/>}</article>
          </>}
        </>}

        {page === 'transactions' && <>
          {pageIntro('WALLET ACTIVITY', 'Wallet & transactions', 'Review every simulated recharge and keep your wallet history transparent.', accountLabel?.role === 'RESIDENT' ? <button className="button primary" onClick={() => setShowRecharge(true)} disabled={!meter}><Plus size={16}/> Add money</button> : undefined)}
          <section className="metric-grid three-metrics"><Metric label="Current balance" value={money(meter?.current_balance ?? 0)} detail="Available to consume" icon={Wallet} tone="mint"/><Metric label="Successful credits" value={money(totalRecharge)} detail="Across loaded history" icon={ArrowDownLeft} tone="violet"/><Metric label="Recharge count" value={String(recharges.length)} detail={`${recharges.filter((item) => item.status.toUpperCase() === 'SUCCESSFUL').length} successful`} icon={ReceiptText} tone="amber"/></section>
          <article className="panel surface-card table-panel transaction-table-panel"><SectionHeading title="Transaction history" description="Search by transaction ID, resident, or status." action={<button className="button secondary" onClick={() => { const rows = [['Transaction ID','Date','Resident ID','Amount','Status'], ...filteredTransactions.map((item) => [String(item.id), dateTime(item.created_at), String(item.user_id), item.amount, item.status])]; const csv = rows.map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n'); const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' })); link.download = 'smartvolt-transactions.csv'; link.click(); URL.revokeObjectURL(link.href) }}><Download size={15}/> Export CSV</button>}/><div className="table-toolbar"><label className="search-field"><Search size={16}/><input placeholder="Search transactions…" value={transactionSearch} onChange={(event) => setTransactionSearch(event.target.value)}/></label><label className="filter-select"><Filter size={15}/><select value={transactionFilter} onChange={(event) => setTransactionFilter(event.target.value)} aria-label="Filter transaction status"><option value="ALL">All statuses</option><option value="SUCCESSFUL">Successful</option><option value="FAILED">Failed</option></select><ChevronDown size={14}/></label></div>
            {filteredTransactions.length ? <div className="table-scroll"><table><thead><tr><th>Transaction</th><th>Date & time</th><th>Resident</th><th>Amount</th><th>Status</th></tr></thead><tbody>{filteredTransactions.map((item) => <tr key={item.id}><td><div className="table-title-cell"><span className="table-icon"><ArrowDownLeft size={16}/></span><span><strong>Wallet recharge</strong><small>{item.recharge_code ?? `TXN-${String(item.id).padStart(5, '0')}`}</small></span></div></td><td>{dateTime(item.created_at)}</td><td><span className="resident-pill">{item.user_id ? 'TN' : 'RM'}</span> {item.user_id ? `Tenant #${item.user_id}` : 'Room-level recharge'}</td><td className="amount-positive">+{money(item.amount)}</td><td><span className={`status-badge ${item.status.toLowerCase()}`}><i/>{item.status.toLowerCase()}</span></td></tr>)}</tbody></table></div> : <EmptyState icon={ReceiptText} title="No matching transactions" description={recharges.length ? 'Try changing your search or status filter.' : 'Your wallet activity will appear after your first demo recharge.'} action={!recharges.length && accountLabel?.role === 'RESIDENT' ? <button className="button primary" onClick={() => setShowRecharge(true)}><Plus size={15}/> Add money</button> : undefined}/>}
            <div className="table-footer"><span>Showing <strong>{filteredTransactions.length}</strong> of <strong>{recharges.length}</strong> loaded transactions</span><span><ShieldCheck size={14}/> Simulated payments only</span></div>
          </article>
        </>}

        {page === 'rooms' && <>
          {pageIntro(accountLabel.role === 'ADMIN' ? 'ROOM CONFIGURATION' : 'ROOM CONFIGURATION', accountLabel.role === 'ADMIN' ? 'Room & meter details' : 'Your room & meter', accountLabel.role === 'ADMIN' ? 'Select any active room to inspect its meter, tariff, balance, residents, and activity.' : 'Control your simulated relay and review the meter currently assigned to your room.', accountLabel.role === 'ADMIN' ? <label className="room-admin-select"><span>Viewing room</span><select aria-label="Select room to inspect" value={meter?.id ?? ''} onChange={(event) => { const selected = roomDirectory.find((room) => room.meter?.id === Number(event.target.value)); if (selected?.meter) setMeter(selected.meter) }}><option value="">Select a room</option>{roomDirectory.filter((room) => room.is_active && room.meter?.is_active).map((room) => <option key={room.id} value={room.meter!.id}>{room.room_code} · Room {room.room_no} · {room.tenants.length} tenant{room.tenants.length === 1 ? '' : 's'}</option>)}</select></label> : <button className="button secondary" onClick={() => void loadMeters()}><Activity size={15}/> Refresh meter</button>)}
          {!meter ? <EmptyState icon={Home} title="No room linked" description="Seed the database to create the demo room and meter."/> : <>
            <div className="room-hero surface-card"><div className="room-hero-copy"><span className="room-tag"><Home size={13}/> {accountLabel.role === 'ADMIN' ? 'ADMIN ROOM VIEW' : 'RESIDENT SPACE'}</span><h2>Room {selectedRoomDetails?.room_no ?? meter.room_id}</h2><p>{accountLabel.role === 'ADMIN' ? <>Room <strong>{selectedRoomDetails?.room_code ?? ''}</strong> is linked to SmartVolt meter <strong>{meter.meter_code}</strong>. Inspect the room and manage its simulated relay below.</> : <>Your room is linked to SmartVolt meter <strong>{meter.meter_code}</strong>. Power changes on this page are simulated in software.</>}</p><div className="room-hero-meta"><span><i className="online-dot"/> Meter {apiConnected ? 'connected' : 'offline'}</span><span><ShieldCheck size={14}/> Prepaid meter</span></div></div><div className={`room-power-visual ${meter.power_status ? 'powered' : 'unpowered'}`}><div className="power-orbit orbit-a"/><div className="power-orbit orbit-b"/><div className="power-visual-core"><Zap size={36} fill="currentColor"/><small>SMART METER</small><strong>{meter.meter_code}</strong></div><span className="power-visual-state"><i/>{meter.power_status ? 'Power enabled' : 'Power disabled'}</span></div></div>
            <section className="room-detail-grid"><article className="panel surface-card"><SectionHeading title="Meter details" description="Current meter configuration."/><div className="detail-list"><DetailRow icon={Gauge} label="Meter ID" value={meter.meter_code}/><DetailRow icon={Home} label="Assigned room" value={selectedRoomDetails ? `${selectedRoomDetails.room_code} · Room ${selectedRoomDetails.room_no}` : `Room ${meter.room_id}`}/><DetailRow icon={CreditCard} label="Energy tariff" value={`${money(meter.tariff_per_kwh)} / kWh`}/><DetailRow icon={Wallet} label="Available balance" value={money(meter.current_balance)}/><DetailRow icon={Clock3} label="Created on" value={dateTime(meter.created_at)}/></div>{accountLabel.role === 'ADMIN' && selectedRoomDetails && <div className="room-tenant-list"><h3>Assigned tenants <span>{selectedRoomDetails.tenants.length}</span></h3>{selectedRoomDetails.tenants.length ? selectedRoomDetails.tenants.map((tenant) => <div className="room-tenant-row" key={tenant.id}><span className="tenant-avatar">{tenant.name.split(/\s+/).map((part) => part[0]).slice(0,2).join('').toUpperCase()}</span><span><strong>{tenant.name}</strong><small>{tenant.tenant_code ?? `User #${tenant.id}`} · @{tenant.username ?? 'no username'}</small></span></div>) : <p className="field-help">No active tenants are assigned to this room.</p>}</div>}</article><article className="panel surface-card relay-panel"><SectionHeading title="Power relay" description="A digital representation of room power."/><div className={`relay-status-banner ${meter.power_status ? 'enabled' : 'disabled'}`}><span className="relay-status-icon"><Power size={20}/></span><div><strong>{meter.power_status ? 'Power is enabled' : 'Power is disabled'}</strong><small>{meter.power_status ? 'Your simulated room relay is currently on.' : 'The simulated relay is off. Turn it on when ready.'}</small></div><span className="relay-led"><i/></span></div><div className="relay-large-control"><span className={`relay-switch ${meter.power_status ? 'on' : ''}`}><i/></span><div className="relay-control-copy"><strong>Room power</strong><small>{meter.power_status ? 'Currently on' : 'Currently off'}</small></div><button className={`button ${meter.power_status ? 'danger-quiet' : 'primary'}`} onClick={togglePower} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)}>{busy ? <LoaderCircle size={15} className="spin"/> : <Power size={15}/>} Turn {meter.power_status ? 'off' : 'on'}</button></div><p className="disclaimer-note"><ShieldCheck size={14}/> Software simulation only. No physical electrical relay is connected.</p></article></section>
            <article className="panel surface-card room-activity"><SectionHeading title="Recent room activity" description="Latest events recorded against this meter." action={<button className="text-button" onClick={() => navigate('usage')}>Usage history <ArrowUpRight size={14}/></button>}/><div className="activity-list"><div className="activity-item"><span className="activity-icon mint"><Check size={16}/></span><span><strong>Meter initialized</strong><small>{dateTime(meter.created_at)}</small></span><span className="activity-status">Registered</span></div>{readings.slice(0, 4).map((reading) => <div className="activity-item" key={reading.id}><span className="activity-icon violet"><Zap size={16}/></span><span><strong>Energy consumption recorded</strong><small>{dateTime(reading.created_at)} · {Number(reading.units_used).toFixed(3)} kWh</small></span><span className="activity-status">-{money(reading.cost)}</span></div>)}{recharges.slice(0, 3).map((item) => <div className="activity-item" key={`r-${item.id}`}><span className="activity-icon amber"><ArrowDownLeft size={16}/></span><span><strong>Wallet recharged</strong><small>{dateTime(item.created_at)} · {item.recharge_code ?? `TXN-${String(item.id).padStart(5, '0')}`} · {item.user_id ? `Tenant #${item.user_id}` : 'Room-level recharge'}</small></span><span className="activity-status positive">+{money(item.amount)}</span></div>)}</div></article>
          </>}
        </>}

        {page === 'settings' && <>
          {pageIntro('PREFERENCES', 'Workspace preferences', 'Adjust how SmartVolt looks and how it keeps you informed.', <span className="saved-indicator"><Check size={14}/> Preferences save automatically</span>)}
          <div className="settings-layout"><div className="settings-main"><article className="panel surface-card settings-panel"><SectionHeading title="My profile" description="Update the contact details associated with your SmartVolt account."/><form className="profile-form" onSubmit={(event) => void saveProfile(event)}><label htmlFor="profile-name">Full name</label><input id="profile-name" className="field-input" required minLength={1} maxLength={100} value={profileName} onChange={(event) => setProfileName(event.target.value)} /><label htmlFor="profile-username">Username</label><input id="profile-username" className="field-input" value={accountLabel.username} readOnly/><label htmlFor="profile-phone">Contact number</label><input id="profile-phone" className="field-input" type="tel" maxLength={15} value={profilePhone} onChange={(event) => setProfilePhone(event.target.value)} placeholder="Add a contact number"/><p className="field-help">{accountLabel.role === 'RESIDENT' ? `Tenant ID: ${accountLabel.tenant_code ?? 'Not assigned'} · Your role and room assignment can only be changed by an administrator.` : 'Your administrator identity and role are managed by the system.'}</p><button className="button primary" type="submit" disabled={profileBusy || !profileName.trim()}>{profileBusy ? <LoaderCircle size={15} className="spin"/> : <Check size={15}/>} Save profile</button></form></article><article className="panel surface-card settings-panel"><SectionHeading title="Change password" description="Use your current password to choose a new one. All active sessions will be signed out."/><form className="profile-form" onSubmit={(event) => void changePassword(event)}><label htmlFor="password-current">Current password</label><input id="password-current" className="field-input" type="password" autoComplete="current-password" required maxLength={200} value={passwordCurrent} onChange={(event) => setPasswordCurrent(event.target.value)}/><label htmlFor="password-new">New password</label><input id="password-new" className="field-input" type="password" autoComplete="new-password" required minLength={8} maxLength={200} value={passwordNew} onChange={(event) => setPasswordNew(event.target.value)}/><label htmlFor="password-confirm">Confirm new password</label><input id="password-confirm" className="field-input" type="password" autoComplete="new-password" required minLength={8} maxLength={200} value={passwordConfirm} onChange={(event) => setPasswordConfirm(event.target.value)}/>{passwordError && <div className="auth-error" role="alert">{passwordError}</div>}<button className="button secondary" type="submit" disabled={passwordBusy || !passwordCurrent || !passwordNew || !passwordConfirm}>{passwordBusy ? <LoaderCircle size={15} className="spin"/> : <LockKeyhole size={15}/>} Change password and sign out</button></form></article><article className="panel surface-card settings-panel"><SectionHeading title="Appearance" description="Choose an interface that works best for you."/><div className="theme-options"><button className={`theme-option ${theme === 'light' ? 'selected' : ''}`} onClick={() => setTheme('light')}><span className="theme-preview light-preview"><i/><i/><i/><b/></span><span><strong>Day mode</strong><small>Clean, bright workspace</small></span><span className="radio-dot"/></button><button className={`theme-option ${theme === 'dark' ? 'selected' : ''}`} onClick={() => setTheme('dark')}><span className="theme-preview dark-preview"><i/><i/><i/><b/></span><span><strong>Night mode</strong><small>Low-light, focused workspace</small></span><span className="radio-dot"/></button></div></article><article className="panel surface-card settings-panel"><SectionHeading title="Notifications" description="Choose which in-app reminders you want to see."/><div className="setting-row"><span className="setting-icon amber"><Bell size={17}/></span><span className="setting-copy"><strong>Low balance warning</strong><small>Show a reminder when the meter balance drops below ₹150.</small></span><button className={`switch-control ${lowBalanceAlert ? 'on' : ''}`} role="switch" aria-checked={lowBalanceAlert} aria-label="Low balance warning" onClick={() => setLowBalanceAlert((value) => !value)}><i/></button></div><div className="setting-row"><span className="setting-icon mint"><Activity size={17}/></span><span className="setting-copy"><strong>Live API status</strong><small>Display the connection state in the top navigation.</small></span><span className={`status-badge ${apiConnected ? 'successful' : 'failed'}`}><i/>{apiConnected ? 'Enabled' : 'Offline'}</span></div></article></div><aside className="settings-aside"><article className="panel surface-card account-card"><span className="account-avatar">{(accountLabel?.name ?? 'Ishan Srivastav').split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</span><span className="account-type">{accountLabel ? `${accountLabel.role} ACCOUNT` : 'DEMO ACCOUNT'}</span><h3>{accountLabel?.name ?? 'Ishan Srivastav'}</h3><p>{accountLabel?.role === 'ADMIN' ? 'Administrator workspace' : 'Resident workspace'}</p><div className="account-divider"/>{accountLabel.role === 'ADMIN' ? <><label>Signed-in identity</label><div className="identity-readonly">{accountLabel.username} · Administrator #{accountLabel.id}</div><small className="field-help">Use Admin Console → Recharge any meter to select a room or tenant. The signed-in administrator is recorded as the transaction actor.</small></> : <><label>Signed-in identity</label><div className="identity-readonly">{accountLabel.username} · User #{accountLabel.id}</div><small className="field-help">Your data access is limited to your assigned room.</small></>}<button className="button secondary full-width" onClick={() => navigate('support')}><LifeBuoy size={15}/> Get support</button></article><div className="settings-note"><ShieldCheck size={17}/><span><strong>Privacy by design</strong><small>Visual preferences are saved only in this browser. This app is still a simulation and is not connected to a physical meter.</small></span></div></aside></div>
        </>}

        {page === 'support' && <>
          {accountLabel.role === 'ADMIN'
            ? pageIntro('ADMIN SUPPORT DESK', 'Resident support requests', 'Review requests, reply with a solution, and track status across all rooms.', <span className="support-hours"><i/> Admin access verified</span>)
            : pageIntro('SUPPORT CENTER', 'How can we help?', 'Room-wide tickets are visible to your current roommates and administrators. Choose a private ticket for sensitive matters.', <span className="support-hours"><i/> Ticketing API available</span>)}
          {accountLabel.role === 'RESIDENT' && <div className="support-layout"><article className="panel surface-card ticket-form-panel"><SectionHeading title="Raise a ticket" description="Share a few details and we’ll log the request."/><form className="support-form" onSubmit={submitTicket}><label htmlFor="ticket-type">Issue category</label><div className="select-wrap"><select id="ticket-type" value={ticketType} onChange={(event) => setTicketType(event.target.value)}><option>Meter or power issue</option><option>Balance or recharge</option><option>Incorrect usage data</option><option>Room details</option><option>Other</option></select><ChevronDown size={15}/></div><label htmlFor="ticket-visibility">Who can see this ticket?</label><div className="select-wrap"><select id="ticket-visibility" value={ticketVisibility} onChange={(event) => setTicketVisibility(event.target.value as 'ROOM' | 'PRIVATE')}><option value="ROOM">My room and administrators</option><option value="PRIVATE">Only me and administrators (private)</option></select><ChevronDown size={15}/></div><label htmlFor="ticket-description">Describe the issue</label><textarea id="ticket-description" rows={5} required minLength={5} maxLength={5000} placeholder="Tell us what happened and when you first noticed it…" value={ticketDescription} onChange={(event) => setTicketDescription(event.target.value)}/><div className="form-helper"><span>{ticketDescription.length}/5000 characters</span><span><ShieldCheck size={13}/> Saved to the demo database</span></div><button className="button primary full-width" type="submit" disabled={submittingTicket || !ticketDescription.trim()}>{submittingTicket ? <LoaderCircle size={16} className="spin"/> : <Plus size={16}/>} Submit support ticket</button></form></article><aside className="support-aside"><div className="support-help-card"><span className="support-illustration"><LifeBuoy size={26}/></span><h3>Need a hand?</h3><p>Include the affected meter ID and any relevant details so the issue is easy to understand.</p><div><span><Clock3 size={15}/> Ticket ID generated automatically</span><span><ShieldCheck size={15}/> Replies are kept in the ticket timeline</span></div></div><article className="panel surface-card support-stat"><div><span>VISIBLE REQUESTS</span><strong>{tickets.length}</strong><small>Your tickets and room-wide requests</small></div><span className="metric-icon violet"><FileClock size={19}/></span></article></aside></div>}
          {accountLabel.role === 'ADMIN' && <div className="ticket-bucket-tabs" role="tablist" aria-label="Support request category"><button role="tab" aria-selected={ticketBucket === 'PENDING'} className={ticketBucket === 'PENDING' ? 'active' : ''} onClick={() => setTicketBucket('PENDING')}><span>Pending</span><strong>{pendingTicketCount}</strong></button><button role="tab" aria-selected={ticketBucket === 'CLOSED'} className={ticketBucket === 'CLOSED' ? 'active' : ''} onClick={() => setTicketBucket('CLOSED')}><span>Resolved & closed</span><strong>{closedTicketCount}</strong></button></div>}
          <article className="panel surface-card table-panel support-tickets-panel"><SectionHeading title={accountLabel.role === 'ADMIN' ? (ticketBucket === 'PENDING' ? 'Pending support requests' : 'Resolved & closed requests') : 'Your tickets & room requests'} description={accountLabel.role === 'ADMIN' ? (ticketBucket === 'PENDING' ? 'Requests that still need attention.' : 'Completed requests remain available for reference.') : 'Requests you created and room-wide tickets from your current room.'} action={<button className="button secondary" onClick={() => void loadTickets()}><Activity size={15}/> Refresh</button>}/>{visibleTickets.length ? <div className="ticket-list">{visibleTickets.map((ticket) => <article className="ticket-card" key={ticket.id}><div className="ticket-card-head"><span className="ticket-type-icon"><LifeBuoy size={17}/></span><div className="ticket-copy"><strong>{ticket.issue_type}</strong><small>{ticket.ticket_code} · Created {dateTime(ticket.created_at)} · Updated {dateTime(ticket.updated_at)}</small>{accountLabel.role === 'ADMIN' && <small className="ticket-requester">Submitted by {ticket.requester_name ?? `User #${ticket.user_id}`}{ticket.requester_username ? ` (@${ticket.requester_username})` : ''} · Room {ticket.room_no_snapshot ?? ticket.room_no ?? 'unassigned'}</small>}</div><div className="ticket-badges"><span className={`ticket-visibility ${ticket.visibility.toLowerCase()}`}>{ticket.visibility === 'PRIVATE' ? 'Private' : 'Room-wide'}</span><span className={`status-badge ${ticket.status.toLowerCase()}`}><i/>{ticket.status.replace(/_/g, ' ').toLowerCase()}</span></div></div><div className="ticket-meta-row"><span>Priority: <strong>{ticket.priority}</strong></span>{ticket.room_code_snapshot && <span>{ticket.room_code_snapshot} · Room {ticket.room_no_snapshot ?? '—'}</span>}</div><div className="ticket-conversation">{(ticket.messages ?? []).map((message) => <div className={`ticket-message ${message.author_role === 'ADMIN' ? 'admin-message' : ''}`} key={message.id}><div className="ticket-message-head"><strong>{message.author_name}</strong><span>{message.author_role === 'ADMIN' ? 'Administrator' : 'Resident'} · {dateTime(message.created_at)}</span></div><p>{message.message}</p></div>)}</div><div className="ticket-actions">{accountLabel.role === 'ADMIN' && <div className="ticket-admin-controls"><label>Status<select value={ticket.status} disabled={ticketActionBusy === ticket.id} onChange={(event) => void updateTicket(ticket.id, { status: event.target.value as TicketStatus })}><option value="OPEN">Open</option><option value="IN_PROGRESS">In progress</option><option value="AWAITING_RESIDENT">Awaiting resident</option><option value="RESOLVED">Resolved</option><option value="CLOSED">Closed</option></select></label><label>Priority<select value={ticket.priority} disabled={ticketActionBusy === ticket.id} onChange={(event) => void updateTicket(ticket.id, { priority: event.target.value as Ticket['priority'] })}><option value="LOW">Low</option><option value="NORMAL">Normal</option><option value="HIGH">High</option><option value="URGENT">Urgent</option></select></label></div>}<form className="ticket-reply-form" onSubmit={(event) => void replyToTicket(event, ticket.id)}><label htmlFor={`ticket-reply-${ticket.id}`}>{accountLabel.role === 'ADMIN' ? 'Reply with an update or solution' : 'Reply to the conversation'}</label><textarea id={`ticket-reply-${ticket.id}`} rows={2} maxLength={5000} value={ticketReplies[ticket.id] ?? ''} onChange={(event) => setTicketReplies((current) => ({ ...current, [ticket.id]: event.target.value }))} placeholder={ticket.status === 'CLOSED' ? 'This ticket is closed. An administrator must reopen it to continue.' : 'Write a reply…'} disabled={ticket.status === 'CLOSED' || ticketActionBusy === ticket.id}/><button className="button primary" type="submit" disabled={ticket.status === 'CLOSED' || ticketActionBusy === ticket.id || !(ticketReplies[ticket.id] ?? '').trim()}>{ticketActionBusy === ticket.id ? <LoaderCircle size={15} className="spin"/> : <ArrowRight size={15}/>} Send reply</button></form></div></article>)}</div> : <EmptyState icon={FileClock} title={accountLabel.role === 'ADMIN' ? (ticketBucket === 'PENDING' ? 'No pending requests' : 'No resolved or closed requests') : 'No support tickets yet'} description={accountLabel.role === 'ADMIN' ? (ticketBucket === 'PENDING' ? 'New and in-progress resident requests will appear here.' : 'Resolved and closed requests are kept here for reference.') : 'Create a request or check back when a roommate raises a room-wide issue.'}/>}</article>
        </>}

        {page === 'simulation' && <LoadLabPage account={accountLabel} meter={meter} meters={meters} onSelectMeter={(meterId) => setMeter(meters.find((item) => item.id === meterId) ?? null)} onNotice={setNotice} onRefresh={refresh}/>}
        {page === 'admin' && accountLabel.role === 'ADMIN' && <AdminPage account={accountLabel} onNotice={setNotice} onRefresh={refresh}/>}

        <footer className="page-footer"><span>© 2026 SmartVolt <span className="footer-separator">·</span> Prepaid energy, simplified</span><span><i className={apiConnected ? 'connected' : ''}/> {apiConnected ? 'Connected to your demo API' : 'Waiting for API connection'}</span></footer>
      </div>
    </main>

    {showRecharge && accountLabel?.role === 'RESIDENT' && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setShowRecharge(false)}><section className="modal surface-card" role="dialog" aria-modal="true" aria-labelledby="recharge-title"><div className="modal-heading"><div className="modal-icon"><Wallet size={21}/></div><button className="close-modal icon-button" onClick={() => setShowRecharge(false)} aria-label="Close"><X size={18}/></button></div><span className="modal-kicker">METER WALLET</span><h2 id="recharge-title">Top up your meter</h2><p>This adds simulated credit to room {meter?.room_id}. No real payment is processed.</p><form onSubmit={submitRecharge}><label htmlFor="recharge-amount">Recharge amount</label><div className="amount-input"><span>₹</span><input id="recharge-amount" inputMode="decimal" type="number" min="1" max="100000" step="0.01" required value={rechargeAmount} onChange={(event) => setRechargeAmount(event.target.value)}/></div><div className="amount-presets">{['100','200','500','1000'].map((amount) => <button type="button" key={amount} className={rechargeAmount === amount ? 'picked' : ''} onClick={() => setRechargeAmount(amount)}>₹{amount}</button>)}</div><p className="form-helper">Recharge is associated with your signed-in account: {accountLabel.username}. Only your assigned room meter can be recharged from this screen.</p><button className="button primary full-width submit-recharge" type="submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <Plus size={17}/>} Confirm demo recharge <ArrowRight size={15}/></button><div className="secure-note"><ShieldCheck size={14}/> Simulated transaction · No payment gateway connected</div></form></section></div>}
  </div>
}

function PeriodControl({ period, setPeriod }: { period: '1d' | '7d' | '30d'; setPeriod: (value: '1d' | '7d' | '30d') => void }) {
  return <div className="period-control" role="group" aria-label="Report period">{(['1d','7d','30d'] as const).map((item) => <button key={item} className={period === item ? 'selected' : ''} onClick={() => setPeriod(item)}>{item === '1d' ? 'Today' : item === '7d' ? '7 days' : '30 days'}</button>)}</div>
}

function MeterStatusCard({ meter, busy, onToggle }: { meter: Meter; busy: boolean; onToggle: () => void }) {
  return <article className="panel surface-card meter-status-panel"><SectionHeading title="Meter status" description="Software relay overview." action={<span className="live-label"><i/> SIMULATED</span>}/><div className={`meter-illustration ${meter.power_status ? 'is-on' : 'is-off'}`}><div className="meter-glow"/><div className="meter-ring"><div className="meter-core"><Zap size={31} fill="currentColor"/><small>SMART METER</small><strong>{meter.meter_code}</strong></div></div><span className="meter-decoration dot-one"/><span className="meter-decoration dot-two"/><span className="meter-decoration ring-small"/></div><div className="status-list"><div><span><i className="status-check"><Check size={11}/></i> Connection</span><strong>Connected</strong></div><div><span><i className={`status-circle ${meter.power_status ? 'green' : 'gray'}`}/>Power relay</span><strong>{meter.power_status ? 'Enabled' : 'Disabled'}</strong></div><div><span><i className="status-circle green"/>Meter tariff</span><strong>{money(meter.tariff_per_kwh)} / kWh</strong></div></div><button className={`button ${meter.power_status ? 'secondary' : 'primary'} full-width`} onClick={onToggle} disabled={busy || (Number(meter.current_balance) <= 0 && !meter.power_status)}>{busy ? <LoaderCircle size={15} className="spin"/> : <Power size={15}/>} Turn power {meter.power_status ? 'off' : 'on'}</button><p className="panel-note">No physical electrical relay is connected.</p></article>
}

function TransactionList({ items }: { items: Recharge[] }) {
  return <div className="transaction-list">{items.map((item) => <div className="transaction-row" key={item.id}><div className="transaction-icon"><ArrowDownLeft size={17}/></div><div className="transaction-main"><strong>Wallet recharge</strong><small>{dateTime(item.created_at)} · {item.recharge_code ?? `TXN-${String(item.id).padStart(5, '0')}`} · {item.user_id ? `Tenant #${item.user_id}` : 'Room-level recharge'}</small></div><div className="transaction-amount"><strong>+{money(item.amount)}</strong><small className={`transaction-status ${item.status.toLowerCase()}`}><i/>{item.status.toLowerCase()}</small></div></div>)}</div>
}

function DetailRow({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return <div className="detail-row"><span className="detail-icon"><Icon size={16}/></span><span className="detail-label">{label}</span><strong>{value}</strong></div>
}
