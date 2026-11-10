import { useMemo, useState } from "react";
import {
  Activity, Gauge, Flag, ChartNoAxesCombined, CloudSun, Map, Fuel,
  Thermometer, CircleGauge, Cable, Settings, Radio, ChevronDown,
  Plus, RotateCcw, Save, X, GripVertical, Pin, PinOff, Moon, Sun,
  LayoutDashboard, Waves, TriangleAlert, Clock3, Zap, Droplets,
} from "lucide-react";

type TileId = "speed" | "gear" | "rpm" | "pedals" | "laps" | "lap_history" | "weather" | "map" | "session" | "brakes" | "tyres" | "fuel" | "warnings" | "hardware";
type TileSize = "small" | "medium" | "large";
type Tile = { id: TileId; size: TileSize; pinned: boolean };
const definitions: { id: TileId; title: string; description: string }[] = [
  { id: "speed", title: "Speed", description: "Live vehicle speed" },
  { id: "gear", title: "Gear", description: "Current selected gear" },
  { id: "rpm", title: "Engine RPM", description: "Engine speed and shift-light progress" },
  { id: "pedals", title: "Pedal inputs", description: "Throttle, brake and clutch" },
  { id: "laps", title: "Lap times", description: "Current, last and best lap" },
  { id: "lap_history", title: "Lap time history", description: "Recent completed laps" },
  { id: "weather", title: "Track weather", description: "Ambient and track conditions" },
  { id: "map", title: "Track map", description: "Circuit layout and car position" },
  { id: "session", title: "Session", description: "Current session information" },
  { id: "brakes", title: "Brake temperatures", description: "Temperatures by corner" },
  { id: "tyres", title: "Tyre condition", description: "Pressures and temperatures" },
  { id: "fuel", title: "Fuel", description: "Remaining fuel and estimated range" },
  { id: "warnings", title: "Penalties & warnings", description: "Lap validity and race penalties" },
  { id: "hardware", title: "Hardware connections", description: "Connected sim-racing devices" },
];
const initial: Tile[] = [
  { id: "speed", size: "small", pinned: true },
  { id: "gear", size: "small", pinned: true },
  { id: "rpm", size: "medium", pinned: true },
  { id: "pedals", size: "medium", pinned: false },
  { id: "laps", size: "medium", pinned: false },
  { id: "lap_history", size: "large", pinned: false },
  { id: "weather", size: "medium", pinned: false },
  { id: "map", size: "medium", pinned: false },
  { id: "session", size: "small", pinned: false },
  { id: "brakes", size: "medium", pinned: false },
  { id: "tyres", size: "medium", pinned: false },
  { id: "fuel", size: "medium", pinned: false },
  { id: "warnings", size: "medium", pinned: false },
  { id: "hardware", size: "large", pinned: false },
];
const nav = [
  { name: "Overview", icon: LayoutDashboard, group: "WORKSPACE" },
  { name: "Race Engineer", icon: Activity, group: "ENGINEERING" },
  { name: "Performance Coach", icon: ChartNoAxesCombined, group: "ENGINEERING" },
  { name: "Corner Coach", icon: Gauge, group: "ENGINEERING" },
  { name: "Race Strategy", icon: Flag, group: "TOOLS" },
  { name: "Replay & Analysis", icon: Clock3, group: "TOOLS" },
  { name: "Hardware", icon: Cable, group: "SYSTEM" },
  { name: "Settings", icon: Settings, group: "SYSTEM" },
];
const fmt = (id: TileId) => definitions.find((d) => d.id === id)?.title ?? id;

function Meter({ label, value, tone = "purple" }: { label: string; value: number; tone?: string }) {
  return <div className="meter-row"><div className="meter-label"><span>{label}</span><b>{value}%</b></div><div className="meter-track"><i className={tone} style={{ width: value + "%" }} /></div></div>;
}
function TileContent({ id }: { id: TileId }) {
  switch (id) {
    case "speed": return <div className="hero-value"><strong>—</strong><span>km/h</span><small>Awaiting telemetry</small></div>;
    case "gear": return <div className="hero-value gear-value"><strong>N</strong><span>GEAR</span><small>Awaiting telemetry</small></div>;
    case "rpm": return <div className="rpm-content"><div className="rpm-number">— <small>RPM</small></div><div className="rpm-leds">{Array.from({ length: 15 }, (_, i) => <i key={i} />)}</div><div className="rpm-scale"><span>0</span><span>2k</span><span>4k</span><span>6k</span><span>8k</span></div></div>;
    case "pedals": return <div className="stacked-meters"><Meter label="Throttle" value={0} /><Meter label="Brake" value={0} tone="red" /><Meter label="Clutch" value={0} tone="teal" /></div>;
    case "laps": return <div className="lap-metrics"><div><span>CURRENT</span><b>—:—.---</b><small>Waiting for lap</small></div><div><span>LAST</span><b>—:—.---</b><small>Not available</small></div><div><span>BEST</span><b>—:—.---</b><small>Not available</small></div></div>;
    case "lap_history": return <div className="history-table"><div className="history-head"><span>LAP</span><span>TIME</span><span>DELTA</span><span>S1</span><span>S2</span><span>S3</span></div><div className="history-empty">Completed laps will appear here.</div></div>;
    case "weather": return <div className="weather-grid">{[["AIR TEMP","— °C"],["TRACK TEMP","— °C"],["WIND","— km/h"],["GRIP","—"],["RAIN NOW","— %"],["RAIN +10","— %"]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "map": return <div className="map-placeholder"><svg viewBox="0 0 360 180" role="img" aria-label="Track map placeholder"><path d="M36 105 C20 48 80 24 124 47 S196 22 235 47 S325 45 315 100 S258 147 218 122 S142 156 106 126 S53 153 36 105Z" /><circle cx="36" cy="105" r="5" /></svg><span>Track map will appear when circuit data is available</span></div>;
    case "session": return <div className="session-info"><div><span>TRACK</span><b>Waiting for ACC</b></div><div><span>SESSION</span><b>—</b></div><div><span>STATUS</span><b className="neutral-state">Not connected</b></div></div>;
    case "brakes": return <div className="corner-grid">{["FL","FR","RL","RR"].map((c) => <div key={c}><span>{c}</span><b>— °C</b><small>Brake disc</small></div>)}</div>;
    case "tyres": return <div className="corner-grid">{["FL","FR","RL","RR"].map((c) => <div key={c}><span>{c}</span><b>— psi</b><small>Core — °C</small></div>)}</div>;
    case "fuel": return <div className="fuel-content"><div className="fuel-main"><b>— <small>L</small></b><span>REMAINING</span></div><div className="fuel-track"><i /></div><div className="fuel-stats"><span>Estimated range <b>— laps</b></span><span>Consumption <b>— L/lap</b></span></div></div>;
    case "warnings": return <div className="warning-list"><div><span>Lap validity</span><b>Not available</b></div><div><span>Penalty time</span><b>—</b></div><p>ACC-reported warnings will be displayed here.</p></div>;
    case "hardware": return <div className="hardware-list">{["Wheel USB link","Wheel device","Pedals device","Handbrake device","RPM LED Controller"].map((d) => <div key={d}><span>{d}</span><b><i />Not reported</b></div>)}</div>;
  }
}
function App() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [active, setActive] = useState("Overview");
  const [tiles, setTiles] = useState<Tile[]>(initial);
  const [draft, setDraft] = useState<Tile[]>(initial);
  const [editing, setEditing] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [dragging, setDragging] = useState<TileId | null>(null);
  const ordered = useMemo(() => [...tiles.filter(t => t.pinned), ...tiles.filter(t => !t.pinned)], [tiles]);
  const shown = editing ? draft : ordered;
  const startEdit = () => { setDraft(ordered.map(t => ({...t}))); setEditing(true); };
  const cancel = () => { setDraft(ordered.map(t => ({...t}))); setEditing(false); setLibraryOpen(false); };
  const save = () => { setTiles(draft); setEditing(false); setLibraryOpen(false); };
  const update = (id: TileId, patch: Partial<Tile>) => setDraft(prev => prev.map(t => t.id === id ? {...t, ...patch} : t));
  const add = (id: TileId) => setDraft(prev => [...prev, {id, size: "medium", pinned: false}]);
  const remove = (id: TileId) => setDraft(prev => prev.filter(t => t.id !== id));
  const move = (from: TileId, to: TileId) => setDraft(prev => { const a = prev.findIndex(t=>t.id===from), b=prev.findIndex(t=>t.id===to); if(a<0||b<0||a===b)return prev; const next=[...prev]; const [item]=next.splice(a,1); next.splice(b,0,item); return next; });
  const reset = () => setDraft(initial.map(t=>({...t})));
  const groups = [...new Set(nav.map(n=>n.group))];
  return <div className="app-shell" data-theme={theme}>
    <aside className="navigation-rail"><div className="brand"><div className="brand-mark">RE</div><div className="brand-copy"><strong>RACE ENGINEER</strong><span>ASSETTO CORSA COMPETIZIONE</span></div></div><nav>{groups.map(group=><div className="nav-group" key={group}><div className="nav-heading">{group}</div>{nav.filter(n=>n.group===group).map(item=>{const Icon=item.icon;return <button key={item.name} className={active===item.name?"nav-item selected":"nav-item"} onClick={()=>setActive(item.name)} title={item.name}><Icon size={19}/><span>{item.name}</span></button>;})}</div>)}</nav><div className="rail-footer"><span className="status-dot"/><span>ACC NOT CONNECTED</span></div></aside>
    <main className="main-content"><header className="top-bar"><div><div className="eyebrow">RACE ENGINEER ACC</div><h1>{active}</h1></div><div className="top-bar-actions"><div className="prototype-state"><span/>DEMO · NOT CONNECTED</div><button className="theme-toggle" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")} title="Toggle theme">{theme==="dark"?<Sun size={16}/>:<Moon size={16}/>}<span>{theme==="dark"?"Light":"Dark"}</span></button></div></header>
      {active==="Overview" ? <section className="workspace overview-page"><div className="overview-heading"><div><div className="eyebrow">LIVE APPLICATION STATUS</div><h2>Race overview</h2><p>A focused view of your current ACC session and connected hardware.</p></div><div className="overview-heading-actions"><div className="connection-chip"><span/>ACC DISCONNECTED</div>{!editing?<button className="primary-action" onClick={startEdit}>Edit dashboard</button>:<><button className="secondary-action" onClick={()=>setLibraryOpen(v=>!v)}><Plus size={15}/> Add tiles</button><button className="primary-action" onClick={save}><Save size={15}/> Save</button><button className="secondary-action" onClick={cancel}><X size={15}/> Cancel</button></>}</div></div>
      {editing&&<div className="dashboard-editor"><div><strong>Edit Overview</strong><span>Drag unpinned tiles to reorder. Pinned tiles stay in the top section.</span></div><button className="text-action" onClick={reset}><RotateCcw size={14}/> Reset to default</button></div>}
      {editing&&libraryOpen&&<div className="tile-library"><div className="tile-library-heading"><strong>Available tiles</strong><button className="text-action" onClick={()=>setLibraryOpen(false)}>Close</button></div><div className="tile-library-grid">{definitions.filter(d=>!draft.some(t=>t.id===d.id)).map(d=><button className="library-item" key={d.id} onClick={()=>add(d.id)}><strong><Plus size={14}/>{d.title}</strong><span>{d.description}</span></button>)}</div></div>}
      <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const el=(e.target as HTMLElement).closest("[data-tile-id]");const to=el?.getAttribute("data-tile-id") as TileId|null;if(dragging&&to)move(dragging,to);setDragging(null);}}>
        {shown.map(tile=><div key={tile.id} data-tile-id={tile.id} draggable={editing&&!tile.pinned} onDragStart={()=>setDragging(tile.id)} onDragEnd={()=>setDragging(null)} className={`tile-drag-wrapper tile-slot-${tile.size} ${tile.id==="hardware"?"tile-slot-hardware":""}`}>
          <article className="dashboard-tile"><div className="tile-heading"><div><span className="tile-icon">{tile.id==="speed"?<Gauge/>:tile.id==="gear"?<Zap/>:tile.id==="rpm"?<Activity/>:tile.id==="pedals"?<Waves/>:tile.id==="laps"?<Flag/>:tile.id==="lap_history"?<Clock3/>:tile.id==="weather"?<CloudSun/>:tile.id==="map"?<Map/>:tile.id==="session"?<Radio/>:tile.id==="brakes"?<Thermometer/>:tile.id==="tyres"?<CircleGauge/>:tile.id==="fuel"?<Fuel/>:tile.id==="warnings"?<TriangleAlert/>:<Cable/>}</span><h3>{fmt(tile.id)}</h3></div>{editing&&<span className="drag-grip"><GripVertical size={17}/></span>}</div><div className="tile-body"><TileContent id={tile.id}/></div></article>
          {editing&&<div className="tile-size-control"><label>Size <select value={tile.size} onChange={e=>update(tile.id,{size:e.target.value as TileSize})}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></label><button className="text-action" onClick={()=>update(tile.id,{pinned:!tile.pinned})}>{tile.pinned?<PinOff size={13}/>:<Pin size={13}/>} {tile.pinned?"Unpin":"Pin"}</button><button className="remove-tile" onClick={()=>remove(tile.id)} aria-label={`Remove ${fmt(tile.id)} tile`}><X size={14}/></button></div>}
        </div>)}
      </div></section> : <section className="workspace"><div className="page-placeholder"><div className="placeholder-mark">RE</div><h2>{active}</h2><p>This workspace will be added in a later implementation stage.</p><span className="pending-label">NOT INTEGRATED</span></div></section>}
      <footer className="demo-footnote"><span><Droplets size={13}/> UI PREVIEW ONLY</span><span>Values are placeholders · No telemetry connection is active</span></footer>
    </main>
  </div>;
}
export default App;
