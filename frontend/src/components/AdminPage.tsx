import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Archive, ArrowDownLeft, Home, LoaderCircle, Pencil, Plus, RefreshCw, RotateCcw, Save, Search, ShieldCheck, Trash2, UserPlus, Users, Wallet, X, Zap } from 'lucide-react'

type Notice = { type: 'success' | 'error' | 'info'; text: string }
type Account = { id: number; name: string; username: string; role: 'ADMIN' | 'RESIDENT'; room_id: number | null }
type Meter = { id: number; meter_code: string; is_active: boolean; room_id: number; current_balance: string; power_status: boolean; tariff_per_kwh: string; created_at: string }
type Tenant = { id: number; tenant_code: string | null; is_active: boolean; name: string; username: string | null; phone: string | null; room_id: number | null; role: string }
type Room = { id: number; room_code: string; is_active: boolean; room_no: string; created_at: string; meter: Meter | null; tenants: Tenant[] }
type RechargeTarget = { meter_id: number; meter_code: string; room_id: number; room_code: string; room_no: string; current_balance: string; tariff_per_kwh: string; tenants: { id: number; tenant_code: string; name: string; username: string | null }[] }
type AdminRecharge = { id: number; recharge_code: string; meter_id: number; meter_code: string; room_id: number; room_code: string; room_no: string; user_id: number | null; tenant_code: string | null; tenant_name: string | null; actor_user_id: number | null; actor_name: string | null; amount: string; status: string; created_at: string }
type Props = { account: Account; onNotice: (notice: Notice) => void; onRefresh: () => Promise<void> }

const TOKEN_KEY = 'smartvolt:accessToken'
const ACCOUNT_KEY = 'smartvolt:account'

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

export default function AdminPage({ account, onNotice, onRefresh }: Props) {
  const [rooms, setRooms] = useState<Room[]>([])
  const [loading, setLoading] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null)
  const [roomNo, setRoomNo] = useState('102')
  const [tariff, setTariff] = useState('8')
  const [openingBalance, setOpeningBalance] = useState('250')
  const [firstName, setFirstName] = useState('')
  const [firstPhone, setFirstPhone] = useState('')
  const [firstUsername, setFirstUsername] = useState('')
  const [firstPassword, setFirstPassword] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [tenantPhone, setTenantPhone] = useState('')
  const [tenantUsername, setTenantUsername] = useState('')
  const [tenantPassword, setTenantPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [editingRoomId, setEditingRoomId] = useState<number | null>(null)
  const [editingRoomNo, setEditingRoomNo] = useState('')
  const [editingTariff, setEditingTariff] = useState('')
  const [editingTenantId, setEditingTenantId] = useState<number | null>(null)
  const [editingTenantName, setEditingTenantName] = useState('')
  const [editingTenantUsername, setEditingTenantUsername] = useState('')
  const [editingTenantPhone, setEditingTenantPhone] = useState('')
  const [editingTenantPassword, setEditingTenantPassword] = useState('')
  const [rechargeTargets, setRechargeTargets] = useState<RechargeTarget[]>([])
  const [targetSearch, setTargetSearch] = useState('')
  const [selectedRechargeMeterId, setSelectedRechargeMeterId] = useState('')
  const [rechargeTenantContextId, setRechargeTenantContextId] = useState('')
  const [adminRechargeAmount, setAdminRechargeAmount] = useState('200.00')
  const [rechargeSaving, setRechargeSaving] = useState(false)
  const [rechargeHistory, setRechargeHistory] = useState<AdminRecharge[]>([])
  const [historySearch, setHistorySearch] = useState('')
  const [loadingRechargeHistory, setLoadingRechargeHistory] = useState(false)

  const loadRechargeTargets = useCallback(async (query = '') => {
    if (account?.role !== 'ADMIN') return
    const term = query.trim()
    const path = `/admin/recharge-targets${term ? `?query=${encodeURIComponent(term)}&limit=100` : '?limit=100'}`
    try {
      const items = await request<RechargeTarget[]>(path)
      setRechargeTargets(items)
      setSelectedRechargeMeterId((current) => items.some((target) => String(target.meter_id) === current) ? current : String(items[0]?.meter_id ?? ''))
      setRechargeTenantContextId('')
    } catch (error) {
      onNotice({ type: 'error', text: (error as Error).message })
    }
  }, [account?.role, onNotice])

  const loadRechargeHistory = useCallback(async (query = '') => {
    if (account?.role !== 'ADMIN') return
    setLoadingRechargeHistory(true)
    try {
      const term = query.trim()
      const path = `/admin/recharges?limit=20${term ? `&query=${encodeURIComponent(term)}` : ''}`
      setRechargeHistory(await request<AdminRecharge[]>(path))
    } catch (error) {
      onNotice({ type: 'error', text: (error as Error).message })
    } finally { setLoadingRechargeHistory(false) }
  }, [account?.role, onNotice])

  useEffect(() => {
    if (account?.role === 'ADMIN' && sessionStorage.getItem(TOKEN_KEY)) {
      void loadRechargeTargets()
      void loadRechargeHistory()
    }
  }, [account?.role, loadRechargeTargets, loadRechargeHistory])

  async function submitAdminRecharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedRechargeMeterId) { onNotice({ type: 'error', text: 'Select an active meter first.' }); return }
    setRechargeSaving(true)
    try {
      const target = rechargeTargets.find((item) => String(item.meter_id) === selectedRechargeMeterId)
      if (!target) throw new Error('The selected meter is no longer in the active target list. Refresh and choose again.')
      const result = await request<AdminRecharge>('/admin/recharges', {
        method: 'POST', body: JSON.stringify({
          target_type: 'meter_id', target_value: selectedRechargeMeterId,
          tenant_context_id: rechargeTenantContextId ? Number(rechargeTenantContextId) : null,
          amount: adminRechargeAmount, idempotency_key: crypto.randomUUID(),
        }),
      })
      onNotice({ type: 'success', text: `${result.recharge_code}: added ₹${Number(result.amount).toFixed(2)} to Meter ${result.meter_code} (Room ${result.room_no}).` })
      setRechargeTenantContextId('')
      await Promise.all([loadRechargeTargets(targetSearch), loadRechargeHistory(historySearch), onRefresh()])
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setRechargeSaving(false) }
  }

  const loadRooms = useCallback(async () => {
    if (account?.role !== 'ADMIN') return
    setLoading(true)
    try {
      const items = await request<Room[]>(`/admin/rooms${showArchived ? '?include_archived=true' : ''}`)
      setRooms(items)
      const activeItems = items.filter((room) => room.is_active)
      setSelectedRoomId((current) => activeItems.some((room) => room.id === current) ? current : activeItems[0]?.id ?? null)
    } catch (error) {
      onNotice({ type: 'error', text: (error as Error).message })
    } finally { setLoading(false) }
  }, [account?.role, onNotice, showArchived])

  useEffect(() => { void loadRooms() }, [loadRooms])

  async function createRoom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true)
    try {
      const created = await request<Room>('/admin/rooms', {
        method: 'POST', body: JSON.stringify({
          room_no: roomNo, tariff_per_kwh: tariff, opening_balance: openingBalance,
          first_tenant_name: firstName || null, first_tenant_phone: firstPhone || null,
          first_tenant_username: firstUsername || null, first_tenant_password: firstPassword || null,
        }),
      })
      setRooms((current) => [...current.filter((room) => room.id !== created.id), created].sort((a, b) => a.room_no.localeCompare(b.room_no, undefined, { numeric: true })))
      setSelectedRoomId(created.id); setRoomNo(''); setFirstName(''); setFirstPhone(''); setFirstUsername(''); setFirstPassword('')
      onNotice({ type: 'success', text: `Room ${created.room_code}, Meter ${created.meter?.meter_code ?? 'created'}${created.tenants[0]?.tenant_code ? `, Tenant ${created.tenants[0].tenant_code}` : ''} created successfully.` })
      await loadRooms()
      await onRefresh()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  async function addTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedRoomId) { onNotice({ type: 'error', text: 'Create or select a room first.' }); return }
    setSaving(true)
    try {
      const tenant = await request<Tenant>(`/admin/rooms/${selectedRoomId}/tenants`, {
        method: 'POST', body: JSON.stringify({ name: tenantName, phone: tenantPhone || null, username: tenantUsername, password: tenantPassword }),
      })
      setTenantName(''); setTenantPhone(''); setTenantUsername(''); setTenantPassword('')
      onNotice({ type: 'success', text: `${tenant.tenant_code ?? 'Tenant'} created. ${tenant.name} can sign in as ${tenant.username}.` })
      await loadRooms()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  function beginEditRoom(room: Room) {
    setSelectedRoomId(room.id)
    setEditingRoomId(room.id)
    setEditingRoomNo(room.room_no)
    setEditingTariff(room.meter?.tariff_per_kwh ?? '8')
  }

  async function updateRoom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingRoomId) return
    setSaving(true)
    try {
      const updated = await request<Room>(`/admin/rooms/${editingRoomId}`, {
        method: 'PATCH', body: JSON.stringify({ room_no: editingRoomNo, tariff_per_kwh: editingTariff }),
      })
      setEditingRoomId(null)
      onNotice({ type: 'success', text: `Room ${updated.room_no} was updated.` })
      await loadRooms()
      await onRefresh()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  async function deleteRoom(room: Room) {
    const confirmed = window.confirm(`Archive Room ${room.room_no} (${room.room_code})? Its meter, balance, usage readings, recharge records and ledger history will be preserved. Active tenants must be removed or reassigned first.`)
    if (!confirmed) return
    setSaving(true)
    try {
      await request<{ message: string }>(`/admin/rooms/${room.id}`, { method: 'DELETE' })
      if (editingRoomId === room.id) setEditingRoomId(null)
      setEditingTenantId(null)
      onNotice({ type: 'success', text: `Room ${room.room_code} was archived. Its financial and usage history was preserved.` })
      await loadRooms()
      await onRefresh()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  async function restoreRoom(room: Room) {
    setSaving(true)
    try {
      await request<Room>(`/admin/rooms/${room.id}/restore`, { method: 'POST' })
      onNotice({ type: 'success', text: `Room ${room.room_code} was restored.` })
      await loadRooms()
      await onRefresh()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  function beginEditTenant(tenant: Tenant) {
    setEditingTenantId(tenant.id)
    setEditingTenantName(tenant.name)
    setEditingTenantUsername(tenant.username ?? '')
    setEditingTenantPhone(tenant.phone ?? '')
    setEditingTenantPassword('')
  }

  async function updateTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingTenantId) return
    setSaving(true)
    const payload: { name: string; username: string; phone: string | null; password?: string } = {
      name: editingTenantName, username: editingTenantUsername, phone: editingTenantPhone || null,
    }
    if (editingTenantPassword) payload.password = editingTenantPassword
    try {
      const updated = await request<Tenant>(`/admin/tenants/${editingTenantId}`, {
        method: 'PATCH', body: JSON.stringify(payload),
      })
      setEditingTenantId(null)
      setEditingTenantPassword('')
      onNotice({ type: 'success', text: `Tenant ${updated.name} was updated.` })
      await loadRooms()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  async function deleteTenant(tenant: Tenant) {
    const confirmed = window.confirm(`Remove ${tenant.name} from Room ${tenant.room_id}? Their sign-in will be disabled. Historical billing records and support history will be retained.`)
    if (!confirmed) return
    setSaving(true)
    try {
      await request<{ message: string }>(`/admin/tenants/${tenant.id}`, { method: 'DELETE' })
      if (editingTenantId === tenant.id) setEditingTenantId(null)
      onNotice({ type: 'success', text: `${tenant.tenant_code ?? tenant.name} was deactivated and their sign-in was disabled.` })
      await loadRooms()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  if (!sessionStorage.getItem(TOKEN_KEY) || account.role !== 'ADMIN') {
    return <div className="feature-stack"><section className="feature-hero surface-card"><span className="feature-icon"><ShieldCheck size={22}/></span><div><span className="eyebrow">RESTRICTED WORKSPACE</span><h2>Administrator access required</h2><p>Sign in with an administrator account from the SmartVolt login page to manage rooms and resident accounts.</p></div></section></div>
  }

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId && room.is_active) ?? null
  return <div className="feature-stack">
    <section className="feature-hero surface-card">
      <span className="feature-icon"><ShieldCheck size={22}/></span><div><span className="eyebrow">ADMIN CONTROL PLANE</span><h2>Rooms & residents</h2><p>Create a room with a prepaid meter, set its tariff and opening credit, then issue tenant credentials.</p></div>
    </section>
    <div className="feature-stats">
      <article className="panel surface-card"><span>ROOMS</span><strong>{rooms.length}</strong><small>Metered spaces</small></article>
      <article className="panel surface-card"><span>RESIDENTS</span><strong>{rooms.reduce((total, room) => total + room.tenants.length, 0)}</strong><small>Tenant accounts</small></article>
      <article className="panel surface-card"><span>ADMIN SESSION</span><strong className="feature-stat-live">Verified</strong><small>{account.username} · role checked by API</small></article>
    </div>
    <section className="panel surface-card feature-panel">
      <div className="feature-section-heading"><div><h2>Recharge any meter</h2><p>Search by meter ID/code, room number/code, or a resident’s tenant ID, name, or username. The meter is always the wallet target.</p></div><Wallet size={20}/></div>
      <form className="feature-form feature-form-grid" onSubmit={(event) => { event.preventDefault(); void loadRechargeTargets(targetSearch) }}>
        <label>Search recharge target<input className="field-input" value={targetSearch} onChange={(event) => setTargetSearch(event.target.value)} maxLength={100} placeholder="MTR-000045, Room 204, TEN-000123, name…" /></label>
        <div className="feature-edit-actions"><button className="button secondary" type="submit"><Search size={15}/> Search</button><button className="icon-button" type="button" aria-label="Refresh recharge targets" onClick={() => void loadRechargeTargets(targetSearch)}><RefreshCw size={15}/></button></div>
      </form>
      <form className="feature-form feature-form-grid" onSubmit={submitAdminRecharge}>
        <label>Meter / room target<select className="field-input" value={selectedRechargeMeterId} onChange={(event) => { setSelectedRechargeMeterId(event.target.value); setRechargeTenantContextId('') }} required>
          <option value="">Select an active meter</option>
          {rechargeTargets.map((target) => <option key={target.meter_id} value={target.meter_id}>Room {target.room_no} · {target.room_code} · {target.meter_code} · ₹{Number(target.current_balance).toFixed(2)} · {target.tenants.length} tenant(s)</option>)}
        </select></label>
        <label>Tenant context (optional)<select className="field-input" value={rechargeTenantContextId} onChange={(event) => setRechargeTenantContextId(event.target.value)}>
          <option value="">Room/meter recharge without tenant attribution</option>
          {(rechargeTargets.find((target) => String(target.meter_id) === selectedRechargeMeterId)?.tenants ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.tenant_code} · {tenant.name}{tenant.username ? ` (@${tenant.username})` : ''}</option>)}
        </select></label>
        <label>Recharge amount (₹)<input className="field-input" type="number" min="0.01" step="0.01" value={adminRechargeAmount} onChange={(event) => setAdminRechargeAmount(event.target.value)} required /></label>
        <button className="button primary feature-form-submit" type="submit" disabled={rechargeSaving || !selectedRechargeMeterId}>{rechargeSaving ? <LoaderCircle size={15} className="spin"/> : <ArrowDownLeft size={15}/>} Credit selected meter</button>
      </form>
      {selectedRechargeMeterId && rechargeTargets.find((target) => String(target.meter_id) === selectedRechargeMeterId) && <p className="feature-footnote"><ShieldCheck size={13}/> Selected meter belongs to Room {rechargeTargets.find((target) => String(target.meter_id) === selectedRechargeMeterId)?.room_no}. Current balance: ₹{Number(rechargeTargets.find((target) => String(target.meter_id) === selectedRechargeMeterId)?.current_balance ?? 0).toFixed(2)}.</p>}
      <div className="feature-section-heading feature-subheading"><div><h2>Recharge history</h2><p>Search cross-room transactions by recharge code, room, meter, tenant, or administrator.</p></div><button type="button" className="icon-button" aria-label="Refresh recharge history" onClick={() => void loadRechargeHistory(historySearch)} disabled={loadingRechargeHistory}><RefreshCw size={15} className={loadingRechargeHistory ? 'spin' : ''}/></button></div>
      <form className="feature-form feature-form-grid" onSubmit={(event) => { event.preventDefault(); void loadRechargeHistory(historySearch) }}><label>Search transactions<input className="field-input" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} maxLength={100} placeholder="RCH-000256, Room 204, tenant, admin…" /></label><div className="feature-edit-actions"><button className="button secondary" type="submit"><Search size={15}/> Search history</button><button className="button secondary" type="button" onClick={() => { setHistorySearch(''); void loadRechargeHistory('') }}>Clear</button></div></form>
      {rechargeHistory.length ? <div className="table-scroll"><table><thead><tr><th>Transaction</th><th>Room / meter</th><th>Tenant context</th><th>Performed by</th><th>Amount</th><th>Date</th></tr></thead><tbody>{rechargeHistory.map((item) => <tr key={item.id}><td><strong>{item.recharge_code}</strong><small className="table-muted">{item.status.toLowerCase()}</small></td><td>Room {item.room_no}<small className="table-muted">{item.room_code} · {item.meter_code}</small></td><td>{item.tenant_name ?? 'Room-level'}<small className="table-muted">{item.tenant_code ?? 'No tenant context'}</small></td><td>{item.actor_name ?? 'Historical actor unknown'}</td><td className="amount-positive">+₹{Number(item.amount).toFixed(2)}</td><td>{new Date(item.created_at).toLocaleString('en-IN')}</td></tr>)}</tbody></table></div> : <p className="feature-empty">{loadingRechargeHistory ? 'Loading recharge history…' : historySearch ? 'No recharge transactions matched that search.' : 'No recharge transactions found yet.'}</p>}
    </section>
    <div className="feature-columns">
      <section className="panel surface-card feature-panel">
        <div className="feature-section-heading"><div><h2>Room directory</h2><p>Select a room to add residents. Room and meter IDs remain stable.</p></div><div className="feature-item-actions"><button className="button secondary" type="button" onClick={() => setShowArchived((value) => !value)}>{showArchived ? 'Hide archived' : 'Show archived'}</button><button className="icon-button" onClick={() => void loadRooms()} aria-label="Refresh rooms"><LoaderCircle className={loading ? 'spin' : ''} size={17}/></button></div></div>
        {loading ? <p className="feature-empty">Loading room directory…</p> : rooms.length === 0 ? <p className="feature-empty">No rooms yet. Create the first one below.</p> : <div className="feature-room-list">{rooms.map((room) => <div className="feature-room-item" key={room.id}><button type="button" className={`feature-room-row ${selectedRoomId === room.id ? 'selected' : ''}`} onClick={() => room.is_active && setSelectedRoomId(room.id)} disabled={!room.is_active}><span className="feature-room-icon"><Home size={16}/></span><span className="feature-room-main"><strong>Room {room.room_no} {!room.is_active && '· Archived'}</strong><small>{room.room_code} · {room.tenants.length} resident{room.tenants.length === 1 ? '' : 's'} · {room.meter?.meter_code ?? 'No meter'}</small></span><span className="feature-room-balance">₹{Number(room.meter?.current_balance ?? 0).toFixed(2)}<small>{room.is_active && room.meter?.power_status ? 'Power on' : 'Inactive'}</small></span></button><div className="feature-item-actions">{room.is_active ? <><button type="button" className="icon-button" title={`Edit Room ${room.room_no}`} aria-label={`Edit Room ${room.room_no}`} onClick={() => beginEditRoom(room)} disabled={saving}><Pencil size={15}/></button><button type="button" className="icon-button danger-action" title={`Archive Room ${room.room_no}`} aria-label={`Archive Room ${room.room_no}`} onClick={() => void deleteRoom(room)} disabled={saving}><Archive size={15}/></button></> : <button type="button" className="icon-button" title={`Restore Room ${room.room_no}`} aria-label={`Restore Room ${room.room_no}`} onClick={() => void restoreRoom(room)} disabled={saving}><RotateCcw size={15}/></button>}</div></div>)}</div>}
        {editingRoomId !== null && <form className="feature-form feature-form-grid feature-edit-card" onSubmit={updateRoom}><div className="feature-form-divider">Edit room details</div><label>Room number<input className="field-input" value={editingRoomNo} onChange={(event) => setEditingRoomNo(event.target.value)} required maxLength={20}/></label><label>Tariff (₹/kWh)<input className="field-input" type="number" min="0.01" step="0.0001" value={editingTariff} onChange={(event) => setEditingTariff(event.target.value)} required/></label><div className="feature-edit-actions"><button className="button primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin"/> : <Save size={15}/>} Save changes</button><button className="button secondary" type="button" onClick={() => setEditingRoomId(null)} disabled={saving}><X size={15}/> Cancel</button></div></form>}
        <div className="feature-section-heading feature-subheading"><div><h2>Create a room</h2><p>Room, tariff, opening credit, and optional first tenant.</p></div></div>
        <form className="feature-form feature-form-grid" onSubmit={createRoom}>
          <label>Room number<input className="field-input" value={roomNo} onChange={(event) => setRoomNo(event.target.value)} required maxLength={20} placeholder="102"/></label>
          <label>Tariff (₹/kWh)<input className="field-input" type="number" min="0.01" step="0.01" value={tariff} onChange={(event) => setTariff(event.target.value)} required/></label>
          <label>Opening balance (₹)<input className="field-input" type="number" min="0" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} required/></label>
          <div className="feature-form-divider">Optional first tenant</div>
          <label>Full name<input className="field-input" value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="Resident name"/></label>
          <label>Phone<input className="field-input" value={firstPhone} onChange={(event) => setFirstPhone(event.target.value)} maxLength={15} placeholder="Optional"/></label>
          <label>Username<input className="field-input" value={firstUsername} onChange={(event) => setFirstUsername(event.target.value)} minLength={3} placeholder="3+ characters"/></label>
          <label>Password<input className="field-input" type="password" value={firstPassword} onChange={(event) => setFirstPassword(event.target.value)} minLength={8} placeholder="8+ characters"/></label>
          <button className="button primary feature-form-submit" type="submit" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} Create room</button>
        </form>
      </section>
      <section className="panel surface-card feature-panel">
        <div className="feature-section-heading"><div><h2>Add tenant</h2><p>Tenant credentials are stored as a salted password hash.</p></div><UserPlusIcon/></div>
        <form className="feature-form" onSubmit={addTenant}>
          <label>Room<select className="field-input" value={selectedRoomId ?? ''} onChange={(event) => setSelectedRoomId(Number(event.target.value) || null)} required><option value="">Select room</option>{rooms.filter((room) => room.is_active).map((room) => <option value={room.id} key={room.id}>Room {room.room_no} · {room.room_code}</option>)}</select></label>
          <label>Full name<input className="field-input" value={tenantName} onChange={(event) => setTenantName(event.target.value)} required maxLength={100}/></label>
          <label>Username<input className="field-input" value={tenantUsername} onChange={(event) => setTenantUsername(event.target.value)} required minLength={3} maxLength={60}/></label>
          <label>Password<input className="field-input" type="password" value={tenantPassword} onChange={(event) => setTenantPassword(event.target.value)} required minLength={8} maxLength={200}/></label>
          <label>Phone<input className="field-input" value={tenantPhone} onChange={(event) => setTenantPhone(event.target.value)} maxLength={15} placeholder="Optional"/></label>
          <button className="button primary" type="submit" disabled={saving || !rooms.some((room) => room.is_active)}><UserPlus size={15}/> Add tenant</button>
        </form>
        <div className="feature-form-divider">{selectedRoom ? `Room ${selectedRoom.room_no} directory` : 'Tenant directory'}</div>
        {selectedRoom?.tenants.length ? <div className="feature-tenant-list">{selectedRoom.tenants.map((tenant) => editingTenantId === tenant.id ? <form className="feature-tenant-edit feature-form" key={tenant.id} onSubmit={updateTenant}><div className="feature-form-divider">Edit {tenant.name}</div><label>Full name<input className="field-input" value={editingTenantName} onChange={(event) => setEditingTenantName(event.target.value)} maxLength={100} required/></label><label>Username<input className="field-input" value={editingTenantUsername} onChange={(event) => setEditingTenantUsername(event.target.value)} minLength={3} maxLength={60} required/></label><label>Phone<input className="field-input" value={editingTenantPhone} onChange={(event) => setEditingTenantPhone(event.target.value)} maxLength={15} placeholder="Optional"/></label><label>New password<input className="field-input" type="password" value={editingTenantPassword} onChange={(event) => setEditingTenantPassword(event.target.value)} minLength={8} maxLength={200} placeholder="Leave blank to keep current password"/></label><div className="feature-edit-actions"><button className="button primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin"/> : <Save size={15}/>} Save changes</button><button className="button secondary" type="button" onClick={() => setEditingTenantId(null)} disabled={saving}><X size={15}/> Cancel</button></div></form> : <div className="feature-tenant-row" key={tenant.id}><span className="feature-tenant-avatar">{tenant.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</span><span className="feature-tenant-main"><strong>{tenant.name}</strong><small>{tenant.tenant_code ?? 'No tenant ID'} · {tenant.username ?? 'No username'} · {tenant.phone ?? 'Phone not set'}</small></span><span className="status-badge successful">{tenant.role.toLowerCase()}</span><div className="feature-item-actions"><button type="button" className="icon-button" title={`Edit ${tenant.name}`} aria-label={`Edit ${tenant.name}`} onClick={() => beginEditTenant(tenant)} disabled={saving}><Pencil size={15}/></button><button type="button" className="icon-button danger-action" title={`Remove ${tenant.name}`} aria-label={`Remove ${tenant.name}`} onClick={() => void deleteTenant(tenant)} disabled={saving}><Trash2 size={15}/></button></div></div>)}</div> : <p className="feature-empty">No resident accounts in this room yet.</p>}
        <p className="feature-footnote"><Zap size={13}/> Room and meter creation is transactional. Opening credit is recorded in the wallet ledger.</p>
      </section>
    </div>
  </div>
}

function UserPlusIcon() { return <Users size={19}/> }
