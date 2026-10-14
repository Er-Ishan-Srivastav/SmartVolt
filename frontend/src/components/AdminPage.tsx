import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Home, KeyRound, LoaderCircle, LogIn, LogOut, Pencil, Plus, Save, ShieldCheck, Trash2, UserPlus, Users, X, Zap } from 'lucide-react'

type Notice = { type: 'success' | 'error' | 'info'; text: string }
type Account = { id: number; name: string; username: string; role: 'ADMIN' | 'RESIDENT'; room_id: number | null }
type Meter = { id: number; room_id: number; current_balance: string; power_status: boolean; tariff_per_kwh: string; created_at: string }
type Tenant = { id: number; name: string; username: string | null; phone: string | null; room_id: number | null; role: string }
type Room = { id: number; room_no: string; created_at: string; meter: Meter | null; tenants: Tenant[] }
type LoginResponse = { access_token: string; account: Account }
type Props = { onNotice: (notice: Notice) => void; onRefresh: () => Promise<void> }

const TOKEN_KEY = 'smartvolt:accessToken'
const ACCOUNT_KEY = 'smartvolt:account'

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

function storedAccount(): Account | null {
  try { return JSON.parse(localStorage.getItem(ACCOUNT_KEY) ?? 'null') as Account | null }
  catch { return null }
}

export default function AdminPage({ onNotice, onRefresh }: Props) {
  const [account, setAccount] = useState<Account | null>(storedAccount)
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [rooms, setRooms] = useState<Room[]>([])
  const [loading, setLoading] = useState(false)
  const [loginBusy, setLoginBusy] = useState(false)
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

  const loadRooms = useCallback(async () => {
    if (account?.role !== 'ADMIN') return
    setLoading(true)
    try {
      const items = await request<Room[]>('/admin/rooms')
      setRooms(items)
      setSelectedRoomId((current) => items.some((room) => room.id === current) ? current : items[0]?.id ?? null)
    } catch (error) {
      onNotice({ type: 'error', text: (error as Error).message })
    } finally { setLoading(false) }
  }, [account?.role, onNotice])

  useEffect(() => { void loadRooms() }, [loadRooms])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoginBusy(true)
    try {
      const result = await request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      localStorage.setItem(TOKEN_KEY, result.access_token)
      localStorage.setItem(ACCOUNT_KEY, JSON.stringify(result.account))
      setAccount(result.account); setPassword(''); window.dispatchEvent(new Event('smartvolt:auth-changed'))
      if (result.account.role !== 'ADMIN') {
        onNotice({ type: 'error', text: 'This account is a resident. Sign in with the administrator account to manage rooms and tenants.' })
      } else {
        onNotice({ type: 'success', text: `Signed in as ${result.account.username}. Administrator tools are unlocked.` })
      }
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setLoginBusy(false) }
  }

  function signOut() {
    localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ACCOUNT_KEY)
    setAccount(null); setRooms([]); setSelectedRoomId(null); window.dispatchEvent(new Event('smartvolt:auth-changed'))
    onNotice({ type: 'info', text: 'Signed out of the admin workspace.' })
  }

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
      onNotice({ type: 'success', text: `Room ${created.room_no} and its simulated meter were created.` })
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
      onNotice({ type: 'success', text: `${tenant.name} can now sign in as ${tenant.username}.` })
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
    const confirmed = window.confirm(`Permanently delete Room ${room.room_no}? Its meter, balance, usage readings, recharge records and ledger history will be deleted. Residents will be unassigned and their sign-in disabled. This cannot be undone.`)
    if (!confirmed) return
    setSaving(true)
    try {
      await request<{ message: string }>(`/admin/rooms/${room.id}`, { method: 'DELETE' })
      if (editingRoomId === room.id) setEditingRoomId(null)
      setEditingTenantId(null)
      onNotice({ type: 'success', text: `Room ${room.room_no} was deleted. Associated meter history was removed.` })
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
      onNotice({ type: 'success', text: `${tenant.name} was removed and their sign-in was disabled.` })
      await loadRooms()
    } catch (error) { onNotice({ type: 'error', text: (error as Error).message }) }
    finally { setSaving(false) }
  }

  if (!account || !localStorage.getItem(TOKEN_KEY) || account.role !== 'ADMIN') {
    return <div className="feature-stack">
      <section className="feature-hero surface-card">
        <span className="feature-icon"><ShieldCheck size={22}/></span><div><span className="eyebrow">SECURE WORKSPACE</span><h2>Administrator sign in</h2><p>Manage rooms and tenant accounts. Admin APIs verify this role on the server before accepting changes.</p></div>
      </section>
      {account?.role === 'RESIDENT' && <div className="feature-notice"><Users size={17}/><span>Currently signed in as resident <strong>{account.username}</strong>. Sign out before switching to the administrator account.</span><button className="button secondary" onClick={signOut}><LogOut size={15}/> Sign out</button></div>}
      <section className="panel surface-card feature-panel admin-login-panel">
        <div className="feature-section-heading"><div><h2>Admin access</h2><p>Use the administrator credentials configured for this local environment.</p></div><KeyRound size={19}/></div>
        <form className="feature-form" onSubmit={signIn}>
          <label>Username<input className="field-input" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required/></label>
          <label>Password<input className="field-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required/></label>
          <button className="button primary" type="submit" disabled={loginBusy}>{loginBusy ? <LoaderCircle size={16} className="spin"/> : <LogIn size={16}/>} Sign in to Admin</button>
        </form>
        <p className="feature-footnote">Fresh local demo credentials default to <code>admin</code> / <code>Admin123!</code> unless changed in <code>.env</code>. Rotate these before sharing the app.</p>
      </section>
    </div>
  }

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId) ?? null
  return <div className="feature-stack">
    <section className="feature-hero surface-card">
      <span className="feature-icon"><ShieldCheck size={22}/></span><div><span className="eyebrow">ADMIN CONTROL PLANE</span><h2>Rooms & residents</h2><p>Create a room with a prepaid meter, set its tariff and opening credit, then issue tenant credentials.</p></div>
      <button className="button secondary feature-hero-action" onClick={signOut}><LogOut size={15}/> Sign out</button>
    </section>
    <div className="feature-stats">
      <article className="panel surface-card"><span>ROOMS</span><strong>{rooms.length}</strong><small>Metered spaces</small></article>
      <article className="panel surface-card"><span>RESIDENTS</span><strong>{rooms.reduce((total, room) => total + room.tenants.length, 0)}</strong><small>Tenant accounts</small></article>
      <article className="panel surface-card"><span>ADMIN SESSION</span><strong className="feature-stat-live">Verified</strong><small>{account.username} · role checked by API</small></article>
    </div>
    <div className="feature-columns">
      <section className="panel surface-card feature-panel">
        <div className="feature-section-heading"><div><h2>Room directory</h2><p>Select a room to add residents.</p></div><button className="icon-button" onClick={() => void loadRooms()} aria-label="Refresh rooms"><LoaderCircle className={loading ? 'spin' : ''} size={17}/></button></div>
        {loading ? <p className="feature-empty">Loading room directory…</p> : rooms.length === 0 ? <p className="feature-empty">No rooms yet. Create the first one below.</p> : <div className="feature-room-list">{rooms.map((room) => <div className="feature-room-item" key={room.id}><button type="button" className={`feature-room-row ${selectedRoomId === room.id ? 'selected' : ''}`} onClick={() => setSelectedRoomId(room.id)}><span className="feature-room-icon"><Home size={16}/></span><span className="feature-room-main"><strong>Room {room.room_no}</strong><small>{room.tenants.length} resident{room.tenants.length === 1 ? '' : 's'} · Meter #{room.meter?.id ?? '—'}</small></span><span className="feature-room-balance">₹{Number(room.meter?.current_balance ?? 0).toFixed(2)}<small>{room.meter?.power_status ? 'Power on' : 'Power off'}</small></span></button><div className="feature-item-actions"><button type="button" className="icon-button" title={`Edit Room ${room.room_no}`} aria-label={`Edit Room ${room.room_no}`} onClick={() => beginEditRoom(room)} disabled={saving}><Pencil size={15}/></button><button type="button" className="icon-button danger-action" title={`Delete Room ${room.room_no}`} aria-label={`Delete Room ${room.room_no}`} onClick={() => void deleteRoom(room)} disabled={saving}><Trash2 size={15}/></button></div></div>)}</div>}
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
          <label>Room<select className="field-input" value={selectedRoomId ?? ''} onChange={(event) => setSelectedRoomId(Number(event.target.value) || null)} required><option value="">Select room</option>{rooms.map((room) => <option value={room.id} key={room.id}>Room {room.room_no}</option>)}</select></label>
          <label>Full name<input className="field-input" value={tenantName} onChange={(event) => setTenantName(event.target.value)} required maxLength={100}/></label>
          <label>Username<input className="field-input" value={tenantUsername} onChange={(event) => setTenantUsername(event.target.value)} required minLength={3} maxLength={60}/></label>
          <label>Password<input className="field-input" type="password" value={tenantPassword} onChange={(event) => setTenantPassword(event.target.value)} required minLength={8} maxLength={200}/></label>
          <label>Phone<input className="field-input" value={tenantPhone} onChange={(event) => setTenantPhone(event.target.value)} maxLength={15} placeholder="Optional"/></label>
          <button className="button primary" type="submit" disabled={saving || !rooms.length}><UserPlus size={15}/> Add tenant</button>
        </form>
        <div className="feature-form-divider">{selectedRoom ? `Room ${selectedRoom.room_no} directory` : 'Tenant directory'}</div>
        {selectedRoom?.tenants.length ? <div className="feature-tenant-list">{selectedRoom.tenants.map((tenant) => editingTenantId === tenant.id ? <form className="feature-tenant-edit feature-form" key={tenant.id} onSubmit={updateTenant}><div className="feature-form-divider">Edit {tenant.name}</div><label>Full name<input className="field-input" value={editingTenantName} onChange={(event) => setEditingTenantName(event.target.value)} maxLength={100} required/></label><label>Username<input className="field-input" value={editingTenantUsername} onChange={(event) => setEditingTenantUsername(event.target.value)} minLength={3} maxLength={60} required/></label><label>Phone<input className="field-input" value={editingTenantPhone} onChange={(event) => setEditingTenantPhone(event.target.value)} maxLength={15} placeholder="Optional"/></label><label>New password<input className="field-input" type="password" value={editingTenantPassword} onChange={(event) => setEditingTenantPassword(event.target.value)} minLength={8} maxLength={200} placeholder="Leave blank to keep current password"/></label><div className="feature-edit-actions"><button className="button primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={15} className="spin"/> : <Save size={15}/>} Save changes</button><button className="button secondary" type="button" onClick={() => setEditingTenantId(null)} disabled={saving}><X size={15}/> Cancel</button></div></form> : <div className="feature-tenant-row" key={tenant.id}><span className="feature-tenant-avatar">{tenant.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</span><span className="feature-tenant-main"><strong>{tenant.name}</strong><small>{tenant.username ?? 'No username'} · {tenant.phone ?? 'Phone not set'}</small></span><span className="status-badge successful">{tenant.role.toLowerCase()}</span><div className="feature-item-actions"><button type="button" className="icon-button" title={`Edit ${tenant.name}`} aria-label={`Edit ${tenant.name}`} onClick={() => beginEditTenant(tenant)} disabled={saving}><Pencil size={15}/></button><button type="button" className="icon-button danger-action" title={`Remove ${tenant.name}`} aria-label={`Remove ${tenant.name}`} onClick={() => void deleteTenant(tenant)} disabled={saving}><Trash2 size={15}/></button></div></div>)}</div> : <p className="feature-empty">No resident accounts in this room yet.</p>}
        <p className="feature-footnote"><Zap size={13}/> Room and meter creation is transactional. Opening credit is recorded in the wallet ledger.</p>
      </section>
    </div>
  </div>
}

function UserPlusIcon() { return <Users size={19}/> }
