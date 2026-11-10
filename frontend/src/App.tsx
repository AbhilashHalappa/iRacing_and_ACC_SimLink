import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, Gauge, Flag, ChartNoAxesCombined, CloudSun, Map, Fuel,
  Thermometer, CircleGauge, Cable, Settings, Radio, ChevronDown,
  Plus, RotateCcw, Save, X, GripVertical, Pin, PinOff, Moon, Sun,
  LayoutDashboard, Waves, TriangleAlert, Clock3, Zap, Droplets,
  Timer, ChartNoAxesColumnIncreasing, Medal, SlidersHorizontal, Wrench, Target, Siren, Lightbulb,
} from "lucide-react";

type TileId = "speed" | "gear" | "rpm" | "pedals" | "laps" | "lap_history" | "weather" | "map" | "session" | "brakes" | "tyres" | "fuel" | "warnings" | "hardware" | "delta" | "sectors" | "position" | "electronics" | "pit_stint" | "damage" | "pressure_targets" | "race_control" | "car_status";
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
  { id: "car_status", title: "Car lights & status", description: "ACC lights, wipers, engine and vehicle status" },
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
  { id: "car_status", size: "medium", pinned: false },
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
type GlowConfig = { tyre:[number,number,number,number]; brake:[number,number,number,number]; damage:[number,number,number]; intensity:number; lapStatus:"valid"|"invalid"|"out" };
const defaultGlow:GlowConfig={tyre:[70,90,100,110],brake:[250,400,500,600],damage:[20,40,70],intensity:65,lapStatus:"valid"};
function readGlow():GlowConfig { try { const v=JSON.parse(window.localStorage.getItem("acc-glow-settings")||"null"); return v?{...defaultGlow,...v}:defaultGlow; } catch { return defaultGlow; } }
function band(value:number, thresholds:number[], prefix:string) { return prefix+"-"+(value<thresholds[0]?0:value<thresholds[1]?1:value<thresholds[2]?2:value<thresholds[3]?3:4); }
function statusTone(value:string) {
  const v=value.trim().toLowerCase();
  if (["on","true","1","enabled","active"].includes(v)) return "light-on";
  if (["off","false","0","disabled","inactive"].includes(v)) return "light-off";
  const numeric=Number(v);
  if (v!=="" && Number.isFinite(numeric)) return numeric>0?"light-on":"light-off";
  return "light-unknown";
}
function flagTone(value:string) {
  const v=value.trim().toLowerCase().replace(/[ _-]+/g,"");
  if (v.includes("chequer") || v.includes("checker")) return "checkered";
  if (v.includes("black") && (v.includes("orange") || v.includes("meatball"))) return "black-orange";
  if (v.includes("black")) return "black";
  if (v.includes("red")) return "red";
  if (v.includes("yellow")) return "yellow";
  if (v.includes("blue")) return "blue";
  if (v.includes("white")) return "white";
  if (v.includes("green")) return "green";
  return "unknown";
}
function ChangeGlowBox({label,value,primary=false}:{label:string;value:string;primary?:boolean}) {
  const [pulseId,setPulseId]=useState(0);
  const previous=useRef(value);
  useEffect(()=>{
    if(previous.current!==value) {
      previous.current=value;
      setPulseId(id=>id+1);
    }
  },[value]);
  return <div key={pulseId} className={`${primary?"electronics-primary-box":"balanced-field"} value-change-glow${pulseId>0?" is-changing":""}`}><span>{label}</span><b>{value}</b></div>;
}
function display(value: unknown, digits=1, suffix="") { return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits)+suffix : "—"; }
function TileContent({ id, glow, telemetry }: { id: TileId; glow:GlowConfig; telemetry:any }) {
  const data=telemetry?.physics?.data ?? null;
  const wheels=data?.wheels ?? {};
  const corners=["FL","FR","RL","RR"];
  switch (id) {
    case "speed": return <div className="hero-value glance-hero"><strong>{display(data?.speed_kph,0)}</strong><span>KM/H</span><small>VEHICLE SPEED · ACC PHYSICS</small></div>;
    case "gear": return <div className="hero-value gear-value glance-hero"><strong>{data?.gear_display ?? "—"}</strong><span>GEAR</span><small>ACC PHYSICS</small></div>;
    case "rpm": { const rpm=Number(data?.rpm??0); const max=Number(data?.current_max_rpm??9000); const lit=max>0?Math.max(0,Math.min(15,Math.round(rpm/max*15))):0; return <div className="rpm-content glance-rpm"><div className="rpm-number">{display(data?.rpm,0)} <small>RPM</small></div><div className="rpm-leds">{Array.from({ length: 15 }, (_, i) => <i key={i} className={i<lit?"active":""}/> )}</div><div className="rpm-scale"><span>0</span><span>{display(max/4,0)}</span><span>{display(max/2,0)}</span><span>{display(max,0)}</span></div><small className="glance-hint">ACC PHYSICS · MAX {display(max,0)} RPM</small></div>; }
    case "pedals": return <div className="stacked-meters glance-pedals"><Meter label="THROTTLE" value={Math.max(0,Math.min(100,Number(data?.throttle??0)*100))}/><Meter label="BRAKE" value={Math.max(0,Math.min(100,Number(data?.brake??0)*100))} tone="red"/><Meter label="CLUTCH" value={Math.max(0,Math.min(100,Number(data?.clutch??0)*100))} tone="teal"/></div>;
    case "laps": return <div className={`lap-metrics glance-laps lap-glow lap-${glow.lapStatus}`} style={{"--glow-intensity":glow.intensity/100,"--glow-blur":`${5+12*glow.intensity/100}px`} as React.CSSProperties}><div className="lap-primary"><span>CURRENT</span><b>—:—.---</b><small>LAP — · VALIDITY —</small></div><div><span>LAST</span><b>—:—.---</b></div><div><span>BEST</span><b>—:—.---</b></div></div>;
    case "lap_history": return <div className="history-table"><div className="history-head"><span>LAP</span><span>TIME</span><span>DELTA</span><span>S1</span><span>S2</span><span>S3</span></div><div className="history-empty">Completed laps will appear here.</div></div>;
    case "weather": return <div className="field-grid balanced-grid glance-weather">{[["ROAD TEMP","— °C"],["AIR TEMP","— °C"],["TRACK GRIP","—"],["RAIN","—"],["RAIN FORECAST","—"],["WIND","— km/h"],["WIND DIRECTION","— °"]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "map": return <div className="map-placeholder"><svg viewBox="0 0 360 180" role="img" aria-label="Track map placeholder"><path d="M36 105 C20 48 80 24 124 47 S196 22 235 47 S325 45 315 100 S258 147 218 122 S142 156 106 126 S53 153 36 105Z" /><circle cx="36" cy="105" r="5" /></svg><span>Track map will appear when circuit data is available</span></div>;
    case "session": return <div className="balanced-grid">{[["TRACK","—"],["CAR MODEL","—"],["SESSION TYPE","—"],["SESSION STATUS","—"],["SESSION TIME LEFT","—:—"],["LAP COUNT","—"],["ACTIVE CARS","—"],["CURRENT POSITION","—"]].map(([a,b]) => <div className="balanced-field" key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "brakes": return <div className="corner-grid extended-corners glance-corners glow-corners" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const w=wheels[c]??{};const t=w.brake_temp_c;return <div key={c} className={typeof t==="number"?band(t,glow.brake,"glow"):""}><span>{c}</span><b>{display(t,0,"°C")}</b><small>DISC TEMP · ACC</small><small>Pressure {display(w.brake_pressure,1)}</small><small>Pad {display(w.pad_life,1)} · Disc {display(w.disc_life,1)}</small></div>})}</div>;
    case "tyres": return <div className="corner-grid extended-corners glance-corners glance-tyres glow-corners" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const w=wheels[c]??{};const t=w.tyre_core_temp_c;return <div key={c} className={typeof t==="number"?band(t,glow.tyre,"glow"):""}><span>{c}</span><b>{display(t,0,"°C")}</b><small>CORE TEMP · ACC</small><small>Pressure {display(w.tyre_pressure_psi,1," psi")}</small><small>Slip {display(w.slip_ratio,2)} · Angle {display(w.slip_angle,1,"°")}</small></div>})}</div>;
    case "fuel": return <div className="fuel-content glance-fuel"><div className="fuel-main"><b>{display(data?.fuel_kg,1)} <small>KG</small></b><span>REMAINING · ACC</span></div><div className="fuel-track"><i style={{width:"0%"}}/></div><div className="glance-inline-stats"><div><span>EST. LAPS LEFT</span><b>—</b></div><div><span>FUEL / LAP</span><b>— kg</b></div></div><small className="glance-footnote">Fuel is reported by ACC in kilograms.</small></div>;
    case "warnings": return <div className="balanced-grid">{[["LAP VALIDITY","—"],["PENALTY TYPE","—"],["PENALTY TIME","—"],["PENALTY SERVED","—"],["CURRENT FLAG","—"],["GLOBAL FLAG","—"],["MANDATORY PIT","—"]].map(([a,b]) => <div className="balanced-field" key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "hardware": return <div className="hardware-list balanced-hardware">{["Wheel USB link","Wheel device","Pedals device","Handbrake device","RPM LED Controller"].map((d) => <div key={d}><span>{d}</span><b><i />Not reported</b></div>)}</div>;
    case "delta": return <div className="glance-delta"><div className="glance-delta-primary"><span>LIVE DELTA · ACC</span><strong>—.---</strong><small>TO REFERENCE LAP</small></div><div className="glance-inline-stats"><div><span>EST. LAP</span><b>—:—.---</b></div><div><span>DELTA TO STORED BEST</span><b>—.---</b></div></div><small className="glance-footnote">Reference: best lap —</small></div>;
    case "sectors": return <div className="glance-sector"><div className="glance-inline-stats"><div><span>LIVE SPLIT</span><b>—:—.---</b></div><div><span>LAST SECTOR</span><b>—:—.---</b></div><div><span>SECTOR</span><b>— / 3</b></div></div><div className="sector-strip">{["S1","S2","S3"].map(s=><div key={s}><span>{s}</span><b>—.---</b><small>Δ —.---</small></div>)}</div><small className="glance-footnote">Captured best sectors · delta calculated</small></div>;
    case "position": return <div className="glance-position"><div className="glance-position-hero"><strong>—</strong><span>POSITION</span><small>OF — CARS</small></div><div className="glance-inline-stats"><div><span>GAP AHEAD</span><b>—</b></div><div><span>GAP BEHIND</span><b>—</b></div></div></div>;
    case "electronics": return <div className="glance-electronics"><div className="electronics-primary"><ChangeGlowBox primary label="TC LEVEL" value={display(data?.tc_level,0)}/><ChangeGlowBox primary label="ABS LEVEL" value={display(data?.abs_level,0)}/><ChangeGlowBox primary label="BRAKE BIAS" value={display(typeof data?.brake_bias==="number"?data.brake_bias*100:null,1,"%")}/><ChangeGlowBox primary label="WATER TEMP" value={display(data?.water_temp_c,0,"°C")}/></div><div className="balanced-grid electronics-secondary"><ChangeGlowBox label="TC INTERVENTION" value={data?String(Boolean(data.tc_in_action)):"—"}/><ChangeGlowBox label="ABS INTERVENTION" value={data?String(Boolean(data.abs_in_action)):"—"}/><ChangeGlowBox label="PIT LIMITER" value={data?String(Boolean(data.pit_limiter_on)):"—"}/><ChangeGlowBox label="IGNITION" value={data?String(Boolean(data.ignition_on)):"—"}/><ChangeGlowBox label="STARTER" value={data?String(Boolean(data.starter_engine_on)):"—"}/><ChangeGlowBox label="ENGINE RUNNING" value={data?String(Boolean(data.engine_running)):"—"}/><ChangeGlowBox label="AUTO SHIFTER" value={data?String(Boolean(data.autoshifter_on)):"—"}/><ChangeGlowBox label="TURBO BOOST" value={display(data?.turbo_boost,2)}/><ChangeGlowBox label="DRS*" value="Not exposed"/></div><small className="glance-footnote">Values are decoded from the ACC Physics stream. Unsupported car-specific controls remain unavailable.</small></div>;
    case "pit_stint": return <div className="glance-pit"><div className="electronics-primary three-up"><div><span>IN PIT</span><b>—</b></div><div><span>IN PIT LANE</span><b>—</b></div><div><span>MANDATORY STOP</span><b>—</b></div></div><div className="balanced-grid pit-secondary"><div className="balanced-field"><span>DRIVER STINT</span><b>—:—</b></div><div className="balanced-field"><span>PIT WINDOW</span><b>— – —</b></div><div className="balanced-field"><span>LAST PIT DURATION</span><b>—:—</b></div><div className="balanced-field"><span>TIME IN CURRENT PIT</span><b>—:—</b></div></div></div>;
    case "damage": return <div className="damage-layout"><div className="damage-summary balanced-grid"><div className="balanced-field"><span>ACC CAR DAMAGE ARRAY</span><b>{data?.car_damage?.map((v:number)=>display(v,2)).join(" / ")??"—"}</b></div><div className="balanced-field"><span>ENGINE / WATER TEMP</span><b>{display(data?.water_temp_c,0," °C")}</b></div></div><section className="damage-corner-group"><h4>SUSPENSION DAMAGE · ACC</h4><div className="corner-grid glance-corners glow-corners damage-glows" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const v=wheels[c]?.suspension_damage;const pct=typeof v==="number"?Math.max(0,Math.min(100,v*100)):null;return <div key={c} className={pct===null?"":`damage-${pct<glow.damage[0]?0:pct<glow.damage[1]?1:pct<glow.damage[2]?2:3}`}><span>{c}</span><b>{display(pct,1,"%")}</b><small>SUSPENSION · ACC</small></div>})}</div></section></div>;
    case "pressure_targets": return <div className="pressure-target-layout"><div className="corner-grid glance-corners pressure-target-grid">{["FL","FR","RL","RR"].map((v)=><div key={v}><span>{v}</span><b>Actual — psi</b><small>MFD setting — psi</small><small>Actual − MFD — psi</small></div>)}</div><p>MFD pressure is shown as the displayed setting, not assumed to be an ideal setup target.</p></div>;
    case "race_control": return <div className="balanced-grid race-control-grid">{[["FLAG (ACC)","—"],["GLOBAL FLAG (ACC)","—"],["PENALTY TYPE (ACC)","—"],["PENALTY TIME (ACC)","—"],["MANDATORY PIT STATUS (ACC)","—"]].map(([a,b])=><div className={`balanced-field ${a.includes("FLAG")?"race-flag-field flag-"+flagTone(b):""}`} key={a}><span>{a}</span><b>{b}</b></div>)}<div className="balanced-field message-field"><span>RACE CONTROL MESSAGE</span><b>—</b></div></div>;
    case "car_status": return <div className="balanced-grid car-status-grid">{[["PIT LIMITER (ACC)",data?String(Boolean(data.pit_limiter_on)):"—"],["ENGINE RUNNING (ACC)",data?String(Boolean(data.engine_running)):"—"],["IGNITION (ACC)",data?String(Boolean(data.ignition_on)):"—"],["STARTER (ACC)",data?String(Boolean(data.starter_engine_on)):"—"],["AI CONTROLLED (ACC)",data?String(Boolean(data.is_ai_controlled)):"—"],["WATER TEMP (ACC)",display(data?.water_temp_c,0," °C")],["AIR TEMP (ACC)",display(data?.air_temp_c,0," °C")],["ROAD TEMP (ACC)",display(data?.road_temp_c,0," °C")]].map(([a,b])=><div className="balanced-field" key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
  }
}
function App() {
  const [telemetry,setTelemetry]=useState<any>(null);
  useEffect(()=>{const events=new EventSource("/events");events.onmessage=event=>{try{setTelemetry(JSON.parse(event.data));}catch{/* Ignore malformed bridge frames. */}};events.onerror=()=>setTelemetry((current:any)=>current?{...current,connected:false}:current);return ()=>events.close();},[]);
  const connected=Boolean(telemetry?.connected);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [active, setActive] = useState("Overview");
  const [tiles, setTiles] = useState<Tile[]>(loadLayout);
  const [draft, setDraft] = useState<Tile[]>(initial);
  const [editing, setEditing] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [dragging, setDragging] = useState<TileId | null>(null);
  const [glow,setGlow] = useState<GlowConfig>(readGlow);
  const patchGlow=(patch:Partial<GlowConfig>)=>setGlow(prev=>{const next={...prev,...patch};try{window.localStorage.setItem("acc-glow-settings",JSON.stringify(next));}catch{}return next;});
  const setBand=(key:"tyre"|"brake"|"damage",index:number,value:number)=>setGlow(prev=>{const next={...prev,[key]:prev[key].map((v,i)=>i===index?value:v)} as GlowConfig;try{window.localStorage.setItem("acc-glow-settings",JSON.stringify(next));}catch{}return next;});
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
    <main className="main-content"><header className="top-bar"><div><div className="eyebrow">RACE ENGINEER ACC</div><h1>{active}</h1></div><div className="top-bar-actions"><div className="prototype-state"><span className={connected?"connected":""}/>{connected?"ACC PHYSICS · LIVE":"WAITING FOR ACC"}</div><button className="theme-toggle" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")} title="Toggle theme">{theme==="dark"?<Sun size={16}/>:<Moon size={16}/>}<span>{theme==="dark"?"Light":"Dark"}</span></button></div></header>
      {active==="Settings" ? <section className="workspace settings-page"><div className="overview-heading"><div><div className="eyebrow">VISUAL FEEDBACK</div><h2>Telemetry glow settings</h2><p>Configure colour thresholds and glow strength. Defaults are preview values, not validated Porsche setup limits.</p></div><button className="secondary-action" onClick={()=>{setGlow(defaultGlow);try{window.localStorage.setItem("acc-glow-settings",JSON.stringify(defaultGlow));}catch{}}}><RotateCcw size={14}/> Reset defaults</button></div>
        <div className="settings-panel"><h3>Tyre core temperature · °C</h3><p>Blue, green, yellow, orange and red temperature bands.</p><div className="threshold-row">{glow.tyre.map((v,i)=><label key={i}>{["Blue → Green","Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" value={v} onChange={e=>setBand("tyre",i,Number(e.target.value))}/></label>)}</div></div>
        <div className="settings-panel"><h3>Brake disc temperature · °C</h3><p>Independent configurable bands for Porsche 992 GT3 R.</p><div className="threshold-row">{glow.brake.map((v,i)=><label key={i}>{["Blue → Green","Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" value={v} onChange={e=>setBand("brake",i,Number(e.target.value))}/></label>)}</div></div>
        <div className="settings-panel"><h3>Vehicle damage · %</h3><p>Severity bands for the displayed damage percentage.</p><div className="threshold-row">{glow.damage.map((v,i)=><label key={i}>{["Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" min="0" max="100" value={v} onChange={e=>setBand("damage",i,Number(e.target.value))}/></label>)}</div></div>
        <div className="settings-panel"><h3>Lap status glow</h3><p>Preview the lap tile using a selected status.</p><select value={glow.lapStatus} onChange={e=>patchGlow({lapStatus:e.target.value as GlowConfig["lapStatus"]})}><option value="valid">Valid · Green</option><option value="invalid">Invalid · Red</option><option value="out">Out lap · Orange</option></select></div>
        <div className="settings-panel"><h3>Glow intensity · {glow.intensity}%</h3><input className="intensity-slider" type="range" min="10" max="100" value={glow.intensity} onChange={e=>patchGlow({intensity:Number(e.target.value)})}/></div>
        <div className="settings-panel"><h3>Preview guide</h3><div className="glow-legend">{["BLUE","GREEN","YELLOW","ORANGE","RED"].map((v,i)=><span key={v} className={"glow-"+i}>{v}</span>)}</div><p>Static sample readings are shown in the Overview brake, tyre and damage tiles to test glow appearance.</p></div>
      </section> : active==="Overview" ? <section className="workspace overview-page"><div className="overview-heading"><div><div className="eyebrow">LIVE APPLICATION STATUS</div><h2>Race overview</h2><p>A focused view of your current ACC session and connected hardware.</p></div><div className="overview-heading-actions"><div className="connection-chip"><span className={connected?"connected":""}/>{connected?"ACC PHYSICS CONNECTED":"ACC DISCONNECTED"}</div>{!editing?<button className="primary-action" onClick={startEdit}>Edit dashboard</button>:<><button className="secondary-action" onClick={()=>setLibraryOpen(v=>!v)}><Plus size={15}/> Add tiles</button><button className="primary-action" onClick={save}><Save size={15}/> Save</button><button className="secondary-action" onClick={cancel}><X size={15}/> Cancel</button></>}</div></div>
      {editing&&<div className="dashboard-editor"><div><strong>Edit Overview</strong><span>Drag unpinned tiles to reorder. Pinned tiles stay in the top section.</span></div><button className="text-action" onClick={reset}><RotateCcw size={14}/> Reset to default</button></div>}
      {editing&&libraryOpen&&<div className="tile-library"><div className="tile-library-heading"><strong>Available tiles</strong><button className="text-action" onClick={()=>setLibraryOpen(false)}>Close</button></div><div className="tile-library-grid">{definitions.filter(d=>!draft.some(t=>t.id===d.id)).map(d=><button className="library-item" key={d.id} onClick={()=>add(d.id)}><strong><Plus size={14}/>{d.title}</strong><span>{d.description}</span></button>)}</div></div>}
      <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const el=(e.target as HTMLElement).closest("[data-tile-id]");const to=el?.getAttribute("data-tile-id") as TileId|null;if(dragging&&to)move(dragging,to);setDragging(null);}}>
        {shown.map(tile=><div key={tile.id} data-tile-id={tile.id} draggable={editing&&!tile.pinned} onDragStart={()=>setDragging(tile.id)} onDragEnd={()=>setDragging(null)} className={`tile-drag-wrapper tile-slot-${tile.size} ${tile.id==="hardware"?"tile-slot-hardware":""}`}>
          <article className="dashboard-tile"><div className="tile-heading"><div><span className="tile-icon">{tile.id==="speed"?<Gauge/>:tile.id==="gear"?<Zap/>:tile.id==="rpm"?<Activity/>:tile.id==="pedals"?<Waves/>:tile.id==="laps"?<Flag/>:tile.id==="lap_history"?<Clock3/>:tile.id==="weather"?<CloudSun/>:tile.id==="map"?<Map/>:tile.id==="session"?<Radio/>:tile.id==="brakes"?<Thermometer/>:tile.id==="tyres"?<CircleGauge/>:tile.id==="fuel"?<Fuel/>:tile.id==="warnings"?<TriangleAlert/>:tile.id==="delta"?<ChartNoAxesColumnIncreasing/>:tile.id==="sectors"?<Timer/>:tile.id==="position"?<Medal/>:tile.id==="electronics"?<SlidersHorizontal/>:tile.id==="pit_stint"?<Timer/>:tile.id==="damage"?<Wrench/>:tile.id==="pressure_targets"?<Target/>:tile.id==="race_control"?<Siren/>:tile.id==="car_status"?<Lightbulb/>:<Cable/>}</span><h3>{fmt(tile.id)}</h3></div>{editing&&<span className="drag-grip"><GripVertical size={17}/></span>}</div><div className="tile-body"><TileContent id={tile.id} glow={glow} telemetry={telemetry}/></div></article>
          {editing&&<div className="tile-size-control"><label>Size <select value={tile.size} onChange={e=>update(tile.id,{size:e.target.value as TileSize})}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></label><button className="text-action" onClick={()=>update(tile.id,{pinned:!tile.pinned})}>{tile.pinned?<PinOff size={13}/>:<Pin size={13}/>} {tile.pinned?"Unpin":"Pin"}</button><button className="remove-tile" onClick={()=>remove(tile.id)} aria-label={`Remove ${fmt(tile.id)} tile`}><X size={14}/></button></div>}
        </div>)}
      </div></section> : <section className="workspace"><div className="page-placeholder"><div className="placeholder-mark">RE</div><h2>{active}</h2><p>This workspace will be added in a later implementation stage.</p><span className="pending-label">NOT INTEGRATED</span></div></section>}
      <footer className="demo-footnote"><span><Droplets size={13}/> {connected?"LIVE ACC PHYSICS":"ACC TELEMETRY"}</span><span>{connected?`${telemetry.physics?.processed_count??0} decoded samples · ${telemetry.physics?.decode_error_count??0} decode errors`:"Waiting for ACC Shared Memory. Graphics and Static fields are not connected yet."}</span></footer>
    </main>
  </div>;
}
export default App;
