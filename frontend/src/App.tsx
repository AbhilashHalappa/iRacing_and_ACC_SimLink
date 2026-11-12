import { useEffect, useMemo, useRef, useState } from "react";
import TrackMapTile from "./TrackMapTile";
import { penaltyTimeDisplay, sessionTimeDisplay } from "./timeDisplay";
import {
  Activity, Gauge, Flag, ChartNoAxesCombined, CloudSun, Map, Fuel,
  Thermometer, CircleGauge, Cable, Settings, Radio, ChevronDown,
  Plus, RotateCcw, Save, X, GripVertical, Pin, PinOff, Moon, Sun,
  LayoutDashboard, Waves, TriangleAlert, Clock3, Zap, Droplets,
  Timer, ChartNoAxesColumnIncreasing, Medal, SlidersHorizontal, Wrench, Target, Siren, Lightbulb,
} from "lucide-react";

type TileId = "driver_trace" | "speed" | "gear" | "rpm" | "pedals" | "laps" | "lap_history" | "weather" | "map" | "session" | "brakes" | "tyres" | "fuel" | "warnings" | "hardware" | "delta" | "sectors" | "position" | "electronics" | "pit_stint" | "damage" | "pressure_targets" | "race_control" | "car_status";
type TileSize = "small" | "medium" | "large";
type StreamName = "physics" | "graphics" | "static";
type StreamFreshness = { state: "fresh" | "stale" | "missing" | "unavailable"; age_ms: number | null; threshold_ms: number; lifecycle_state: string };
type Tile = { id: TileId; size: TileSize; pinned: boolean };
const definitions: { id: TileId; title: string; description: string }[] = [
  { id: "driver_trace", title: "Driver inputs", description: "Brake, throttle, gear, speed and RPM plotted over one lap" },
  { id: "speed", title: "Speed", description: "Live vehicle speed" },
  { id: "gear", title: "Gear", description: "Current selected gear" },
  { id: "rpm", title: "Engine RPM", description: "Engine speed and shift-light progress" },
  { id: "pedals", title: "Driver inputs", description: "Steering angle, throttle, brake and clutch" },
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
  { id: "driver_trace", size: "large", pinned: false },
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

function Meter({ label, value, tone = "purple" }: { label: string; value: number | null; tone?: string }) {
  const shown=value===null?"—":`${Math.round(value)}%`;
  return <div className="meter-row"><div className="meter-label"><span>{label}</span><b>{shown}</b></div><div className="meter-track"><i className={tone} style={{ width: (value??0) + "%" }} /></div></div>;
}
type GlowConfig = { tyre:[number,number,number,number]; brake:[number,number,number,number]; damage:[number,number,number]; intensity:number; lapStatus:"valid"|"invalid"|"out" };
type TargetPressureConfig = { FL:string; FR:string; RL:string; RR:string };
const defaultTargetPressures:TargetPressureConfig={FL:"",FR:"",RL:"",RR:""};
function readTargetPressures():TargetPressureConfig { try { const v=JSON.parse(window.localStorage.getItem("acc-target-pressures")||"null"); return v?{...defaultTargetPressures,...v}:defaultTargetPressures; } catch { return defaultTargetPressures; } }
const defaultGlow:GlowConfig={tyre:[70,90,100,110],brake:[250,400,500,600],damage:[20,40,70],intensity:65,lapStatus:"valid"};
function readGlow():GlowConfig { try { const v=JSON.parse(window.localStorage.getItem("acc-glow-settings")||"null"); return v?{...defaultGlow,...v}:defaultGlow; } catch { return defaultGlow; } }
function band(value:number, thresholds:number[], prefix:string) { return prefix+"-"+(value<thresholds[0]?0:value<thresholds[1]?1:value<thresholds[2]?2:value<thresholds[3]?3:4); }
function onOff(value: unknown) { return typeof value === "boolean" ? (value ? "ON" : "OFF") : "—"; }
function statusTone(value:string, label?:string) {
  const v=value.trim().toLowerCase();
  if (label==="LIGHTS STAGE" && v==="endu") return "light-on";
  if (label==="WIPER LEVEL" && ["1","2","3"].includes(v)) return "light-on";
  if (label==="WIPER LEVEL" && v==="0") return "light-off";
  if (["on","true","enabled","active"].includes(v)) return "light-on";
  if (["off","false","disabled","inactive"].includes(v)) return "light-off";
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
function millisecondsDisplay(value: unknown, digits=3) { return typeof value === "number" && Number.isFinite(value) ? (value/1000).toFixed(digits)+" s" : "—"; }

function splitTimeDisplay(value: unknown) {
  if(typeof value!=="string") return "—:—.---";
  const match=value.trim().match(/^(\d{1,4}):(\d{2}):(\d{3})$/);
  if(match) return `${String(Number(match[1])).padStart(2,"0")}:${match[2]}.${match[3]}`;
  return lapTimeDisplay(value,null);
}
function sectorTimeMilliseconds(value: string): number | null {
  const match=value.trim().match(/^(\d{1,4}):(\d{2})\.(\d{3})$/);
  if(!match) return null;
  const minutes=Number(match[1]), seconds=Number(match[2]), millis=Number(match[3]);
  if(seconds>=60) return null;
  return minutes*60000+seconds*1000+millis;
}
function lapTimeDisplay(raw: unknown, milliseconds: unknown, allowZero=false) {
  if (typeof raw === "string") {
    const match = raw.trim().match(/^(\d{1,4}):(\d{2})\.(\d{3})$/);
    if (match && Number(match[1]) < 1440 && Number(match[2]) < 60) return raw.trim();
  }
  if (typeof milliseconds !== "number" || !Number.isInteger(milliseconds) || milliseconds < (allowZero ? 0 : 1) || milliseconds >= 86400000) return "—:—.---";
  const minutes = Math.floor(milliseconds / 60000);
  const seconds = Math.floor((milliseconds % 60000) / 1000);
  const millis = milliseconds % 1000;
  return `${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}.${String(millis).padStart(3,"0")}`;
}
function stintTimeDisplay(value: unknown) {
  if(typeof value!=="number"||!Number.isFinite(value)||value<0) return "—";
  const totalSeconds=Math.floor(value/1000);
  const hours=Math.floor(totalSeconds/3600);
  const minutes=Math.floor((totalSeconds%3600)/60);
  const seconds=totalSeconds%60;
  return hours>0?`${hours}:${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}`:`${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}`;
}
function tyreSetDisplay(value: unknown) {
  // ACC Graphics tyre-set indices are zero-based; the MFD displays them from 1.
  return typeof value==="number"&&Number.isInteger(value)&&value>=0?`Set ${value+1}`:"—";
}
function engineMapDisplay(value: unknown) {
  // ACC Graphics engine-map index is zero-based; the in-car MFD is one-based.
  return typeof value==="number"&&Number.isInteger(value)&&value>=0?String(value+1):"—";
}
function tyreCompoundDisplay(value: unknown) {
  if(typeof value!=="string"||!value.trim()) return "—";
  return value.trim().replace(/_compound$/i,"").replace(/_/g," ").replace(/\b\w/g,char=>char.toUpperCase());
}
function graphicsStatus(value: unknown) { return ({0:"OFF",1:"REPLAY",2:"LIVE",3:"PAUSED"} as Record<number,string>)[Number(value)]??"—"; }
function graphicsSession(value: unknown) { return ({0:"PRACTICE",1:"QUALIFY",2:"RACE",3:"HOTLAP",4:"TIME ATTACK",5:"DRIFT",6:"DRAG",7:"HOTSTINT",8:"HOTSTINT SUPERPOLE"} as Record<number,string>)[Number(value)]??"—"; }
function rawEnum(value: unknown) { return typeof value==="number"&&Number.isFinite(value)?String(value):"—"; }
function lightsStageDisplay(value: unknown) { return value===0?"OFF":value===1?"ON":value===2?"ENDU":typeof value==="number"&&Number.isFinite(value)?`UNKNOWN (${value})`:"—"; }
function graphicsTrackGrip(value: unknown) { return ({0:"Green",1:"Fast",2:"Optimum",3:"Greasy",4:"Damp",5:"Wet",6:"Flooded"} as Record<number,string>)[Number(value)]??"—"; }
function graphicsFlag(value: unknown) { return ({0:"No Flag",1:"Blue Flag",2:"Yellow Flag",3:"Black Flag",4:"White Flag",5:"Chequered Flag",6:"Penalty Flag",7:"Green Flag",8:"Orange Flag"} as Record<number,string>)[Number(value)]??"Unknown"; }
function graphicsPenalty(value: unknown) { return ({0:"No Penalty",1:"Drive-Through · Track Limits",2:"10s Stop & Go · Track Limits",3:"20s Stop & Go · Track Limits",4:"30s Stop & Go · Track Limits",5:"Disqualified · Track Limits",6:"Lap Time Deleted · Track Limits",7:"Drive-Through · Pit Speeding",8:"10s Stop & Go · Pit Speeding",9:"20s Stop & Go · Pit Speeding",10:"30s Stop & Go · Pit Speeding",11:"Disqualified · Pit Speeding",12:"Lap Time Deleted · Pit Speeding",13:"Disqualified · Mandatory Pit Ignored",14:"Post-Race Time Penalty",15:"Disqualified · Unsportsmanlike Conduct",16:"Disqualified · Pit Entry",17:"Disqualified · Pit Exit",18:"Disqualified · Wrong Way",19:"Drive-Through · Driver Stint Limit",20:"Disqualified · Driver Stint Limit",21:"Disqualified · Driver Stint Limit Exceeded"} as Record<number,string>)[Number(value)]??"Unknown"; }
function graphicsRainIcon(value: unknown) { return ({0:"☀️",1:"🌦️",2:"🌧️",3:"🌧️",4:"🌧️",5:"⛈️"} as Record<number,string>)[Number(value)]??"—"; }
function graphicsWindDirection(value: unknown) {
  if(typeof value!=="number"||!Number.isFinite(value)) return "—";
  const degrees=((value*180/Math.PI)%360+360)%360;
  const compass=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  return `${compass[Math.round(degrees/22.5)%16]} (${degrees.toFixed(1)}°)`;
}
function globalFlagSummary(g:any) { if(!g)return "—"; const flags=[g.global_red&&"RED",g.global_yellow&&"YELLOW",g.global_white&&"WHITE",g.global_green&&"GREEN",g.global_chequered&&"CHEQUERED"]; return flags.filter(Boolean).join(" · ")||"NONE"; }
function correctedBrakeBiasPercent(data: any, carModel: unknown): number | null {
  const raw = data?.brake_bias;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  const model = typeof carModel === "string" ? carModel.trim().toLowerCase() : "";
  // ACC Static car IDs can include a namespace/prefix; match the Porsche 992
  // family rather than requiring one exact serialized identifier.
  const isPorsche992 = model.includes("porsche") && model.includes("992");
  return raw * 100 + (isPorsche992 ? -21.0 : 0);
}
type LapHistoryEntry = { lap:number; timeMs:number; valid:boolean|null; s1Ms:number|null; s2Ms:number|null; s3Ms:number|null };
const LAP_HISTORY_LIMIT = 10;
function readLapHistory(key:string):LapHistoryEntry[] {
  try {
    const raw=JSON.parse(window.localStorage.getItem(key)||"[]");
    if(!Array.isArray(raw)) return [];
    return raw.filter((lap:any)=>lap&&Number.isInteger(lap.lap)&&Number.isInteger(lap.timeMs)&&lap.timeMs>0)
      .slice(-LAP_HISTORY_LIMIT);
  } catch { return []; }
}
function lapDeltaDisplay(delta:number|null):string {
  if(delta===null||!Number.isFinite(delta)) return "—";
  const sign=delta>0?"+":delta<0?"−":"";
  const absolute=Math.abs(Math.round(delta));
  return sign+lapTimeDisplay(null,absolute,true);
}

type DriverTracePoint = { t:number; distance:number; brake:number|null; throttle:number|null; gear:number|null; speed:number|null; rpm:number|null };
const traceSeries = [
  {key:"brake",label:"Brake",color:"#ef6262",unit:"%"},
  {key:"throttle",label:"Throttle",color:"#54d889",unit:"%"},
  {key:"gear",label:"Gear",color:"#f59e0b",unit:""},
  {key:"speed",label:"Speed",color:"#4aa8ff",unit:" km/h"},
  {key:"rpm",label:"RPM",color:"#b78aff",unit:" rpm"},
] as const;
function DriverTraceTile({points}:{points:DriverTracePoint[]}) {
  const [enabled,setEnabled]=useState<Record<string,boolean>>(()=>{
    try { const saved=JSON.parse(window.localStorage.getItem("acc-driver-trace-series")||"null"); return saved?{brake:true,throttle:true,gear:true,speed:true,rpm:true,...saved}:{brake:true,throttle:true,gear:true,speed:true,rpm:true}; }
    catch { return {brake:true,throttle:true,gear:true,speed:true,rpm:true}; }
  });
  const toggle=(key:string)=>setEnabled(prev=>{const next={...prev,[key]:!prev[key]};try{window.localStorage.setItem("acc-driver-trace-series",JSON.stringify(next));}catch{}return next;});
  const active=traceSeries.filter(s=>enabled[s.key]&&points.some(p=>typeof p[s.key]==="number"));
  const latest=points.length?points[points.length-1].t:Date.now()/1000;
  const windowStart=latest-15;
  const latestDistance=points.length?points[points.length-1].distance:0;
  const firstDistance=points.length?points[0].distance:0;
  const distanceSpan=Math.max(1,latestDistance-firstDistance);
  const pathFor=(key:typeof traceSeries[number]["key"])=>{
    const valid=points.filter(p=>typeof p[key]==="number");
    if(valid.length<2)return "";
    const vals=valid.map(p=>p[key] as number),lo=Math.min(...vals),hi=Math.max(...vals),range=hi-lo||1;
    return valid.map((p,i)=>`${i===0?"M":"L"} ${((Math.max(0,Math.min(1,(p.distance-firstDistance)/distanceSpan))*960)+20).toFixed(1)} ${(238-((p[key] as number)-lo)/range*208).toFixed(1)}`).join(" ");
  };
  return <div className="driver-trace">
    <div className="trace-controls">{traceSeries.map(s=><button key={s.key} type="button" className={enabled[s.key]?"trace-toggle active":"trace-toggle"} aria-pressed={!!enabled[s.key]} onClick={()=>toggle(s.key)}><i style={{background:s.color}}/>{s.label}</button>)}</div>
    <div className="trace-chart-wrap"><svg className="trace-chart" viewBox="0 0 1000 280" role="img" aria-label="Brake, throttle, gear, speed and RPM traces over the latest 15 seconds">
      {[30,82,134,186,238].map(y=><line key={y} x1="20" x2="980" y1={y} y2={y} className="trace-gridline"/>)}
      {[0,1/3,2/3,1].map(x=><g key={x}><line x1={20+x*960} x2={20+x*960} y1="24" y2="238" className="trace-gridline"/><text x={20+x*960} y="260" textAnchor="middle">{x===1?"NOW":`${Math.round((x-1)*distanceSpan)} m`}</text></g>)}
      {active.map(s=><path key={s.key} d={pathFor(s.key)} fill="none" stroke={s.color} strokeWidth="2.8" strokeLinejoin="round" strokeLinecap="round"><title>{s.label} trace</title></path>)}
    </svg></div>
    <div className="trace-legend">{active.map(s=>{const last=[...points].reverse().find(p=>typeof p[s.key]==="number");return <span key={s.key}><i style={{background:s.color}}/>{s.label}: <b>{last?(last[s.key] as number).toFixed(s.key==="gear"?0:s.key==="rpm"?0:1)+s.unit:"—"}</b></span>;})}</div>
    <small className="trace-footnote">{points.length<2?"Waiting for live ACC telemetry. The graph fills as samples arrive.":"Distance-based view · latest 15 seconds retained to keep the graph readable; horizontal axis shows metres travelled in the current lap."}</small>
  </div>;
}

function TileContentBody({ id, glow, telemetry, targetPressures, trace }: { id: TileId; glow:GlowConfig; telemetry:any; targetPressures:TargetPressureConfig; trace:DriverTracePoint[] }) {
  const data=telemetry?.physics?.data ?? null;
  const graphics=telemetry?.graphics?.data ?? null;
  const wheels=data?.wheels ?? {};
  const corners=["FL","FR","RL","RR"];
  const carModel=telemetry?.vehicle?.car_model;
  const brakeBiasPercent=correctedBrakeBiasPercent(data,carModel);
  const fuelKg=typeof data?.fuel_kg==="number"&&Number.isFinite(data.fuel_kg)?Math.max(0,data.fuel_kg):null;
  const fuelMaxSeen=useRef(0);
  if(fuelKg!==null) fuelMaxSeen.current=Math.max(fuelMaxSeen.current,fuelKg);
  const fuelFill=fuelKg!==null&&fuelMaxSeen.current>0?Math.max(0,Math.min(100,fuelKg/fuelMaxSeen.current*100)):0;
  const sectorHistory=useRef<{lap:number|null;sector:number|null;times:Record<number,string>;liveTime:string}>({lap:null,sector:null,times:{},liveTime:"—:—.---"});
  const [,setSectorHistoryRevision]=useState(0);
  useEffect(()=>{
    const sector=typeof graphics?.sector==="number"&&graphics.sector>=0&&graphics.sector<=2?graphics.sector:null;
    const completedLaps=typeof graphics?.completed_laps==="number"?graphics.completed_laps:null;
    if(sector===null) return;
    const liveTime=splitTimeDisplay(graphics?.split_time_str);
    const hasLiveTime=liveTime!=="—:—.---";
    const history=sectorHistory.current;
    if(history.lap===null){
      history.lap=completedLaps;
      history.sector=sector;
      history.times={};
      history.liveTime=hasLiveTime?liveTime:"—:—.---";
      return;
    }
    const newLap=(completedLaps!==null&&history.lap!==null&&completedLaps!==history.lap)||(history.sector===2&&sector===0);
    if(newLap){
      history.lap=completedLaps;
      history.sector=sector;
      history.times={};
      history.liveTime=hasLiveTime?liveTime:"—:—.---";
      setSectorHistoryRevision(value=>value+1);
      return;
    }
    if(history.sector!==sector){
      if(history.sector!==null&&history.liveTime!=="—:—.---") history.times[history.sector]=history.liveTime;
      history.sector=sector;
      if(hasLiveTime) history.liveTime=liveTime;
      setSectorHistoryRevision(value=>value+1);
      return;
    }
    if(hasLiveTime) history.liveTime=liveTime;
  },[graphics?.sector,graphics?.completed_laps,graphics?.split_time_str]);
  // Separate display-only best-sector calculation. The existing live-sector
  // tracker above remains unchanged and continues to own current-lap timings.
  const bestSectorTimes=useMemo(()=>{
    const best:(number|null)[]=[null,null,null];
    const completed=Array.isArray(telemetry?.lap_history)?telemetry.lap_history:[];
    for(const lap of completed){
      if(lap?.valid!==true) continue;
      const values=[lap.s1Ms,lap.s2Ms,lap.s3Ms];
      values.forEach((value,index)=>{
        if(typeof value==="number"&&Number.isInteger(value)&&value>0&&(best[index]===null||value<best[index]!)) best[index]=value;
      });
    }
    return best;
  },[telemetry?.lap_history]);
  switch (id) {
    case "driver_trace": return <DriverTraceTile points={trace}/>;
    case "speed": return <div className="hero-value glance-hero"><strong>{display(data?.speed_kph,0)}</strong><span>KM/H</span><small>VEHICLE SPEED · ACC PHYSICS</small></div>;
    case "gear": return <div className="hero-value gear-value glance-hero"><strong>{data?.gear_display ?? "—"}</strong><span>GEAR</span><small>ACC PHYSICS</small></div>;
    case "rpm": { const rpm=Number(data?.rpm??0); const max=Number(data?.current_max_rpm??9000); const ratio=max>0?Math.max(0,Math.min(1,rpm/max)):0; const shift=ratio>=0.95; const lit=shift?15:Math.max(0,Math.min(15,Math.round(ratio*15))); return <div className={"rpm-content glance-rpm"+(shift?" rpm-shift-active":"")}><div className="rpm-number">{display(data?.rpm,0)} <small>RPM</small></div><div className="rpm-leds">{Array.from({ length: 15 }, (_, i) => { const zone=i<5?"green":i<9?"yellow":i<12?"orange":"red"; return <i key={i} className={i<lit?("active zone-"+zone+(shift?" shift-flash":"")):""}/>; })}</div><div className="rpm-scale"><span>0</span><span>{display(max/4,0)}</span><span>{display(max/2,0)}</span><span>{display(max,0)}</span></div><small className="glance-hint">ACC PHYSICS · MAX {display(max,0)} RPM{shift?" · SHIFT":""}</small></div>; }
    case "pedals": { const steeringDeg=typeof data?.steering_angle==="number"?data.steering_angle*180/Math.PI:null; const steeringWidth=steeringDeg===null?0:Math.min(50,Math.abs(steeringDeg)/180*50); return <div className="stacked-meters glance-pedals"><div className="driver-steering-angle"><div className="steering-angle-heading"><span>STEERING ANGLE</span><b>{display(steeringDeg,1,"°")}</b></div><div className="steering-angle-track"><i className="steering-angle-center"/>{steeringDeg!==null&&<i className={`steering-angle-fill ${steeringDeg<0?"left":"right"}`} style={{width:`${steeringWidth}%`}}/>}</div><div className="steering-angle-scale"><span>LEFT</span><span>CENTER</span><span>RIGHT</span></div></div><Meter label="THROTTLE" value={data?Math.max(0,Math.min(100,Number(data.throttle)*100)):null}/><Meter label="BRAKE" value={data?Math.max(0,Math.min(100,Number(data.brake)*100)):null} tone="red"/><Meter label="CLUTCH" value={data?Math.max(0,Math.min(100,Number(data.clutch)*100)):null} tone="teal"/></div>; }
    case "laps": { const validity=graphics?.is_valid_lap===true?"VALID":graphics?.is_valid_lap===false?"INVALID":"—"; return <div className={`lap-metrics glance-laps lap-glow lap-${telemetry?.graphics?.lap_status??(validity==="VALID"?"valid":validity==="INVALID"?"invalid":"unknown")}`} style={{"--glow-intensity":glow.intensity/100,"--glow-blur":`${5+12*glow.intensity/100}px`} as React.CSSProperties}><div className="lap-primary"><span>CURRENT</span><b>{lapTimeDisplay(graphics?.current_time_str,graphics?.current_time_ms,true)}</b><small>{["out","out_lap","out-lap"].includes(String(telemetry?.graphics?.lap_status??graphics?.lap_status??"").toLowerCase())?"OUT LAP":`LAP ${typeof graphics?.completed_laps==="number"?graphics.completed_laps+1:"—"} · ${validity}`}</small></div><div><span>LAST</span><b>{lapTimeDisplay(graphics?.last_time_str,graphics?.last_time_ms)}</b></div><div><span>BEST</span><b>{lapTimeDisplay(graphics?.best_time_str,graphics?.best_time_ms)}</b></div></div>; }
    case "lap_history": { const best=typeof graphics?.best_time_ms==="number"&&graphics.best_time_ms>0?graphics.best_time_ms:null; const history=(telemetry?.lap_history??[]) as LapHistoryEntry[]; return <div className="history-table"><div className="history-head"><span>RECORD</span><span>TIME</span><span>DELTA</span><span>S1</span><span>S2</span><span>S3</span></div>{history.length===0?<div className="history-empty">No completed timed laps recorded in this session yet.<br/>LAST · {lapTimeDisplay(graphics?.last_time_str,graphics?.last_time_ms)} · BEST · {lapTimeDisplay(graphics?.best_time_str,graphics?.best_time_ms)}</div>:<div className="history-rows">{[...history].reverse().map((lap)=> <div className="history-row" key={lap.lap}><span> LAP {lap.lap} · {lap.valid===true?"VALID":lap.valid===false?"INVALID":"REVIEW"}</span><b>{lapTimeDisplay(null,lap.timeMs)}</b><span>{lapDeltaDisplay(best===null?null:lap.timeMs-best)}</span><span>{lapTimeDisplay(null,lap.s1Ms)}</span><span>{lapTimeDisplay(null,lap.s2Ms)}</span><span>{lapTimeDisplay(null,lap.s3Ms)}</span></div>)}</div>}</div>; }
    case "weather": return <div className="field-grid balanced-grid glance-weather">{[["ROAD TEMP",display(data?.road_temp_c,1," °C")],["AIR TEMP",display(data?.air_temp_c,1," °C")],["TRACK GRIP",graphicsTrackGrip(graphics?.track_grip_status)],["NOW / +10 / +30",[graphics?.rain_intensity,graphics?.rain_10min,graphics?.rain_30min].map(graphicsRainIcon).join(" / ")],["WIND SPEED",display(graphics?.wind_speed,2," km/h")],["WIND DIRECTION",graphicsWindDirection(graphics?.wind_direction)]].map(([a,b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "map": return <TrackMapTile track={telemetry?.vehicle?.track} configuration={telemetry?.vehicle?.track_configuration} graphics={graphics} lapStatus={telemetry?.graphics?.lap_status ?? graphics?.lap_status}/>;
    case "session": { const position=typeof graphics?.position==="number"&&graphics.position>0?graphics.position:null; const activeCars=typeof graphics?.active_cars==="number"&&graphics.active_cars>0?graphics.active_cars:null; const positionDisplay=position!==null&&activeCars!==null?`${position} / ${activeCars}`:"—"; return <div className="balanced-grid">{[["TRACK",telemetry?.vehicle?.track??"—"],["SESSION TYPE",graphicsSession(graphics?.session)],["SESSION STATUS",graphicsStatus(graphics?.status)],["TIME LEFT",sessionTimeDisplay(graphics?.session_time_left_s)],["LAP COUNT",typeof graphics?.completed_laps==="number"?String(graphics.completed_laps):"—"],["POSITION",positionDisplay],["TYRE COMPOUND",tyreCompoundDisplay(graphics?.tyre_compound)]].map(([a,b]) => <div className="balanced-field" key={a}><span>{a}</span><b>{b}</b></div>)}</div>; }
    case "brakes": return <div className="corner-grid extended-corners glance-corners glow-corners" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const w=wheels[c]??{};const t=w.brake_temp_c;return <div key={c} className={typeof t==="number"?band(t,glow.brake,"glow"):""}><span>{c}</span><b>{display(t,0,"°C")}</b><small>DISC TEMP · ACC</small><small>Pressure {display(w.brake_pressure,1)}</small><small>Pad {display(w.pad_life,1)} · Disc {display(w.disc_life,1)}</small></div>})}</div>;
    case "tyres": return <div className="corner-grid extended-corners glance-corners glance-tyres glow-corners" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const w=wheels[c]??{};const t=w.tyre_core_temp_c;return <div key={c} className={typeof t==="number"?band(t,glow.tyre,"glow"):""}><span>{c}</span><b>{display(t,0,"°C")}</b><small>CORE TEMP · ACC</small><small>Pressure {display(w.tyre_pressure_psi,1," psi")}</small><small>Slip {display(w.slip_ratio,2)} · Angle {display(w.slip_angle,1,"°")}</small></div>})}</div>;
    case "fuel": return <div className="fuel-content glance-fuel"><div className="fuel-main"><b>{display(fuelKg,1)} <small>KG</small></b><span>REMAINING · ACC PHYSICS</span></div><div className="fuel-track fuel-gradient-track"><i style={{width:fuelFill+"%"}}/></div><div className="fuel-bar-caption"><span>LOW</span><span>SESSION HIGH OBSERVED</span></div><div className="glance-inline-stats"><div><span>EST. LAPS LEFT</span><b>{display(graphics?.fuel_estimated_laps,1," laps")}</b></div><div><span>FUEL / LAP</span><b>{display(graphics?.fuel_per_lap_l,2," L/lap")}</b></div></div><small className="glance-footnote">Fuel remaining is ACC Physics. Fuel per lap and estimated laps are read directly from ACC Graphics; the bar remains relative to the highest fuel level observed since app start.</small></div>;
    case "warnings": return <div className="balanced-grid">{[["LAP VALIDITY",graphics?.is_valid_lap===true?"VALID":graphics?.is_valid_lap===false?"INVALID":"—"],["PENALTY",graphicsPenalty(graphics?.penalty)],["PENALTY TIME",penaltyTimeDisplay(graphics?.penalty_time_s)],["MISSING MANDATORY PITS",rawEnum(graphics?.missing_mandatory_pits)],["MANDATORY PIT DONE",onOff(graphics?.mandatory_pit_done)]].map(([a,b]) => <div className="balanced-field" key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
    case "hardware": return <div className="hardware-list balanced-hardware">{["Wheel USB link","Wheel device","Pedals device","Handbrake device","RPM LED Controller"].map((d) => <div key={d}><span>{d}</span><b><i />Not reported</b></div>)}</div>;
    case "delta": { const deltaTone=graphics?.delta_positive===false?"delta-negative":graphics?.delta_positive===true?"delta-positive":""; return <div className="glance-delta"><div className={`glance-delta-primary ${deltaTone}`}><span>LIVE DELTA · ACC</span><strong>{graphics?.delta_lap_time_str||"—.---"}</strong><small>{graphics?.delta_positive===true?"POSITIVE":graphics?.delta_positive===false?"NEGATIVE":"SIGN UNKNOWN"}</small></div><div className="glance-inline-stats"><div><span>EST. LAP</span><b>{lapTimeDisplay(graphics?.estimated_lap_time_str,graphics?.estimated_lap_time_ms)}</b></div><div><span>BEST LAP</span><b>{lapTimeDisplay(graphics?.best_time_str,graphics?.best_time_ms)}</b></div></div><small className="glance-footnote">ACC Graphics delta and estimated lap fields; delta sign is shown as reported.</small></div>; }
    case "sectors": { const sectorIndex=typeof graphics?.sector==="number"&&graphics.sector>=0&&graphics.sector<=2?graphics.sector:null; const liveSplit=splitTimeDisplay(graphics?.split_time_str); const history=sectorHistory.current.times; const previousSector=sectorIndex!==null&&sectorIndex>0?history[sectorIndex-1]:null; return <div className="glance-sector"><div className="glance-inline-stats"><div><span>LIVE SECTOR TIME</span><b>{liveSplit}</b></div><div><span>LAST COMPLETED SECTOR</span><b>{previousSector??"—:—.---"}</b></div><div><span>CURRENT SECTOR</span><b>{sectorIndex!==null?sectorIndex+1:"—"} / 3</b></div></div><div className="sector-strip">{["S1","S2","S3"].map((s,i)=>{const isLive=i===sectorIndex;const recorded=history[i];return <div key={s}><span>{s}</span><b>{isLive?liveSplit:recorded??"—:—.---"}</b><small>{isLive?"LIVE":recorded?"COMPLETED":"NOT RECORDED"}</small></div>;})}</div><div className="best-sector-strip">{["S1","S2","S3"].map((s,i)=>{const current=sectorTimeMilliseconds(i===sectorIndex?liveSplit:history[i]??"");const best=bestSectorTimes[i];const delta=current!==null&&best!==null?current-best:null;return <div key={s}><span>{s} BEST</span><b>{best===null?"—:—.---":lapTimeDisplay(null,best)}</b><small className={delta===null?"sector-delta-unavailable":delta>0?"sector-delta-slower":delta<0?"sector-delta-faster":"sector-delta-even"}>DELTA {lapDeltaDisplay(delta)}</small></div>;})}</div><small className="glance-footnote">Best sectors are calculated separately from completed valid laps. Delta compares the current lap's available sector time with that sector best; the existing live-sector timing tracker is unchanged.</small></div>; }
    case "position": return <div className="glance-position"><div className="glance-position-hero"><strong>{rawEnum(graphics?.position)}</strong><span>POSITION</span><small>OF {rawEnum(graphics?.active_cars)} ACTIVE CARS</small></div><div className="glance-inline-stats"><div><span>GAP AHEAD</span><b>{millisecondsDisplay(graphics?.gap_ahead_ms)}</b></div><div><span>GAP BEHIND</span><b>{millisecondsDisplay(graphics?.gap_behind_ms)}</b></div></div><small className="glance-footnote">Gap values are converted from milliseconds to seconds; the ACC-provided sign is preserved.</small></div>;
    case "electronics": return <div className="glance-electronics"><div className="electronics-primary"><ChangeGlowBox primary label="TC LEVEL" value={display(graphics?.tc_level,0)}/><ChangeGlowBox primary label="ABS LEVEL" value={display(graphics?.abs_level,0)}/><ChangeGlowBox primary label="BRAKE BIAS" value={display(brakeBiasPercent,1,"%")}/></div><div className="balanced-grid electronics-secondary"><ChangeGlowBox label="TC CUT" value={rawEnum(graphics?.tc_cut)}/><ChangeGlowBox label="ENGINE MAP" value={engineMapDisplay(graphics?.engine_map)}/><ChangeGlowBox label="AUTO SHIFTER" value={onOff(data?.autoshifter_on)}/><ChangeGlowBox label="TURBO BOOST" value={display(data?.turbo_boost,2)}/></div><small className="glance-footnote">TC/ABS setup levels are sourced from ACC Graphics. Brake bias remains under investigation in issue #13.</small></div>;
    case "pit_stint": { const mfdTyreSet=graphics?.mfd_tyre_set; const currentTyreSet=graphics?.current_tyre_set; const tyreChange=typeof mfdTyreSet==="number"&&Number.isInteger(mfdTyreSet)&&mfdTyreSet>=0&&typeof currentTyreSet==="number"&&Number.isInteger(currentTyreSet)&&currentTyreSet>=0?mfdTyreSet!==currentTyreSet:null; return <div className="glance-pit"><div className="electronics-primary three-up"><div><span>PIT BOX</span><b>{onOff(graphics?.is_in_pit)}</b></div><div><span>PIT LANE</span><b>{onOff(graphics?.is_in_pit_lane)}</b></div><div><span>MANDATORY STOP</span><b>{onOff(graphics?.mandatory_pit_done)}</b></div></div><div className="balanced-grid pit-secondary"><div className="balanced-field"><span>STINT TOTAL TIME LEFT</span><b>{stintTimeDisplay(graphics?.driver_stint_total_ms)}</b></div><div className="balanced-field"><span>STINT TIME LEFT</span><b>{stintTimeDisplay(graphics?.driver_stint_left_ms)}</b></div><div className="balanced-field"><span>FUEL USED</span><b>{display(graphics?.used_fuel_l,1," L")}</b></div><div className="balanced-field"><span>MFD FUEL TO ADD</span><b>{display(graphics?.mfd_fuel_to_add,1," L")}</b></div><div className="balanced-field"><span>MFD TYRE SET</span><b>{tyreSetDisplay(mfdTyreSet)}</b></div><div className="balanced-field"><span>CURRENT / STRATEGY SET</span><b>{tyreSetDisplay(currentTyreSet)} / {tyreSetDisplay(graphics?.strategy_tyre_set)}</b></div><div className="balanced-field"><span>TYRE CHANGE</span><b>{tyreChange===null?"—":tyreChange?"YES":"NO"}</b></div>{tyreChange===true&&<><div className="balanced-field"><span>TYRE COMPOUND</span><b>{tyreCompoundDisplay(graphics?.tyre_compound)}</b></div>{["FL","FR","RL","RR"].map((corner,i)=><div className="balanced-field" key={corner}><span>MFD {corner} PRESSURE REQUEST</span><b>{display(graphics?.mfd_tyre_pressures?.[i],1," psi")}</b></div>)}</>}</div><small className="glance-footnote">Stint times are shown as mm:ss (or h:mm:ss); unavailable ACC sentinel values are hidden. Tyre change is inferred when the selected MFD tyre set differs from the current set. MFD pressures are requested PSI values; fuel quantities are in litres.</small></div>; }
    case "damage": { const carDamageLabels=["FRONT","REAR","LEFT","RIGHT","CENTRE"]; return <div className="damage-layout"><div className="damage-summary balanced-grid">{carDamageLabels.map((label,index)=><div className="balanced-field" key={label}><span>CAR DAMAGE · {label}</span><b>{display(data?.car_damage?.[index],2)}</b></div>)}</div><section className="damage-corner-group"><h4>SUSPENSION DAMAGE · ACC</h4><div className="corner-grid glance-corners glow-corners damage-glows" style={{"--glow-intensity":glow.intensity/100} as React.CSSProperties}>{corners.map(c=>{const v=wheels[c]?.suspension_damage;const pct=typeof v==="number"?Math.max(0,Math.min(100,v*100)):null;return <div key={c} className={pct===null?"":`damage-${pct<glow.damage[0]?0:pct<glow.damage[1]?1:pct<glow.damage[2]?2:3}`}><span>{c}</span><b>{display(pct,1,"%")}</b><small>SUSPENSION · ACC</small></div>})}</div></section></div>; }
    case "pressure_targets": return <div className="pressure-target-layout"><div className="corner-grid glance-corners pressure-target-grid">{corners.map((v)=>{const actual=wheels[v]?.tyre_pressure_psi;const configured=targetPressures[v as keyof TargetPressureConfig];const target=configured.trim()===""?null:Number(configured);const delta=typeof actual==="number"&&Number.isFinite(actual)&&target!==null&&Number.isFinite(target)?actual-target:null;return <div key={v}><span>{v}</span><b>Actual {display(actual,1," psi")}</b><small>Configured target {target!==null&&Number.isFinite(target)?display(target,1," psi"):"—"}</small><small>{delta===null?"Difference —":`Difference ${delta>0?"+":""}${delta.toFixed(1)} psi`}</small></div>})}</div><p>Actual pressure is live ACC Physics data. Targets are manually configured in Settings → Vehicle &amp; Telemetry; no ACC MFD target is assumed.</p></div>;
    case "race_control": return <div className="balanced-grid race-control-grid">{[["FLAG",graphicsFlag(graphics?.flag)],["GLOBAL FLAGS",globalFlagSummary(graphics)],["TRACK STATUS",graphics?.track_status||"—"]].map(([a,b])=><div className={`balanced-field ${a.includes("FLAG")?"race-flag-field flag-"+flagTone(b):""}`} key={a}><span>{a}</span><b>{b}</b></div>)}<div className="balanced-field"><span>SECTOR YELLOW FLAGS</span><b>{[graphics?.global_yellow_1,graphics?.global_yellow_2,graphics?.global_yellow_3].map((v,i)=>v?String(i+1):null).filter(Boolean).join(", ")||"NONE"}</b></div><div className="balanced-field"><span>GLOBAL GREEN / CHEQUERED</span><b>{[graphics?.global_green&&"GREEN",graphics?.global_chequered&&"CHEQUERED",graphics?.global_red&&"RED"].filter(Boolean).join(" / ")||"—"}</b></div><div className="balanced-field message-field"><span>RACE CONTROL MESSAGE</span><b>Not exposed as a text field in this Graphics page</b></div></div>;
    case "car_status": return <div className="balanced-grid car-status-grid">{[["PIT LIMITER",onOff(data?.pit_limiter_on)],["ENGINE RUNNING",onOff(data?.engine_running)],["IGNITION",onOff(data?.ignition_on)],["STARTER",onOff(data?.starter_engine_on)],["AI CONTROL",onOff(data?.is_ai_controlled)],["WATER TEMP",display(data?.water_temp_c,0,"°C")],["RAIN LIGHT",onOff(graphics?.rain_lights)],["FLASHING LIGHTS",onOff(graphics?.flashing_lights)],["LIGHTS STAGE",lightsStageDisplay(graphics?.lights_stage)],["WIPER LEVEL",rawEnum(graphics?.wiper_level)],["LEFT INDICATOR",onOff(graphics?.direction_left)],["RIGHT INDICATOR",onOff(graphics?.direction_right)],["EXHAUST TEMP",display(graphics?.exhaust_temp_c,0,"°C")],["RAIN TYRES",onOff(graphics?.rain_tyres)]].map(([a,b])=><div className={`balanced-field light-status-field ${statusTone(b,a)}`} key={a}><span>{a}</span><b>{b}</b></div>)}</div>;
  }
}
const tileStreamDependencies: Record<TileId, StreamName[]> = {
  driver_trace: ["physics", "graphics"],
  speed: ["physics"], gear: ["physics"], rpm: ["physics"], pedals: ["physics"],
  laps: ["graphics"], lap_history: ["graphics"], weather: ["physics", "graphics"],
  map: ["graphics", "static"], session: ["graphics", "static"],
  brakes: ["physics"], tyres: ["physics"], fuel: ["physics", "graphics"],
  warnings: ["graphics"], hardware: [], delta: ["graphics"], sectors: ["graphics"],
  position: ["graphics"], electronics: ["physics", "graphics"], pit_stint: ["graphics"],
  damage: ["physics"], pressure_targets: ["physics"], race_control: ["graphics"],
  car_status: ["physics", "graphics"],
};

function TileContent({ id, glow, telemetry, targetPressures, trace, freshness }: {
  id: TileId;
  glow: GlowConfig;
  telemetry: any;
  targetPressures: TargetPressureConfig;
  trace: DriverTracePoint[];
  freshness: Partial<Record<StreamName, StreamFreshness>>;
}) {
  const blocked = (tileStreamDependencies[id] ?? []).filter((stream) => freshness[stream]?.state !== "fresh");
  const healthLabel = blocked.map((stream) => {
    const state = freshness[stream]?.state ?? "missing";
    return `${stream.toUpperCase()} ${state.toUpperCase()}`;
  }).join(" · ");
  return <div className={blocked.length ? "tile-content-health is-stale" : "tile-content-health"}>
    {blocked.length > 0 && <div className="tile-stale-banner" role="status">
      <strong>LAST-KNOWN VALUES · NOT LIVE</strong><span>{healthLabel}</span>
    </div>}
    <div className="tile-content-values">
      <TileContentBody id={id} glow={glow} telemetry={telemetry} targetPressures={targetPressures} trace={trace}/>
    </div>
  </div>;
}

function App() {
  const [telemetry,setTelemetry]=useState<any>(null);
  useEffect(()=>{const events=new EventSource("/events");events.onmessage=event=>{try{setTelemetry(JSON.parse(event.data));}catch{/* Ignore malformed bridge frames. */}};events.onerror=()=>setTelemetry((current:any)=>current?{...current,connected:false}:current);return ()=>events.close();},[]);
  const connected=Boolean(telemetry?.connected);
  const [driverTrace,setDriverTrace]=useState<DriverTracePoint[]>([]);
  const traceSession=useRef<string|null>(null);
  const lapDistanceOrigin=useRef<number|null>(null);
  const previousTraceDistance=useRef<number|null>(null);
  const previousTraceCompletedLaps=useRef<number|null>(null);
  const previousTraceNormalizedPosition=useRef<number|null>(null);
  const previousTraceSample=useRef<string>("");
  useEffect(()=>{
    const g=telemetry?.graphics?.data, p=telemetry?.physics?.data;
    if(!g||!p||typeof g.normalized_car_position!=="number"||!Number.isFinite(g.normalized_car_position)||g.normalized_car_position<0||g.normalized_car_position>1) return;
    const sessionKey=[telemetry?.vehicle?.track??"",telemetry?.vehicle?.track_configuration??"",g.session_index??"",g.session??""].join("|");
    const distance=typeof g.distance_traveled_m==="number"&&Number.isFinite(g.distance_traveled_m)?g.distance_traveled_m:null;
    if(distance===null)return;
    const completedLaps=typeof g.completed_laps==="number"&&Number.isFinite(g.completed_laps)?g.completed_laps:null;
    if(traceSession.current!==sessionKey){
      traceSession.current=sessionKey;
      lapDistanceOrigin.current=distance;
      previousTraceDistance.current=distance;
      previousTraceCompletedLaps.current=completedLaps;
      previousTraceNormalizedPosition.current=g.normalized_car_position;
      previousTraceSample.current="";
      setDriverTrace([]);
    }
    const previousDistance=previousTraceDistance.current;
    const previousCompletedLaps=previousTraceCompletedLaps.current;
    const previousNormalized=previousTraceNormalizedPosition.current;
    const completedLapChanged=completedLaps!==null&&previousCompletedLaps!==null&&completedLaps>previousCompletedLaps;
    const normalizedPositionWrapped=previousNormalized!==null&&previousNormalized>0.9&&g.normalized_car_position<0.1;
    const distanceCounterReset=previousDistance!==null&&distance<previousDistance-100;
    if(completedLapChanged||normalizedPositionWrapped||distanceCounterReset){
      lapDistanceOrigin.current=distance;
      previousTraceSample.current="";
      setDriverTrace([]);
    }
    const distanceOrigin=lapDistanceOrigin.current??distance;
    lapDistanceOrigin.current=distanceOrigin;
    const lapDistance=Math.max(0,distance-distanceOrigin);
    const point:DriverTracePoint={t:Date.now()/1000,distance:lapDistance,brake:typeof p.brake==="number"?Math.max(0,Math.min(100,p.brake*100)):null,throttle:typeof p.throttle==="number"?Math.max(0,Math.min(100,p.throttle*100)):null,gear:typeof p.gear_raw==="number"?(p.gear_raw===0?-1:p.gear_raw-1):null,speed:typeof p.speed_kph==="number"?p.speed_kph:null,rpm:typeof p.rpm==="number"?p.rpm:null};
    const signature=[point.distance,point.brake,point.throttle,point.gear,point.speed,point.rpm].join("|");
    if(signature!==previousTraceSample.current){
      previousTraceSample.current=signature;setDriverTrace(old=>[...old.filter(sample=>point.t-sample.t<=15),point].slice(-1800));
    }
    previousTraceDistance.current=distance;
    previousTraceCompletedLaps.current=completedLaps;
    previousTraceNormalizedPosition.current=g.normalized_car_position;
  },[telemetry]);
  const [lapHistory,setLapHistory]=useState<LapHistoryEntry[]>([]);
  const lapCapture=useRef<{sessionKey:string|null;completedLaps:number|null;sector:number|null;sector1BoundaryMs:number|null;sector2BoundaryMs:number|null;validity:boolean|null}>({sessionKey:null,completedLaps:null,sector:null,sector1BoundaryMs:null,sector2BoundaryMs:null,validity:null});
  useEffect(()=>{
    const graphics=telemetry?.graphics?.data;
    if(!graphics) return;
    const track=String(telemetry?.vehicle?.track??"unknown-track");
    const configuration=String(telemetry?.vehicle?.track_configuration??"");
    const sessionKey=[track,configuration,telemetry?.vehicle?.car_model??"unknown-car",graphics.session_index,graphics.session].join("|");
    const storageKey="acc-lap-history-v1:"+sessionKey;
    const completed=typeof graphics.completed_laps==="number"?graphics.completed_laps:null;
    const sector=typeof graphics.sector==="number"&&graphics.sector>=0&&graphics.sector<=2?graphics.sector:null;
    const tracker=lapCapture.current;
    if(tracker.sessionKey!==sessionKey){
      lapCapture.current={sessionKey,completedLaps:completed,sector,sector1BoundaryMs:null,sector2BoundaryMs:null,validity:typeof graphics.is_valid_lap==="boolean"?graphics.is_valid_lap:null};
      const savedHistory=readLapHistory(storageKey);
      // ACC can reuse track/car/session-type identity across separate sessions.
      // On app startup, a stored lap number ahead of ACC's current completed
      // lap counter proves this is a fresh session, not an app restart mid-session.
      const belongsToEarlierSession=completed!==null&&savedHistory.some(entry=>entry.lap>completed);
      if(belongsToEarlierSession){
        try{window.localStorage.removeItem(storageKey);}catch{}
        setLapHistory([]);
      } else {
        setLapHistory(savedHistory);
      }
      return;
    }
    if(completed!==null&&tracker.completedLaps!==null&&completed<tracker.completedLaps){
      lapCapture.current={sessionKey,completedLaps:completed,sector,sector1BoundaryMs:null,sector2BoundaryMs:null,validity:typeof graphics.is_valid_lap==="boolean"?graphics.is_valid_lap:null};
      try{window.localStorage.removeItem(storageKey);}catch{}
      setLapHistory([]);
      return;
    }
    const completingLap=completed!==null&&tracker.completedLaps!==null&&completed>tracker.completedLaps;
    // ACC exposes last_sector_time_ms as cumulative elapsed time at the
    // completed sector boundary, not as the duration of that sector.
    const lastSectorBoundaryMs=typeof graphics.last_sector_time_ms==="number"&&Number.isInteger(graphics.last_sector_time_ms)&&graphics.last_sector_time_ms>0?graphics.last_sector_time_ms:null;
    if(sector!==null&&tracker.sector!==null&&sector!==tracker.sector){
      if(tracker.sector===0&&sector===1) tracker.sector1BoundaryMs=lastSectorBoundaryMs;
      if(tracker.sector===1&&sector===2) tracker.sector2BoundaryMs=lastSectorBoundaryMs;
      tracker.sector=sector;
    } else if(tracker.sector===null) tracker.sector=sector;
    if(graphics.is_valid_lap===false) tracker.validity=false;
    else if(graphics.is_valid_lap===true&&tracker.validity===null&&!completingLap) tracker.validity=true;
    if(completingLap){
      const lapTime=typeof graphics.last_time_ms==="number"&&graphics.last_time_ms>0?graphics.last_time_ms:null;
      const outLap=["out","out_lap","out-lap"].includes(String(telemetry?.graphics?.lap_status??graphics.lap_status??"").toLowerCase());
      if(lapTime!==null&&!outLap){
        const t1=tracker.sector1BoundaryMs;
        const t2=tracker.sector2BoundaryMs;
        const validBoundaries=t1!==null&&t2!==null&&t1>0&&t2>t1&&lapTime>t2;
        const s1=validBoundaries?t1:null;
        const s2=validBoundaries?t2-t1:null;
        const s3=validBoundaries?lapTime-t2:null;
        const entry:LapHistoryEntry={lap:completed,timeMs:lapTime,valid:tracker.validity,s1Ms:s1,s2Ms:s2,s3Ms:s3};
        const next=[...readLapHistory(storageKey),entry].slice(-LAP_HISTORY_LIMIT);
        setLapHistory(next);
        try{window.localStorage.setItem(storageKey,JSON.stringify(next));}catch{/* Keep the in-memory history if browser storage is unavailable. */}
      }
      tracker.completedLaps=completed;
      tracker.sector1BoundaryMs=null;
      tracker.sector2BoundaryMs=null;
      tracker.validity=null;
      tracker.sector=sector;
      return;
    }
    if(completed!==null) tracker.completedLaps=completed;
  },[telemetry?.graphics?.data?.completed_laps,telemetry?.graphics?.data?.sector,telemetry?.graphics?.data?.split_time_str,telemetry?.graphics?.data?.last_time_ms,telemetry?.graphics?.data?.is_valid_lap,telemetry?.vehicle?.track,telemetry?.vehicle?.track_configuration,telemetry?.vehicle?.car_model,telemetry?.graphics?.data?.session_index,telemetry?.graphics?.data?.session,telemetry?.graphics?.lap_status]);

  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [active, setActive] = useState("Overview");
  const [tiles, setTiles] = useState<Tile[]>(loadLayout);
  const [draft, setDraft] = useState<Tile[]>(initial);
  const [editing, setEditing] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [dragging, setDragging] = useState<TileId | null>(null);
  const [glow,setGlow] = useState<GlowConfig>(readGlow);
  const [settingsTab,setSettingsTab] = useState<"visual"|"vehicle">("visual");
  const [targetPressures,setTargetPressures] = useState<TargetPressureConfig>(readTargetPressures);
  const setTargetPressure=(corner:keyof TargetPressureConfig,value:string)=>setTargetPressures(prev=>{const next={...prev,[corner]:value};try{window.localStorage.setItem("acc-target-pressures",JSON.stringify(next));}catch{}return next;});
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
    <aside className="navigation-rail"><div className="brand" title="Race Engineer ACC"><div className="brand-mark">RE</div></div><nav aria-label="Main navigation">{groups.map(group=><div className="nav-group" key={group}>{nav.filter(n=>n.group===group).map(item=>{const Icon=item.icon;return <button key={item.name} className={active===item.name?"nav-item selected":"nav-item"} onClick={()=>setActive(item.name)} title={item.name} aria-label={item.name} data-tooltip={item.name}><Icon size={20}/></button>;})}</div>)}</nav><div className="rail-footer" title={connected?"ACC Physics connected":"ACC not connected"}><span className={`status-dot ${connected?"connected":""}`}/></div></aside>
    <main className="main-content"><header className="top-bar"><div><div className="eyebrow">RACE ENGINEER ACC</div><h1>{active}</h1></div><div className="top-bar-actions"><div className="stream-health-group" aria-label="Telemetry stream status">{(["physics","graphics","static"] as const).map((stream) => { const state=(telemetry?.streams?.[stream]?.state??"missing") as StreamFreshness["state"]; return <div key={stream} className={`stream-health-chip stream-${state}`} title={`${stream.toUpperCase()} · ${state.toUpperCase()}`}><i/><span>{stream.toUpperCase()}</span><b>{state==="fresh"?"LIVE":state==="stale"?"STALE":state==="unavailable"?"OFFLINE":"WAITING"}</b></div>; })}</div><button className="theme-toggle" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")} title="Toggle theme">{theme==="dark"?<Sun size={16}/>:<Moon size={16}/>}<span>{theme==="dark"?"Light":"Dark"}</span></button></div></header>
      {active==="Settings" ? <section className="workspace settings-page"><div className="overview-heading"><div><div className="eyebrow">APPLICATION CONFIGURATION</div><h2>Settings</h2><p>Configure vehicle targets and telemetry visual feedback. Changes are saved automatically on this device.</p></div><button className="secondary-action" onClick={()=>{setGlow(defaultGlow);setTargetPressures(defaultTargetPressures);try{window.localStorage.setItem("acc-glow-settings",JSON.stringify(defaultGlow));window.localStorage.setItem("acc-target-pressures",JSON.stringify(defaultTargetPressures));}catch{}}}><RotateCcw size={14}/> Reset all settings</button></div>
        <div className="settings-tabs" role="tablist" aria-label="Settings categories"><button role="tab" aria-selected={settingsTab==="visual"} className={settingsTab==="visual"?"settings-tab active":"settings-tab"} onClick={()=>setSettingsTab("visual")}>Visual Feedback</button><button role="tab" aria-selected={settingsTab==="vehicle"} className={settingsTab==="vehicle"?"settings-tab active":"settings-tab"} onClick={()=>setSettingsTab("vehicle")}>Vehicle &amp; Telemetry</button></div>
        {settingsTab==="visual"?<><div className="settings-panel"><h3>Lap status glow</h3><p>Preview the lap tile using a selected status.</p><select value={glow.lapStatus} onChange={e=>patchGlow({lapStatus:e.target.value as GlowConfig["lapStatus"]})}><option value="valid">Valid · Green</option><option value="invalid">Invalid · Red</option><option value="out">Out lap · Orange</option></select></div><div className="settings-panel"><h3>Preview guide</h3><div className="glow-legend">{["BLUE","GREEN","YELLOW","ORANGE","RED"].map((v,i)=><span key={v} className={"glow-"+i}>{v}</span>)}</div><p>Temperature and damage thresholds, target pressures and glow strength are configured under Vehicle &amp; Telemetry.</p></div></>:<><div className="settings-panel"><h3>Glow intensity · {glow.intensity}%</h3><input className="intensity-slider" type="range" min="10" max="100" value={glow.intensity} onChange={e=>patchGlow({intensity:Number(e.target.value)})}/></div><div className="settings-panel"><h3>Target tyre pressure · PSI</h3><p>Enter an independent target for each wheel. Leave a field blank if you do not want a target comparison for that wheel.</p><div className="threshold-row target-pressure-row">{(["FL","FR","RL","RR"] as const).map(corner=><label key={corner}>{corner}<input type="number" min="0" max="100" step="0.1" placeholder="Not set" value={targetPressures[corner]} onChange={e=>setTargetPressure(corner,e.target.value)}/></label>)}</div></div><div className="settings-panel"><h3>Tyre core temperature · °C</h3><p>Blue, green, yellow, orange and red temperature bands.</p><div className="threshold-row">{glow.tyre.map((v,i)=><label key={i}>{["Blue → Green","Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" value={v} onChange={e=>setBand("tyre",i,Number(e.target.value))}/></label>)}</div></div><div className="settings-panel"><h3>Brake disc temperature · °C</h3><p>Temperature colour bands for brake discs.</p><div className="threshold-row">{glow.brake.map((v,i)=><label key={i}>{["Blue → Green","Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" value={v} onChange={e=>setBand("brake",i,Number(e.target.value))}/></label>)}</div></div><div className="settings-panel"><h3>Vehicle damage thresholds</h3><p>Severity thresholds using the current displayed telemetry scale; units are not asserted.</p><div className="threshold-row">{glow.damage.map((v,i)=><label key={i}>{["Green → Yellow","Yellow → Orange","Orange → Red"][i]}<input type="number" min="0" value={v} onChange={e=>setBand("damage",i,Number(e.target.value))}/></label>)}</div></div></>}</section> : active==="Overview" ? <section className="workspace overview-page"><div className="overview-heading"><div><div className="eyebrow">LIVE APPLICATION STATUS</div><h2>Race overview</h2><p>A focused view of your current ACC session and connected hardware.</p></div><div className="overview-heading-actions"><div className="connection-chip"><span className={connected?"connected":""}/>{connected?"ACC PHYSICS CONNECTED":"ACC DISCONNECTED"}</div>{!editing?<button className="primary-action" onClick={startEdit}>Edit dashboard</button>:<><button className="secondary-action" onClick={()=>setLibraryOpen(v=>!v)}><Plus size={15}/> Add tiles</button><button className="primary-action" onClick={save}><Save size={15}/> Save</button><button className="secondary-action" onClick={cancel}><X size={15}/> Cancel</button></>}</div></div>
      {editing&&<div className="dashboard-editor"><div><strong>Edit Overview</strong><span>Drag unpinned tiles to reorder. Pinned tiles stay in the top section.</span></div><button className="text-action" onClick={reset}><RotateCcw size={14}/> Reset to default</button></div>}
      {editing&&libraryOpen&&<div className="tile-library"><div className="tile-library-heading"><strong>Available tiles</strong><button className="text-action" onClick={()=>setLibraryOpen(false)}>Close</button></div><div className="tile-library-grid">{definitions.filter(d=>!draft.some(t=>t.id===d.id)).map(d=><button className="library-item" key={d.id} onClick={()=>add(d.id)}><strong><Plus size={14}/>{d.title}</strong><span>{d.description}</span></button>)}</div></div>}
      <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const el=(e.target as HTMLElement).closest("[data-tile-id]");const to=el?.getAttribute("data-tile-id") as TileId|null;if(dragging&&to)move(dragging,to);setDragging(null);}}>
        {shown.map(tile=><div key={tile.id} data-tile-id={tile.id} draggable={editing&&!tile.pinned} onDragStart={()=>setDragging(tile.id)} onDragEnd={()=>setDragging(null)} className={`tile-drag-wrapper tile-slot-${tile.size} ${tile.id==="hardware"?"tile-slot-hardware":""}`}>
          <article className="dashboard-tile"><div className="tile-heading"><div><span className="tile-icon">{tile.id==="driver_trace"?<ChartNoAxesCombined/>:tile.id==="speed"?<Gauge/>:tile.id==="gear"?<Zap/>:tile.id==="rpm"?<Activity/>:tile.id==="pedals"?<Waves/>:tile.id==="laps"?<Flag/>:tile.id==="lap_history"?<Clock3/>:tile.id==="weather"?<CloudSun/>:tile.id==="map"?<Map/>:tile.id==="session"?<Radio/>:tile.id==="brakes"?<Thermometer/>:tile.id==="tyres"?<CircleGauge/>:tile.id==="fuel"?<Fuel/>:tile.id==="warnings"?<TriangleAlert/>:tile.id==="delta"?<ChartNoAxesColumnIncreasing/>:tile.id==="sectors"?<Timer/>:tile.id==="position"?<Medal/>:tile.id==="electronics"?<SlidersHorizontal/>:tile.id==="pit_stint"?<Timer/>:tile.id==="damage"?<Wrench/>:tile.id==="pressure_targets"?<Target/>:tile.id==="race_control"?<Siren/>:tile.id==="car_status"?<Lightbulb/>:<Cable/>}</span><h3>{fmt(tile.id)}</h3></div>{editing&&<span className="drag-grip"><GripVertical size={17}/></span>}</div><div className="tile-body"><TileContent id={tile.id} glow={glow} telemetry={{...telemetry,lap_history:lapHistory}} targetPressures={targetPressures} trace={driverTrace} freshness={telemetry?.streams??{}}/></div></article>
          {editing&&<div className="tile-size-control"><label>Size <select value={tile.size} onChange={e=>update(tile.id,{size:e.target.value as TileSize})}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></label><button className="text-action" onClick={()=>update(tile.id,{pinned:!tile.pinned})}>{tile.pinned?<PinOff size={13}/>:<Pin size={13}/>} {tile.pinned?"Unpin":"Pin"}</button><button className="remove-tile" onClick={()=>remove(tile.id)} aria-label={`Remove ${fmt(tile.id)} tile`}><X size={14}/></button></div>}
        </div>)}
      </div></section> : <section className="workspace"><div className="page-placeholder"><div className="placeholder-mark">RE</div><h2>{active}</h2><p>This workspace will be added in a later implementation stage.</p><span className="pending-label">NOT INTEGRATED</span></div></section>}
      <footer className="demo-footnote"><span><Droplets size={13}/> {connected?"LIVE ACC PHYSICS":"ACC TELEMETRY"}</span><span>{connected?`${telemetry.physics?.processed_count??0} decoded samples · ${telemetry.physics?.decode_error_count??0} decode errors`:"Waiting for ACC Shared Memory. Static identity and expanded Graphics decoding are available when a valid sample arrives."}</span></footer>
    </main>
  </div>;
}
export default App;