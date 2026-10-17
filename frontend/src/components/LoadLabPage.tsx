import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Activity, CalendarDays, Fan, Gauge, Laptop, Lightbulb, LoaderCircle, Pause, Play, Plus, Power, Router, ShieldCheck, Sparkles, ThermometerSun, Zap } from 'lucide-react'

type Notice = { type: 'success' | 'error' | 'info'; text: string }
type Meter = { id: number; room_id: number; current_balance: string; power_status: boolean; tariff_per_kwh: string; created_at: string }
type Appliance = { id: string; name: string; watts: number; category: string; hint: string }
type ActiveAppliance = { id: number; meter_id: number; appliance_id: string; appliance_name: string; watts: number; quantity: number; started_at: string }
type Block = { label: string; start_min: number; end_min: number; appliance_ids: string[]; appliance_quantities?: Record<string, number> }
type Scenario = { id: number; slug: string; name: string; audience: 'ADMIN' | 'RESIDENT'; description: string; blocks: Block[]; is_builtin: boolean; owner_user_id: number | null }
type Account = { id: number; name: string; username: string; role: 'ADMIN' | 'RESIDENT'; room_id: number | null }
type Props = { account: Account; meter: Meter | null; meters: Meter[]; onSelectMeter: (meterId: number) => void; onNotice: (notice: Notice) => void; onRefresh: () => Promise<void> }

const TOKEN_KEY = 'smartvolt:accessToken'
const ACCOUNT_KEY = 'smartvolt:account'
const SPEEDS = [{ value: 1, label: 'Real time' }, { value: 60, label: '1 min/sec' }, { value: 300, label: '5 min/sec' }, { value: 3600, label: '1 hr/sec' }]
const DEFAULT_HOURS: Record<string, number> = { fan: 8, tube: 5, lamp: 3, laptop: 4, phone: 2, router: 24, cooler: 0, kettle: 0.25, iron: 0, speaker: 1 }
const SLOT_START: Record<string, number> = { router: 0, fan: 0, tube: 360, lamp: 1080, laptop: 1020, phone: 360, cooler: 660, kettle: 360, iron: 600, speaker: 1200 }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    if (response.status === 401 && token) {
      sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(ACCOUNT_KEY)
      window.dispatchEvent(new Event('smartvolt:auth-expired'))
    }
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
function localISODate(date = new Date()): string {
  const year = date.getFullYear(); const month = String(date.getMonth() + 1).padStart(2, '0'); const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const money = (amount: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(amount)

export default function LoadLabPage({ account, meter: selectedMeter, meters, onSelectMeter, onNotice, onRefresh }: Props) {
  const [appliances, setAppliances] = useState<Appliance[]>([])
  const [activeLoads, setActiveLoads] = useState<ActiveAppliance[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const audience: 'ADMIN' | 'RESIDENT' = account.role
  const meter = account.role === 'RESIDENT'
    ? meters.find((item) => item.room_id === account.room_id) ?? null
    : selectedMeter
  const selectableMeters = account.role === 'RESIDENT'
    ? meters.filter((item) => item.room_id === account.room_id)
    : meters
  const hasSession = Boolean(sessionStorage.getItem(TOKEN_KEY))
  const [selectedScenario, setSelectedScenario] = useState('')
  const [simulationDate, setSimulationDate] = useState(localISODate())
  const [applyAllRooms, setApplyAllRooms] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)
  const [templateName, setTemplateName] = useState('My daily routine')
  const [hours, setHours] = useState<Record<string, number>>({ ...DEFAULT_HOURS })
  const [startTimes, setStartTimes] = useState<Record<string, string>>(Object.fromEntries(Object.entries(SLOT_START).map(([id, minute]) => [id, formatMinute(minute)])))
  const [boardQuantities, setBoardQuantities] = useState<Record<string, number>>({})
  const [templateQuantities, setTemplateQuantities] = useState<Record<string, number>>({})
  const [savingTemplate, setSavingTemplate] = useState(false)
  const inFlight = useRef(false)
  const ticks = useRef(0)
  const refreshRef = useRef(onRefresh)
  refreshRef.current = onRefresh

  const currentWatts = activeLoads.reduce((total, item) => total + item.watts * item.quantity, 0)
  const activeById = useMemo(() => new Map<string, ActiveAppliance>(activeLoads.map((item) => [item.appliance_id, item] as const)), [activeLoads])
  const activeUnitCount = activeLoads.reduce((total, item) => total + item.quantity, 0)
  const selected = scenarios.find((item) => String(item.id) === selectedScenario) ?? scenarios[0] ?? null
  const projectedUnits = selected ? selected.blocks.reduce((total, item) => {
    const watts = item.appliance_ids.reduce((sum, id) => sum + (appliances.find((appliance) => appliance.id === id)?.watts ?? 0) * Math.max(1, item.appliance_quantities?.[id] ?? 1), 0)
    return total + (watts * Math.max(0, item.end_min - item.start_min)) / 60000
  }, 0) : 0
  const projectedCost = projectedUnits * Number(meter?.tariff_per_kwh ?? 8)
  const templateProjectedUnits = appliances.reduce((total, appliance) => {
    const rawQuantity = Number(templateQuantities[appliance.id] ?? 1)
    const quantity = Math.min(100, Math.max(0, Number.isFinite(rawQuantity) ? Math.round(rawQuantity) : 1))
    const duration = Math.min(24, Math.max(0, Number(hours[appliance.id] ?? 0)))
    return total + (appliance.watts * quantity * duration) / 1000
  }, 0)
  const templateProjectedCost = templateProjectedUnits * Number(meter?.tariff_per_kwh ?? 8)

  useEffect(() => {
    if (account.role === 'RESIDENT' && meter && selectedMeter?.id !== meter.id) onSelectMeter(meter.id)
  }, [account?.role, account.room_id, meter?.id, selectedMeter?.id, onSelectMeter])

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
        setBoardQuantities(Object.fromEntries(catalogue.map((item) => [item.id, active.find((load) => load.appliance_id === item.id)?.quantity ?? 1])))
        setTemplateQuantities((current) => Object.fromEntries(catalogue.map((item) => [item.id, current[item.id] ?? 1])))
        setSelectedScenario((old) => templates.some((item) => String(item.id) === old) ? old : String(templates[0]?.id ?? ''))
      } catch (error) { if (alive) onNotice({ type: 'error', text: (error as Error).message }) }
      finally { if (alive) setLoading(false) }
    }
    void load()
    return () => { alive = false }
  }, [meter?.id, audience, account.id, hasSession, onNotice])

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
    const active = activeById.get(appliance.id)
    const quantity = validQuantity(boardQuantities[appliance.id] ?? active?.quantity ?? 1)
    try {
      const next = await request<ActiveAppliance[]>(`/meters/${meter.id}/simulation/appliances/${appliance.id}`, {
        method: 'PUT', body: JSON.stringify({ enabled: !active, quantity }),
      })
      setActiveLoads(next)
      if (!active) setBoardQuantities((current) => ({ ...current, [appliance.id]: quantity }))
      onNotice({ type: 'success', text: active
        ? `${appliance.name} switched off.`
        : `${quantity} × ${appliance.name} switched on · ${(appliance.watts * quantity).toLocaleString('en-IN')} W total.` })
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
  }

  async function updateApplianceQuantity(appliance: Appliance) {
    if (!meter) return
    const quantity = validQuantity(boardQuantities[appliance.id] ?? 1)
    try {
      const next = await request<ActiveAppliance[]>(`/meters/${meter.id}/simulation/appliances/${appliance.id}`, {
        method: 'PUT', body: JSON.stringify({ enabled: true, quantity }),
      })
      setActiveLoads(next)
      setBoardQuantities((current) => ({ ...current, [appliance.id]: quantity }))
      onNotice({ type: 'success', text: `Updated ${appliance.name} to ${quantity} unit(s), ${(appliance.watts * quantity).toLocaleString('en-IN')} W total.` })
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
        method: 'POST', body: JSON.stringify({ meter_id: meter.id, apply_all: applyAllRooms && account.role === 'ADMIN', simulation_date: simulationDate }),
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

  async function saveTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!account || !sessionStorage.getItem(TOKEN_KEY)) { onNotice({ type: 'error', text: 'Sign in first to save a personal template.' }); return }
    const blocks: Block[] = appliances.flatMap((appliance) => {
      const duration = Math.min(24, Math.max(0, Number(hours[appliance.id] ?? 0)))
      const quantity = Number(templateQuantities[appliance.id] ?? 1)
      if (!duration || quantity === 0) return []
      const [hourText, minuteText] = (startTimes[appliance.id] ?? '00:00').split(':')
      const start = Math.min(1439, Math.max(0, Number(hourText || 0) * 60 + Number(minuteText || 0)))
      const end = start + Math.round(duration * 60)
      const quantities = { [appliance.id]: validQuantity(quantity) }
      if (end <= 1440) return end > start ? [{ label: appliance.name, start_min: start, end_min: end, appliance_ids: [appliance.id], appliance_quantities: quantities }] : []
      // A daily routine may cross midnight; split it at 24:00 and retain the unit count.
      return [
        { label: `${appliance.name} (before midnight)`, start_min: start, end_min: 1440, appliance_ids: [appliance.id], appliance_quantities: quantities },
        { label: `${appliance.name} (after midnight)`, start_min: 0, end_min: end - 1440, appliance_ids: [appliance.id], appliance_quantities: quantities },
      ].filter((block) => block.end_min > block.start_min)
    })
    if (!blocks.length) { onNotice({ type: 'error', text: 'Choose at least one appliance with a quantity greater than zero and a daily runtime above zero.' }); return }
    if (blocks.length > 48) { onNotice({ type: 'error', text: 'This template creates too many schedule blocks. Reduce the number of appliances or midnight-crossing schedules.' }); return }
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
        {account.role === 'ADMIN' && <label className="feature-checkbox"><input type="checkbox" checked={applyAllRooms} onChange={(event) => setApplyAllRooms(event.target.checked)}/> Apply to every room (admin)</label>}
        <label className="feature-label">Template<select className="field-input" value={selected?.id ?? ''} onChange={(event) => setSelectedScenario(event.target.value)} disabled={loading || scenarios.length === 0}>{scenarios.map((item) => <option value={item.id} key={item.id}>{item.name}{item.is_builtin ? ' · built-in' : ' · custom'}</option>)}</select></label>
        {selected && <><p className="scenario-description">{selected.description}</p><div className="scenario-estimate"><div><span>Estimated daily use</span><strong>{projectedUnits.toFixed(2)} kWh</strong></div><div><span>Estimated cost</span><strong>{money(projectedCost)}</strong></div></div><div className="scenario-schedule">{selected.blocks.slice(0, 5).map((block) => <div key={`${block.label}-${block.start_min}-${block.end_min}`}><span><strong>{block.label}</strong><small>{block.appliance_ids.map((id) => `${Math.max(1, block.appliance_quantities?.[id] ?? 1)} × ${appliances.find((appliance) => appliance.id === id)?.name ?? id}`).join(' · ')}</small></span><small>{formatMinute(block.start_min)}–{formatMinute(block.end_min)}</small></div>)}{selected.blocks.length > 5 && <small className="feature-footnote">+ {selected.blocks.length - 5} more schedule blocks</small>}</div></>}
        <label className="feature-label">Simulation date<input className="field-input" type="date" value={simulationDate} max={localISODate()} onChange={(event) => setSimulationDate(event.target.value)}/></label>
        {simulationDate < localISODate() && <p className="feature-inline-info">Historical mode: readings are backfilled on this date and the current wallet is not charged again.</p>}
        <button className="button primary full-width" onClick={() => void applyScenario()} disabled={!hasSession || !meter || !selected || loading}><Zap size={15}/> Apply daily scenario</button>
      </article>
    </section>
    <section className="panel surface-card feature-panel">
      <div className="feature-section-heading"><div><h2>Appliance board</h2><p>Choose the number of units for each device, then switch it on. The total live load uses unit watts × quantity.</p></div><span className={`load-status-pill ${currentWatts > 0 ? 'active' : ''}`}><i/>{activeUnitCount} unit{activeUnitCount === 1 ? '' : 's'} active</span></div>
      {loading ? <div className="feature-empty"><LoaderCircle className="spin" size={20}/> Loading appliance catalogue…</div> : <div className="appliance-grid">{appliances.map((item) => {
        const active = activeById.get(item.id)
        const draftQuantity = validQuantity(boardQuantities[item.id] ?? active?.quantity ?? 1)
        const changedQuantity = Boolean(active && active.quantity !== draftQuantity)
        return <article className={`appliance-card ${active ? 'active' : ''}`} key={item.id}>
          <span className="appliance-card-icon">{iconFor(item.id)}</span>
          <div className="appliance-card-copy"><strong>{item.name}</strong><span>{item.category}</span><small>{item.hint}</small></div>
          <div className="appliance-quantity-row"><label htmlFor={`board-qty-${item.id}`}>Units running</label><input id={`board-qty-${item.id}`} aria-label={`${item.name} quantity`} type="number" min="1" max="100" step="1" value={boardQuantities[item.id] ?? active?.quantity ?? 1} onChange={(event) => setBoardQuantities((current) => ({ ...current, [item.id]: Number(event.target.value || 1) }))} disabled={!hasSession}/></div>
          <p className="appliance-load-summary">{active ? `${active.quantity} × ${item.watts.toLocaleString('en-IN')} W = ${(active.quantity * item.watts).toLocaleString('en-IN')} W live` : `${item.watts.toLocaleString('en-IN')} W per unit · max 100 units`}</p>
          {changedQuantity && <button type="button" className="button secondary appliance-update-count" onClick={() => void updateApplianceQuantity(item)} disabled={!hasSession || !meter || !meter.power_status || Number(meter.current_balance) <= 0}>Apply {draftQuantity} units</button>}
          <div className="appliance-card-bottom"><strong>{active ? `${(active.quantity * item.watts).toLocaleString('en-IN')} W total` : `${item.watts.toLocaleString('en-IN')} W each`}</strong><button type="button" className={`switch-control ${active ? 'on' : ''}`} role="switch" aria-checked={Boolean(active)} aria-label={`${active ? 'Turn off' : 'Turn on'} ${item.name}`} onClick={() => void toggleAppliance(item)} disabled={!hasSession || !meter || !meter.power_status || Number(meter.current_balance) <= 0}><i/></button></div>
        </article>
      })}</div>}
      <p className="feature-footnote"><Activity size={14}/> Low-watt loads are accumulated between meter readings so rounding doesn’t erase real-time simulation use.</p>
    </section>
    <section className="feature-columns">
      <article className="panel surface-card feature-panel">
        <div className="feature-section-heading"><div><h2>Build a daily load template</h2><p>Define how many units run, their start times, and daily runtime. Preview the energy and cost before saving.</p></div><Sparkles size={19}/></div>
        {!hasSession ? <div className="feature-notice"><ShieldCheck size={16}/><span>Your session is no longer active. Return to the sign-in page to continue.</span></div> : <div className="feature-account-row"><span className="feature-tenant-avatar">{account.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</span><span><strong>{account.name}</strong><small>{account.username} · {account.role.toLowerCase()} templates</small></span></div>}
        <form className="feature-form" onSubmit={saveTemplate}>
          <label>Template name<input className="field-input" value={templateName} onChange={(event) => setTemplateName(event.target.value)} required minLength={3} maxLength={100}/></label>
          <p className="template-help">Set the quantity, start time, and runtime for each appliance. Quantity 0 or runtime 0 means that appliance is not included. Start time is set to the minute; runtime supports 15-minute increments. Overnight schedules are split at midnight automatically.</p>
          <div className="template-estimate"><div><span>Estimated daily energy</span><strong>{templateProjectedUnits.toFixed(3)} kWh</strong></div><div><span>Estimated daily cost</span><strong>{money(templateProjectedCost)}</strong></div></div>
          <div className="custom-load-header" aria-hidden="true"><span>Appliance / unit watts</span><span>Quantity</span><span>Start time</span><span>Runtime</span></div>
          <div className="custom-load-list">{appliances.map((appliance) => <div className="template-load-row" key={appliance.id}><span className="template-appliance-name">{appliance.name}<small>{appliance.watts.toLocaleString('en-IN')} W each</small></span><label className="template-control"><span>Units</span><input aria-label={`${appliance.name} quantity in template`} type="number" min="0" max="100" step="1" value={templateQuantities[appliance.id] ?? 1} onChange={(event) => setTemplateQuantities((current) => ({ ...current, [appliance.id]: Number(event.target.value) }))}/></label><label className="template-control"><span>Starts at</span><input aria-label={`${appliance.name} start time`} type="time" step="60" value={startTimes[appliance.id] ?? '00:00'} onChange={(event) => setStartTimes((current) => ({ ...current, [appliance.id]: event.target.value }))}/></label><label className="template-control"><span>Hours/day</span><input aria-label={`${appliance.name} runtime hours per day`} type="number" min="0" max="24" step="0.25" value={hours[appliance.id] ?? 0} onChange={(event) => setHours((current) => ({ ...current, [appliance.id]: Number(event.target.value) }))}/></label></div>)}</div>
          <button className="button primary" type="submit" disabled={savingTemplate || !hasSession}>{savingTemplate ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} Save template to database</button>
        </form>
      </article>
      <aside className="panel surface-card feature-panel scenario-notes-panel"><div className="feature-section-heading"><div><h2>How billing works</h2><p>Simulation rules at a glance.</p></div><ShieldCheck size={18}/></div><div className="feature-rule"><span className="rule-number">01</span><div><strong>Watts become kWh</strong><p>Consumption equals total active watts × simulated seconds ÷ 3,600,000.</p></div></div><div className="feature-rule"><span className="rule-number">02</span><div><strong>Wallet uses the room tariff</strong><p>The server records meter readings and debits the same prepaid wallet already used by SmartVolt.</p></div></div><div className="feature-rule"><span className="rule-number">03</span><div><strong>Empty wallet means power off</strong><p>When the balance reaches zero, the simulated relay turns off and active appliances are cleared.</p></div></div><div className="feature-rule"><span className="rule-number">04</span><div><strong>Past dates are historical only</strong><p>Replaying a prior day fills analytics without charging the current wallet a second time.</p></div></div></aside>
    </section>
  </div>
}

function validQuantity(value: number): number {
  return Math.min(100, Math.max(1, Number.isFinite(value) ? Math.round(value) : 1))
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
