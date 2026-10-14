import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Activity, CalendarDays, Fan, Gauge, Laptop, Lightbulb, LoaderCircle, Pause, Play, Plus, Power, Router, ShieldCheck, Sparkles, ThermometerSun, UserRound, Zap } from 'lucide-react'

type Notice = { type: 'success' | 'error' | 'info'; text: string }
type Meter = { id: number; room_id: number; current_balance: string; power_status: boolean; tariff_per_kwh: string; created_at: string }
type Appliance = { id: string; name: string; watts: number; category: string; hint: string }
type ActiveAppliance = { id: number; meter_id: number; appliance_id: string; appliance_name: string; watts: number; started_at: string }
type Block = { label: string; start_min: number; end_min: number; appliance_ids: string[] }
type Scenario = { id: number; slug: string; name: string; audience: 'ADMIN' | 'RESIDENT'; description: string; blocks: Block[]; is_builtin: boolean; owner_user_id: number | null }
type Account = { id: number; name: string; username: string; role: 'ADMIN' | 'RESIDENT'; room_id: number | null }
type LoginResponse = { access_token: string; account: Account }
type Props = { meter: Meter | null; meters: Meter[]; onSelectMeter: (meterId: number) => void; onNotice: (notice: Notice) => void; onRefresh: () => Promise<void> }

const TOKEN_KEY = 'smartvolt:accessToken'
const ACCOUNT_KEY = 'smartvolt:account'
const SPEEDS = [{ value: 1, label: 'Real time' }, { value: 60, label: '1 min/sec' }, { value: 300, label: '5 min/sec' }, { value: 3600, label: '1 hr/sec' }]
const DEFAULT_HOURS: Record<string, number> = { fan: 8, tube: 5, lamp: 3, laptop: 4, phone: 2, router: 24, cooler: 0, kettle: 0.25, iron: 0, speaker: 1 }
const SLOT_START: Record<string, number> = { router: 0, fan: 0, tube: 360, lamp: 1080, laptop: 1020, phone: 360, cooler: 660, kettle: 360, iron: 600, speaker: 1200 }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
function readAccount(): Account | null {
  try { return JSON.parse(localStorage.getItem(ACCOUNT_KEY) ?? 'null') as Account | null } catch { return null }
}
function localISODate(date = new Date()): string {
  const year = date.getFullYear(); const month = String(date.getMonth() + 1).padStart(2, '0'); const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const money = (amount: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(amount)

export default function LoadLabPage({ meter: selectedMeter, meters, onSelectMeter, onNotice, onRefresh }: Props) {
  const [appliances, setAppliances] = useState<Appliance[]>([])
  const [activeLoads, setActiveLoads] = useState<ActiveAppliance[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [account, setAccount] = useState<Account | null>(readAccount)
  const [audience, setAudience] = useState<'ADMIN' | 'RESIDENT'>(readAccount()?.role ?? 'RESIDENT')
  const meter = account?.role === 'RESIDENT'
    ? meters.find((item) => item.room_id === account.room_id) ?? null
    : selectedMeter
  const selectableMeters = account?.role === 'RESIDENT'
    ? meters.filter((item) => item.room_id === account.room_id)
    : meters
  const hasSession = Boolean(account && localStorage.getItem(TOKEN_KEY))
  const [selectedScenario, setSelectedScenario] = useState('')
  const [simulationDate, setSimulationDate] = useState(localISODate())
  const [applyAllRooms, setApplyAllRooms] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loginUsername, setLoginUsername] = useState('ishan')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [templateName, setTemplateName] = useState('My daily routine')
  const [hours, setHours] = useState<Record<string, number>>({ ...DEFAULT_HOURS })
  const [startHours, setStartHours] = useState<Record<string, number>>(Object.fromEntries(Object.entries(SLOT_START).map(([id, minute]) => [id, minute / 60])))
  const [savingTemplate, setSavingTemplate] = useState(false)
  const inFlight = useRef(false)
  const ticks = useRef(0)
  const refreshRef = useRef(onRefresh)
  refreshRef.current = onRefresh

  const currentWatts = activeLoads.reduce((total, item) => total + item.watts, 0)
  const enabledIds = useMemo(() => new Set(activeLoads.map((item) => item.appliance_id)), [activeLoads])
  const selected = scenarios.find((item) => String(item.id) === selectedScenario) ?? scenarios[0] ?? null
  const projectedUnits = selected ? selected.blocks.reduce((total, item) => {
    const watts = item.appliance_ids.reduce((sum, id) => sum + (appliances.find((appliance) => appliance.id === id)?.watts ?? 0), 0)
    return total + (watts * Math.max(0, item.end_min - item.start_min)) / 60000
  }, 0) : 0
  const projectedCost = projectedUnits * Number(meter?.tariff_per_kwh ?? 8)

  useEffect(() => {
    if (account?.role === 'RESIDENT' && meter && selectedMeter?.id !== meter.id) onSelectMeter(meter.id)
  }, [account?.role, account?.room_id, meter?.id, selectedMeter?.id, onSelectMeter])

  useEffect(() => {
    let alive = true
    setLoading(true)
    const load = async () => {
      try {
        const [catalogue, templates, active] = await Promise.all([
          request<Appliance[]>('/simulation/appliances'),
          request<Scenario[]>(`/simulation/scenarios?audience=${audience}`),
          meter && hasSession ? request<ActiveAppliance[]>(`/meters/${meter.id}/simulation/appliances`) : Promise.resolve([]),
        ])
        if (!alive) return
        setAppliances(catalogue); setScenarios(templates); setActiveLoads(active)
        setSelectedScenario((old) => templates.some((item) => String(item.id) === old) ? old : String(templates[0]?.id ?? ''))
      } catch (error) { if (alive) onNotice({ type: 'error', text: (error as Error).message }) }
      finally { if (alive) setLoading(false) }
    }
    void load()
    return () => { alive = false }
  }, [meter?.id, audience, account?.id, hasSession, onNotice])

  useEffect(() => {
    if (!running || !meter || !meter.power_status || currentWatts <= 0) return
    let active = true
    const timer = window.setInterval(async () => {
      if (inFlight.current || !active) return
      inFlight.current = true
      try {
        const result = await request<{ meter: Meter; live_watts: number; reading: unknown | null }>(`/meters/${meter.id}/simulation/tick`, {
          method: 'POST', body: JSON.stringify({ elapsed_seconds: speed }),
        })
        ticks.current += 1
        if (!result.meter.power_status) {
          setRunning(false)
          setActiveLoads([])
          onNotice({ type: 'info', text: 'The prepaid balance is exhausted. SmartVolt switched the simulated relay off.' })
        }
        if (ticks.current % 5 === 0 || !result.meter.power_status) await refreshRef.current()
      } catch (error) {
        setRunning(false); onNotice({ type: 'error', text: (error as Error).message })
      } finally { inFlight.current = false }
    }, 1000)
    return () => { active = false; window.clearInterval(timer) }
  }, [running, meter?.id, meter?.power_status, currentWatts, speed, onNotice])

  async function toggleAppliance(appliance: Appliance) {
    if (!meter) { onNotice({ type: 'error', text: 'There is no meter to attach this appliance to. Create a room first.' }); return }
    try {
      const next = await request<ActiveAppliance[]>(`/meters/${meter.id}/simulation/appliances/${appliance.id}`, {
        method: 'PUT', body: JSON.stringify({ enabled: !enabledIds.has(appliance.id) }),
      })
      setActiveLoads(next)
      onNotice({ type: 'success', text: `${appliance.name} ${enabledIds.has(appliance.id) ? 'switched off' : 'switched on'}${!enabledIds.has(appliance.id) ? ` · ${appliance.watts} W` : ''}.` })
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
  }

  async function allOff() {
    if (!meter) return
    setRunning(false)
    try {
      let next: ActiveAppliance[] = activeLoads
      for (const appliance of activeLoads) next = await request<ActiveAppliance[]>(`/meters/${meter.id}/simulation/appliances/${appliance.appliance_id}`, { method: 'PUT', body: JSON.stringify({ enabled: false }) })
      setActiveLoads(next); await refreshRef.current()
      onNotice({ type: 'success', text: 'All appliances are off.' })
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
  }

  async function applyScenario() {
    if (!selected || !meter) return
    try {
      const result = await request<{ simulation_date: string; results: Array<{ meter_id: number; units_used: string; cost: string; reading_count: number; partial: boolean; historical_only: boolean }> }>(`/simulation/scenarios/${selected.id}/apply`, {
        method: 'POST', body: JSON.stringify({ meter_id: meter.id, apply_all: applyAllRooms && account?.role === 'ADMIN', simulation_date: simulationDate }),
      })
      const item = result.results[0]
      if (item) {
        const totalUnits = result.results.reduce((total, row) => total + Number(row.units_used), 0)
        const totalCost = result.results.reduce((total, row) => total + Number(row.cost), 0)
        const readingCount = result.results.reduce((total, row) => total + row.reading_count, 0)
        const isHistorical = result.results.every((row) => row.historical_only)
        const wasPartial = result.results.some((row) => row.partial)
        onNotice({ type: wasPartial ? 'info' : 'success', text: isHistorical
          ? `Saved ${selected.name} as historical telemetry for ${simulationDate}: ${totalUnits.toFixed(3)} kWh, estimated ${money(totalCost)} across ${result.results.length} meter(s). Current wallets unchanged.`
          : `Applied ${selected.name}: ${totalUnits.toFixed(3)} kWh across ${readingCount} readings; ${money(totalCost)} deducted across ${result.results.length} meter(s).${wasPartial ? ' Some meters ran out of funds.' : ''}` })
      }
      await refreshRef.current()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoginBusy(true)
    try {
      const result = await request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username: loginUsername, password: loginPassword }) })
      localStorage.setItem(TOKEN_KEY, result.access_token); localStorage.setItem(ACCOUNT_KEY, JSON.stringify(result.account))
      setAccount(result.account); setAudience(result.account.role); setLoginPassword(''); window.dispatchEvent(new Event('smartvolt:auth-changed'))
      onNotice({ type: 'success', text: `Signed in as ${result.account.username}. You can save personal scenario templates now.` })
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setLoginBusy(false) }
  }

  function signOut() {
    localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ACCOUNT_KEY); setAccount(null); setAudience('RESIDENT'); window.dispatchEvent(new Event('smartvolt:auth-changed'))
    setActiveLoads([]); setRunning(false); window.dispatchEvent(new Event('smartvolt:auth-changed'))
    onNotice({ type: 'info', text: 'Signed out. Sign in to operate a meter or apply a daily scenario.' })
  }

  async function saveTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!account || !localStorage.getItem(TOKEN_KEY)) { onNotice({ type: 'error', text: 'Sign in first to save a personal template.' }); return }
    const blocks: Block[] = appliances.flatMap((appliance) => {
      const duration = Math.min(24, Math.max(0, Number(hours[appliance.id] ?? 0)))
      if (!duration) return []
      const defaultStart = (SLOT_START[appliance.id] ?? 0) / 60
      const start = Math.min(1439, Math.max(0, Math.round(Number(startHours[appliance.id] ?? defaultStart) * 60)))
      const end = Math.min(1440, start + Math.round(duration * 60))
      return end > start ? [{ label: appliance.name, start_min: start, end_min: end, appliance_ids: [appliance.id] }] : []
    })
    if (!blocks.length) { onNotice({ type: 'error', text: 'Give at least one appliance some daily hours.' }); return }
    setSavingTemplate(true)
    try {
      const template = await request<Scenario>('/simulation/scenarios', {
        method: 'POST', body: JSON.stringify({ name: templateName, audience: account.role, description: 'Custom daily appliance schedule created in the SmartVolt Load Lab.', blocks }),
      })
      setScenarios((current) => [template, ...current]); setSelectedScenario(String(template.id))
      onNotice({ type: 'success', text: `Saved “${template.name}” to the database for ${account.role.toLowerCase()} templates.` })
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSavingTemplate(false) }
  }

  return <div className="feature-stack">
    <section className={`feature-hero surface-card ${currentWatts > 0 ? 'feature-hero-live' : ''}`}>
      <span className="feature-icon"><Zap size={22}/></span><div><span className="eyebrow">APPLIANCE SIMULATOR</span><h2>Load Lab</h2><p>Turn on appliances and watch simulated energy use reduce the prepaid balance. Nothing is connected to physical hardware.</p></div>
      <div className="load-live-metric"><strong>{currentWatts.toLocaleString('en-IN')} <small>W</small></strong><span>{currentWatts > 0 ? 'Live connected load' : 'No active load'}</span></div>
    </section>
    {!hasSession && <section className="panel surface-card feature-panel load-auth-panel">
      <div className="feature-section-heading"><div><h2>Sign in to operate the meter</h2><p>Resident accounts can operate their assigned room. Administrators can simulate any room and apply hostel-wide scenarios.</p></div><ShieldCheck size={19}/></div>
      <form className="feature-form feature-login-inline" onSubmit={signIn}>
        <label>Username<input className="field-input" value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} autoComplete="username" required/></label>
        <label>Password<input className="field-input" type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} autoComplete="current-password" required/></label>
        <button className="button primary" type="submit" disabled={loginBusy}>{loginBusy ? <LoaderCircle size={15} className="spin"/> : <UserRound size={15}/>} Sign in</button>
      </form>
      <p className="feature-footnote">Demo accounts after seeding: resident <code>ishan</code> / <code>resident123</code>; admin <code>admin</code> / your configured admin password.</p>
    </section>}
    <section className="load-control-grid">
      <article className="panel surface-card feature-panel load-run-panel">
        <div className="feature-section-heading"><div><h2>Simulation clock</h2><p>Set the pace, run the clock, and meter units accumulate against the wallet.</p></div><span className={`status-badge ${running ? 'successful' : 'failed'}`}><i/>{running ? 'Running' : 'Paused'}</span></div>
        <div className="speed-options" role="group" aria-label="Simulation speed">{SPEEDS.map((option) => <button type="button" key={option.value} className={speed === option.value ? 'selected' : ''} onClick={() => setSpeed(option.value)}>{option.label}</button>)}</div>
        <div className="load-clock-actions"><button className="button primary" onClick={() => setRunning((value) => !value)} disabled={!hasSession || !meter || !meter.power_status || currentWatts === 0}>{running ? <Pause size={15}/> : <Play size={15}/>} {running ? 'Pause clock' : 'Run clock'}</button><button className="button secondary" onClick={() => void allOff()} disabled={!hasSession || !activeLoads.length}><Power size={15}/> All off</button></div>
        <div className="load-meter-strip"><span><Gauge size={15}/> Room {meter?.room_id ?? '—'} · Meter #{meter?.id ?? '—'}</span><strong>{money(Number(meter?.tariff_per_kwh ?? 8))}/kWh</strong><span>Balance <strong>{money(Number(meter?.current_balance ?? 0))}</strong></span></div>
        {!meter?.power_status && <p className="feature-inline-warning">Turn the simulated room power on from Overview before running active appliances.</p>}
        {meter && Number(meter.current_balance) <= 0 && <p className="feature-inline-warning">This prepaid meter is empty. Recharge it before running a scenario.</p>}
      </article>
      <article className="panel surface-card feature-panel scenario-panel">
        <div className="feature-section-heading"><div><h2>Daily scenario</h2><p>Apply a complete load profile to this meter.</p></div><CalendarDays size={19}/></div>
        <label className="feature-label">Target meter<select className="field-input" value={meter?.id ?? ''} onChange={(event) => { setApplyAllRooms(false); onSelectMeter(Number(event.target.value)) }} disabled={!selectableMeters.length}>{selectableMeters.map((item) => <option key={item.id} value={item.id}>Room {item.room_id} · Meter #{item.id}</option>)}</select></label>
        {account?.role === 'ADMIN' && <label className="feature-checkbox"><input type="checkbox" checked={applyAllRooms} onChange={(event) => setApplyAllRooms(event.target.checked)}/> Apply to every room (admin)</label>}
        <label className="feature-label">Template<select className="field-input" value={selected?.id ?? ''} onChange={(event) => setSelectedScenario(event.target.value)} disabled={loading || scenarios.length === 0}>{scenarios.map((item) => <option value={item.id} key={item.id}>{item.name}{item.is_builtin ? ' · built-in' : ' · custom'}</option>)}</select></label>
        {selected && <><p className="scenario-description">{selected.description}</p><div className="scenario-estimate"><div><span>Estimated daily use</span><strong>{projectedUnits.toFixed(2)} kWh</strong></div><div><span>Estimated cost</span><strong>{money(projectedCost)}</strong></div></div><div className="scenario-schedule">{selected.blocks.slice(0, 5).map((block) => <div key={`${block.label}-${block.start_min}`}><span>{block.label}</span><small>{formatMinute(block.start_min)}–{formatMinute(block.end_min)}</small></div>)}{selected.blocks.length > 5 && <small className="feature-footnote">+ {selected.blocks.length - 5} more schedule blocks</small>}</div></>}
        <label className="feature-label">Simulation date<input className="field-input" type="date" value={simulationDate} max={localISODate()} onChange={(event) => setSimulationDate(event.target.value)}/></label>
        {simulationDate < localISODate() && <p className="feature-inline-info">Historical mode: readings are backfilled on this date and the current wallet is not charged again.</p>}
        <button className="button primary full-width" onClick={() => void applyScenario()} disabled={!hasSession || !meter || !selected || loading}><Zap size={15}/> Apply daily scenario</button>
      </article>
    </section>
    <section className="panel surface-card feature-panel">
      <div className="feature-section-heading"><div><h2>Appliance board</h2><p>Toggle the devices that are drawing power right now. Wattages are representative simulation values.</p></div><span className={`load-status-pill ${currentWatts > 0 ? 'active' : ''}`}><i/>{activeLoads.length} active</span></div>
      {loading ? <div className="feature-empty"><LoaderCircle className="spin" size={20}/> Loading appliance catalogue…</div> : <div className="appliance-grid">{appliances.map((item) => <article className={`appliance-card ${enabledIds.has(item.id) ? 'active' : ''}`} key={item.id}><span className="appliance-card-icon">{iconFor(item.id)}</span><div className="appliance-card-copy"><strong>{item.name}</strong><span>{item.category}</span><small>{item.hint}</small></div><div className="appliance-card-bottom"><strong>{item.watts.toLocaleString('en-IN')} W</strong><button type="button" className={`switch-control ${enabledIds.has(item.id) ? 'on' : ''}`} role="switch" aria-checked={enabledIds.has(item.id)} aria-label={`${enabledIds.has(item.id) ? 'Turn off' : 'Turn on'} ${item.name}`} onClick={() => void toggleAppliance(item)} disabled={!hasSession || !meter || !meter.power_status || Number(meter.current_balance) <= 0}><i/></button></div></article>)}</div>}
      <p className="feature-footnote"><Activity size={14}/> Low-watt loads are accumulated between meter readings so rounding doesn’t erase real-time simulation use.</p>
    </section>
    <section className="feature-columns">
      <article className="panel surface-card feature-panel">
        <div className="feature-section-heading"><div><h2>Build a personal template</h2><p>Choose how long each appliance should run during a typical day.</p></div><Sparkles size={19}/></div>
        {!hasSession ? <div className="feature-notice"><UserRound size={16}/><span>Sign in above to save resident templates or admin templates. Templates are persisted in the database.</span></div> : <div className="feature-account-row"><span className="feature-tenant-avatar">{account!.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</span><span><strong>{account!.name}</strong><small>{account!.username} · {account!.role.toLowerCase()} templates</small></span><button className="button secondary" onClick={signOut}>Sign out</button></div>}
        <form className="feature-form" onSubmit={saveTemplate}>
          <label>Template name<input className="field-input" value={templateName} onChange={(event) => setTemplateName(event.target.value)} required minLength={3} maxLength={100}/></label>
          <div className="custom-load-list">{appliances.map((appliance) => <label key={appliance.id}><span>{appliance.name}<small>{appliance.watts} W</small></span><div className="custom-load-fields"><input aria-label={`${appliance.name} start hour`} type="number" min="0" max="23.75" step="0.25" value={startHours[appliance.id] ?? 0} onChange={(event) => setStartHours((current) => ({ ...current, [appliance.id]: Number(event.target.value) }))}/><input aria-label={`${appliance.name} hours per day`} type="number" min="0" max="24" step="0.25" value={hours[appliance.id] ?? 0} onChange={(event) => setHours((current) => ({ ...current, [appliance.id]: Number(event.target.value) }))}/></div><small>start · hours/day</small></label>)}</div>
          <button className="button primary" type="submit" disabled={savingTemplate || !hasSession}>{savingTemplate ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} Save template to database</button>
        </form>
      </article>
      <aside className="panel surface-card feature-panel scenario-notes-panel"><div className="feature-section-heading"><div><h2>How billing works</h2><p>Simulation rules at a glance.</p></div><ShieldCheck size={18}/></div><div className="feature-rule"><span className="rule-number">01</span><div><strong>Watts become kWh</strong><p>Consumption equals total active watts × simulated seconds ÷ 3,600,000.</p></div></div><div className="feature-rule"><span className="rule-number">02</span><div><strong>Wallet uses the room tariff</strong><p>The server records meter readings and debits the same prepaid wallet already used by SmartVolt.</p></div></div><div className="feature-rule"><span className="rule-number">03</span><div><strong>Empty wallet means power off</strong><p>When the balance reaches zero, the simulated relay turns off and active appliances are cleared.</p></div></div><div className="feature-rule"><span className="rule-number">04</span><div><strong>Past dates are historical only</strong><p>Replaying a prior day fills analytics without charging the current wallet a second time.</p></div></div></aside>
    </section>
  </div>
}

function formatMinute(minutes: number): string {
  const hour = Math.floor(minutes / 60) % 24; const minute = minutes % 60
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}
function iconFor(id: string) {
  switch (id) {
    case 'fan': return <Fan size={20}/>
    case 'tube': case 'lamp': return <Lightbulb size={20}/>
    case 'laptop': return <Laptop size={20}/>
    case 'router': return <Router size={20}/>
    case 'cooler': return <ThermometerSun size={20}/>
    default: return <Zap size={20}/>
  }
}
