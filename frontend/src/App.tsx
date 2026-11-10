import { useMemo, useState } from "react";
import {
  Activity, Gauge, Flag, ChartNoAxesCombined, CloudSun, Map, Fuel,
  Thermometer, CircleGauge, Cable, Settings, Radio, ChevronDown,
  Plus, RotateCcw, Save, X, GripVertical, Pin, PinOff, Moon, Sun,
  LayoutDashboard, Waves, TriangleAlert, Clock3, Zap, Droplets,
  Timer, ChartNoAxesColumnIncreasing, Medal, SlidersHorizontal, Wrench, Target, Siren,
} from "lucide-react";

type TileId = "speed" | "gear" | "rpm" | "pedals" | "laps" | "lap_history" | "weather" | "map" | "session" | "brakes" | "tyres" | "fuel" | "warnings" | "hardware" | "delta" | "sectors" | "position" | "electronics" | "pit_stint" | "damage" | "pressure_targets" | "race_control";
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
  { id: "delta", title: "Delta to best lap", description: "Live time difference to the reference lap" },
  { id: "sectors", title: "Sector performance", description: "Current sector times and best-sector deltas" },
  { id: "position", title: "Race position & gaps", description: "Position and gaps to cars ahead and behind" },
  { id: "electronics", title: "Car electronics", description: "ABS, traction control and brake bias" },
  { id: "pit_stint", title: "Pit stop & stint", description: "Pit status, stint duration and stop information" },
  { id: "damage", title: "Vehicle damage", description: "ACC-reported vehicle damage status" },
  { id: "pressure_targets", title: "Tyre pressure targets", description: "Actual pressures compared with target pressures" },
  { id: "race_control", title: "Race control", description: "Flags, warnings and race-control messages" },
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
  { id: "delta", size: "medium", pinned: false },
  { id: "sectors", size: "medium", pinned: false },
  { id: "position", size: "medium", pinned: false },
  { id: "electronics", size: "medium", pinned: false },
  { id: "pit_stint", size: "medium", pinned: false },
  { id: "damage", size: "medium", pinned: false },
  { id: "pressure_targets", size: "large", pinned: false },
  { id: "race_control", size: "medium", pinned: false },
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
function loadLayout(): Tile[] {
  try {
    const raw = window.localStorage.getItem("acc-overview-layout");
    if (!raw) return initial;
    const saved = JSON.parse(raw) as Tile[];
    if (!Array.isArray(saved)) return initial;
    const valid = saved.filter((item): item is Tile => !!item && definitions.some(d => d.id === item.id) && ["small", "medium", "large"].includes(item.size) && typeof item.pinned === "boolean");
    const unique = valid.filter((item, index, list) => list.findIndex(other => other.id === item.id) === index);
    const missing = initial.filter(item => !unique.some(savedItem => savedItem.id === item.id));
    return [...unique, ...missing];
  } catch { return initial; }
}

function Meter({ label, value, tone = "purple" }: { label: string; value: number; tone?: string }) {
  return <div className="meter-row"><div className="meter-label"><span>{label}</span><b>{value}%</b></div><div className="meter-track"><i className={tone} style={{ width: value + "%" }} /></div></div>;
}
function TileContent({ id }: { id: TileId }) {
  switch (id) {
    case "speed": return <div className="hero-value"><strong>—</strong><span>km/h</span><small>Awaiting telemetry</small></div>;
    case "gear": return <div className="hero-value gear-value"><strong>N</strong><span>GEAR</span><small>Awaiting telemetry</small></div>;
    case "rpm": return <div className="rpm-content"><div className="rpm-number">— <small>RPM</small></div><div className="rpm-leds">{Array.from({ length: 15 }, (_, i) => <i key={i} />)}</div><div className="rpm-scale"><span>0</span><span>2k</span><span>4k</span><span>6k</span><span>8k</span></div></div>;
    case "pedals": return <div className="stacked-meters"><Meter label="Throttle" value={0} /><Meter label="Brake" value={0} tone="red" /><Meter label="Clutch" value={0} tone="teal" /></div>;
    case "laps": return <div className="lap-metrics"><div><span>CURRENT LAP</span><b>—:—.---</b><small>Lap — · validity —</small></div><div><span>LAST LAP</span><b>—:—.---</b><small>Last completed lap</small></div><div><span>BEST LAP</span><b>—:—.---</b><small>Session best</small></div></div>;
    case "lap_history": return <div className="history-table"><div className="history-head"><span>LAP</span><span>TIME</span><span>DELTA</span><span>S1</span><span>S2</span><span>S3</span></div><div className="history-empty">Completed laps will appear here.</div></div>;
    case "weather": return <div className="field-grid">{[["AIR TEMP","— °C"],["ROAD TEMP","— °C"],["WIND SPEED","— km/h"],["WIND DIRECTION","— °"],["RAIN INTENSITY","—"],["RAIN FORECAST","—"],["TRACK GRIP","—"]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "map": return <div className="map-placeholder"><svg viewBox="0 0 360 180" role="img" aria-label="Track map placeholder"><path d="M36 105 C20 48 80 24 124 47 S196 22 235 47 S325 45 315 100 S258 147 218 122 S142 156 106 126 S53 153 36 105Z" /><circle cx="36" cy="105" r="5" /></svg><span>Track map will appear when circuit data is available</span></div>;
    case "session": return <div className="field-rows">{[["TRACK","—"],["CAR MODEL","—"],["SESSION TYPE","—"],["SESSION STATUS","—"],["SESSION TIME LEFT","—:—"],["LAP COUNT","—"],["ACTIVE CARS","—"],["CURRENT POSITION","—"]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "brakes": return <div className="corner-grid extended-corners">{["FL","FR","RL","RR"].map((c) => <div key={c}><span>{c}</span><b>— °C</b><small>Disc temperature</small><small>Pressure —</small><small>Pad life —</small><small>Disc life —</small></div>)}<p>Front compound — · Rear compound —</p></div>;
    case "tyres": return <div className="corner-grid extended-corners">{["FL","FR","RL","RR"].map((c) => <div key={c}><span>{c}</span><b>— psi</b><small>Core temp — °C</small><small>Slip —</small><small>Slip ratio —</small><small>Slip angle — °</small></div>)}</div>;
    case "fuel": return <div className="fuel-content"><div className="fuel-main"><b>— <small>L</small></b><span>REMAINING FUEL</span></div><div className="fuel-track"><i /></div><div className="field-rows compact"><div><span>FUEL PER LAP (ACC)</span><b>— L/lap</b></div><div><span>ESTIMATED LAPS LEFT (CALCULATED)</span><b>—</b></div><div><span>FUEL USED THIS LAP</span><b>— L</b></div></div></div>;
    case "warnings": return <div className="field-rows">{[["LAP VALIDITY","—"],["PENALTY TYPE","—"],["PENALTY TIME","—"],["PENALTY SERVED","—"],["CURRENT FLAG","—"],["GLOBAL FLAG","—"],["MANDATORY PIT","—"]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "hardware": return <div className="hardware-list">{["Wheel USB link","Wheel device","Pedals device","Handbrake device","RPM LED Controller"].map((d) => <div key={d}><span>{d}</span><b><i />Not reported</b></div>)}</div>;
    case "delta": return <div className="field-rows"><div><span>DELTA TO REFERENCE (ACC)</span><b>—.---</b></div><div><span>ESTIMATED LAP TIME (ACC)</span><b>—:—.---</b></div><div><span>DELTA TO STORED BEST (CALCULATED)</span><b>—.---</b></div><div><span>REFERENCE LAP</span><b>Best lap —</b></div></div>;
    case "sectors": return <div className="field-rows"><div><span>CURRENT SECTOR INDEX (ACC)</span><b>—</b></div><div><span>LAST SECTOR TIME (ACC)</span><b>—:—.---</b></div><div><span>LIVE SPLIT (ACC)</span><b>—:—.---</b></div><div><span>SECTOR 1 / 2 / 3</span><b>— / — / —</b></div><div><span>BEST SECTORS (CAPTURED)</span><b>— / — / —</b></div><div><span>DELTA TO BEST SECTORS (CALC)</span><b>— / — / —</b></div></div>;
    case "position": return <div className="field-rows"><div><span>POSITION (ACC)</span><b>—</b></div><div><span>ACTIVE CARS (ACC)</span><b>—</b></div><div><span>GAP AHEAD (ACC)</span><b>—</b></div><div><span>GAP BEHIND (ACC)</span><b>—</b></div></div>;
    case "electronics": return <div className="field-rows"><div><span>TRACTION CONTROL LEVEL (ACC)</span><b>—</b></div><div><span>TC CUT LEVEL (ACC)</span><b>—</b></div><div><span>ABS LEVEL (ACC)</span><b>—</b></div><div><span>ENGINE MAP (ACC)</span><b>—</b></div><div><span>BRAKE BIAS (ACC)</span><b>— %</b></div><div><span>TC INTERVENTION ACTIVE (ACC)</span><b>—</b></div><div><span>ABS INTERVENTION ACTIVE (ACC)</span><b>—</b></div><div><span>PIT LIMITER (ACC)</span><b>—</b></div><div><span>AUTO SHIFTER (ACC)</span><b>—</b></div><div><span>IGNITION / STARTER (ACC)</span><b>— / —</b></div><div><span>ENGINE RUNNING (ACC)</span><b>—</b></div><div><span>DRS STATE (IF SUPPORTED)</span><b>—</b></div></div>;
    case "pit_stint": return <div className="field-rows"><div><span>IN PIT (ACC)</span><b>—</b></div><div><span>IN PIT LANE (ACC)</span><b>—</b></div><div><span>MANDATORY PIT DONE (ACC)</span><b>—</b></div><div><span>PIT WINDOW START / END (STATIC)</span><b>— / —</b></div><div><span>DRIVER STINT TIME (ACC)</span><b>—:—</b></div><div><span>LAST PIT DURATION (CALCULATED)</span><b>—:—</b></div><div><span>TIME IN CURRENT PIT (CALCULATED)</span><b>—:—</b></div></div>;
    case "damage": return <div className="field-rows"><div><span>CAR DAMAGE (ACC ARRAY)</span><b>— / — / — / — / —</b></div><div><span>SUSPENSION FL / FR / RL / RR</span><b>— / — / — / —</b></div><div><span>BRAKE PAD LIFE FL / FR / RL / RR</span><b>— / — / — / —</b></div><div><span>BRAKE DISC LIFE FL / FR / RL / RR</span><b>— / — / — / —</b></div><div><span>DAMAGE SUMMARY (DERIVED)</span><b>—</b></div></div>;
    case "pressure_targets": return <div className="pressure-target-grid">{["FL","FR","RL","RR"].map((v) => <div key={v}><strong>{v}</strong><b>Actual — psi</b><span>MFD setting — psi</span><small>Actual − MFD — psi</small></div>)}<p>MFD pressure is shown as the car's displayed setting, not assumed to be an ideal setup target.</p></div>;
    case "race_control": return <div className="field-rows"><div><span>FLAG (ACC)</span><b>—</b></div><div><span>GLOBAL FLAG (ACC)</span><b>—</b></div><div><span>PENALTY TYPE (ACC)</span><b>—</b></div><div><span>PENALTY TIME (ACC)</span><b>—</b></div><div><span>MANDATORY PIT STATUS (ACC)</span><b>—</b></div><div><span>RACE CONTROL MESSAGE</span><b>—</b></div></div>;
  }
}
function App() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [active, setActive] = useState("Overview");
  const [tiles, setTiles] = useState<Tile[]>(loadLayout);
  const [draft, setDraft] = useState<Tile[]>(initial);
  const [editing, setEditing] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [dragging, setDragging] = useState<TileId | null>(null);
  const ordered = useMemo(() => [...tiles.filter(t => t.pinned), ...tiles.filter(t => !t.pinned)], [tiles]);
  const shown = editing ? draft : ordered;
  const startEdit = () => { setDraft(ordered.map(t => ({...t}))); setEditing(true); };
  const cancel = () => { setDraft(ordered.map(t => ({...t}))); setEditing(false); setLibraryOpen(false); };
  const save = () => { try { window.localStorage.setItem("acc-overview-layout", JSON.stringify(draft)); } catch { /* Layout remains available for this session. */ } setTiles(draft); setEditing(false); setLibraryOpen(false); };
  const update = (id: TileId, patch: Partial<Tile>) => setDraft(prev => prev.map(t => t.id === id ? {...t, ...patch} : t));
  const add = (id: TileId) => setDraft(prev => [...prev, {id, size: "medium", pinned: false}]);
  const remove = (id: TileId) => setDraft(prev => prev.filter(t => t.id !== id));
  const move = (from: TileId, to: TileId) => setDraft(prev => { const a = prev.findIndex(t=>t.id===from), b=prev.findIndex(t=>t.id===to); if(a<0||b<0||a===b)return prev; const next=[...prev]; const [item]=next.splice(a,1); next.splice(b,0,item); return next; });
  const reset = () => setDraft(initial.map(t=>({...t})));
  const groups = [...new Set(nav.map(n=>n.group))];
  return <div className="app-shell" data-theme={theme}>
    <aside className="navigation-rail"><div className="brand" title="Race Engineer ACC"><div className="brand-mark">RE</div></div><nav aria-label="Main navigation">{groups.map(group=><div className="nav-group" key={group}>{nav.filter(n=>n.group===group).map(item=>{const Icon=item.icon;return <button key={item.name} className={active===item.name?"nav-item selected":"nav-item"} onClick={()=>setActive(item.name)} title={item.name} aria-label={item.name} data-tooltip={item.name}><Icon size={20}/></button>;})}</div>)}</nav><div className="rail-footer" title="ACC not connected"><span className="status-dot"/></div></aside>
    <main className="main-content"><header className="top-bar"><div><div className="eyebrow">RACE ENGINEER ACC</div><h1>{active}</h1></div><div className="top-bar-actions"><div className="prototype-state"><span/>DEMO · NOT CONNECTED</div><button className="theme-toggle" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")} title="Toggle theme">{theme==="dark"?<Sun size={16}/>:<Moon size={16}/>}<span>{theme==="dark"?"Light":"Dark"}</span></button></div></header>
      {active==="Overview" ? <section className="workspace overview-page"><div className="overview-heading"><div><div className="eyebrow">LIVE APPLICATION STATUS</div><h2>Race overview</h2><p>A focused view of your current ACC session and connected hardware.</p></div><div className="overview-heading-actions"><div className="connection-chip"><span/>ACC DISCONNECTED</div>{!editing?<button className="primary-action" onClick={startEdit}>Edit dashboard</button>:<><button className="secondary-action" onClick={()=>setLibraryOpen(v=>!v)}><Plus size={15}/> Add tiles</button><button className="primary-action" onClick={save}><Save size={15}/> Save</button><button className="secondary-action" onClick={cancel}><X size={15}/> Cancel</button></>}</div></div>
      {editing&&<div className="dashboard-editor"><div><strong>Edit Overview</strong><span>Drag unpinned tiles to reorder. Pinned tiles stay in the top section.</span></div><button className="text-action" onClick={reset}><RotateCcw size={14}/> Reset to default</button></div>}
      {editing&&libraryOpen&&<div className="tile-library"><div className="tile-library-heading"><strong>Available tiles</strong><button className="text-action" onClick={()=>setLibraryOpen(false)}>Close</button></div><div className="tile-library-grid">{definitions.filter(d=>!draft.some(t=>t.id===d.id)).map(d=><button className="library-item" key={d.id} onClick={()=>add(d.id)}><strong><Plus size={14}/>{d.title}</strong><span>{d.description}</span></button>)}</div></div>}
      <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const el=(e.target as HTMLElement).closest("[data-tile-id]");const to=el?.getAttribute("data-tile-id") as TileId|null;if(dragging&&to)move(dragging,to);setDragging(null);}}>
        {shown.map(tile=><div key={tile.id} data-tile-id={tile.id} draggable={editing&&!tile.pinned} onDragStart={()=>setDragging(tile.id)} onDragEnd={()=>setDragging(null)} className={`tile-drag-wrapper tile-slot-${tile.size} ${tile.id==="hardware"?"tile-slot-hardware":""}`}>
          <article className="dashboard-tile"><div className="tile-heading"><div><span className="tile-icon">{tile.id==="speed"?<Gauge/>:tile.id==="gear"?<Zap/>:tile.id==="rpm"?<Activity/>:tile.id==="pedals"?<Waves/>:tile.id==="laps"?<Flag/>:tile.id==="lap_history"?<Clock3/>:tile.id==="weather"?<CloudSun/>:tile.id==="map"?<Map/>:tile.id==="session"?<Radio/>:tile.id==="brakes"?<Thermometer/>:tile.id==="tyres"?<CircleGauge/>:tile.id==="fuel"?<Fuel/>:tile.id==="warnings"?<TriangleAlert/>:tile.id==="delta"?<ChartNoAxesColumnIncreasing/>:tile.id==="sectors"?<Timer/>:tile.id==="position"?<Medal/>:tile.id==="electronics"?<SlidersHorizontal/>:tile.id==="pit_stint"?<Timer/>:tile.id==="damage"?<Wrench/>:tile.id==="pressure_targets"?<Target/>:tile.id==="race_control"?<Siren/>:<Cable/>}</span><h3>{fmt(tile.id)}</h3></div>{editing&&<span className="drag-grip"><GripVertical size={17}/></span>}</div><div className="tile-body"><TileContent id={tile.id}/></div></article>
          {editing&&<div className="tile-size-control"><label>Size <select value={tile.size} onChange={e=>update(tile.id,{size:e.target.value as TileSize})}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></label><button className="text-action" onClick={()=>update(tile.id,{pinned:!tile.pinned})}>{tile.pinned?<PinOff size={13}/>:<Pin size={13}/>} {tile.pinned?"Unpin":"Pin"}</button><button className="remove-tile" onClick={()=>remove(tile.id)} aria-label={`Remove ${fmt(tile.id)} tile`}><X size={14}/></button></div>}
        </div>)}
      </div></section> : <section className="workspace"><div className="page-placeholder"><div className="placeholder-mark">RE</div><h2>{active}</h2><p>This workspace will be added in a later implementation stage.</p><span className="pending-label">NOT INTEGRATED</span></div></section>}
      <footer className="demo-footnote"><span><Droplets size={13}/> UI PREVIEW ONLY</span><span>Values are placeholders · No telemetry connection is active</span></footer>
    </main>
  </div>;
}
export default App;
