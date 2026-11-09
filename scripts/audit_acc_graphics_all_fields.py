#!/usr/bin/env python3
"""Full offline audit of the 87-field Pro Engineer ACC Graphics candidate layout.

Reads an existing ACCGFX01 .gfxraw file; validates header/block CRCs, sequences,
record lengths and packet IDs; never connects to ACC or modifies the recording.
Offsets are source-derived candidate layout, not official Kunos ABI sign-off.
"""
from __future__ import annotations
import argparse, json, math, struct, zlib
from collections import Counter
from pathlib import Path

HEADER=struct.Struct("<8sIIQI")
BLOCK=struct.Struct("<4sQIII")
RECORD=struct.Struct("<QQQQQI")
MAGIC=b"ACCGFX01"
BLOCK_MAGIC=b"GFXB"
FIELDS=[
  {
    "name": "packet_id",
    "type": "i32",
    "offset": 0,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "status",
    "type": "i32",
    "offset": 4,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "session",
    "type": "i32",
    "offset": 8,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "current_time",
    "type": "[u16; 15]",
    "offset": 12,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "last_time",
    "type": "[u16; 15]",
    "offset": 42,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "best_time",
    "type": "[u16; 15]",
    "offset": 72,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "split",
    "type": "[u16; 15]",
    "offset": 102,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "completed_laps",
    "type": "i32",
    "offset": 132,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "position",
    "type": "i32",
    "offset": 136,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "i_current_time",
    "type": "i32",
    "offset": 140,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "i_last_time",
    "type": "i32",
    "offset": 144,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "i_best_time",
    "type": "i32",
    "offset": 148,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "session_time_left",
    "type": "f32",
    "offset": 152,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "distance_traveled",
    "type": "f32",
    "offset": 156,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "is_in_pit",
    "type": "i32",
    "offset": 160,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "current_sector_index",
    "type": "i32",
    "offset": 164,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "last_sector_time",
    "type": "i32",
    "offset": 168,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "number_of_laps",
    "type": "i32",
    "offset": 172,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "tyre_compound",
    "type": "StringU16_33",
    "offset": 176,
    "size": 66,
    "kind": "u16str",
    "count": 33
  },
  {
    "name": "replay_time_multiplier",
    "type": "f32",
    "offset": 244,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "normalized_car_position",
    "type": "f32",
    "offset": 248,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "active_cars",
    "type": "i32",
    "offset": 252,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "car_coordinates",
    "type": "CarPositions",
    "offset": 256,
    "size": 720,
    "kind": "f32array",
    "count": 180
  },
  {
    "name": "car_id",
    "type": "CarIds",
    "offset": 976,
    "size": 240,
    "kind": "i32array",
    "count": 60
  },
  {
    "name": "player_car_id",
    "type": "i32",
    "offset": 1216,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "penalty_time",
    "type": "f32",
    "offset": 1220,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "flag",
    "type": "i32",
    "offset": 1224,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "penalty",
    "type": "i32",
    "offset": 1228,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "ideal_line_on",
    "type": "i32",
    "offset": 1232,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "is_in_pit_lane",
    "type": "i32",
    "offset": 1236,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "surface_grip",
    "type": "f32",
    "offset": 1240,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "mandatory_pit_done",
    "type": "i32",
    "offset": 1244,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "wind_speed",
    "type": "f32",
    "offset": 1248,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "wind_direction",
    "type": "f32",
    "offset": 1252,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "is_setup_menu_visible",
    "type": "i32",
    "offset": 1256,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "main_display_index",
    "type": "i32",
    "offset": 1260,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "secondary_display_index",
    "type": "i32",
    "offset": 1264,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "tc",
    "type": "i32",
    "offset": 1268,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "tc_cut",
    "type": "i32",
    "offset": 1272,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "engine_map",
    "type": "i32",
    "offset": 1276,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "abs",
    "type": "i32",
    "offset": 1280,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "fuel_x_lap",
    "type": "f32",
    "offset": 1284,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "rain_lights",
    "type": "i32",
    "offset": 1288,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "flashing_lights",
    "type": "i32",
    "offset": 1292,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "lights_stage",
    "type": "i32",
    "offset": 1296,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "exhaust_temperature",
    "type": "f32",
    "offset": 1300,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "wiper_stage",
    "type": "i32",
    "offset": 1304,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "driver_stint_total_time_left",
    "type": "i32",
    "offset": 1308,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "driver_stint_time_left",
    "type": "i32",
    "offset": 1312,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "rain_tyres",
    "type": "i32",
    "offset": 1316,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "session_index",
    "type": "i32",
    "offset": 1320,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "used_fuel",
    "type": "f32",
    "offset": 1324,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "delta_lap_time",
    "type": "[u16; 15]",
    "offset": 1328,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "i_delta_lap_time",
    "type": "i32",
    "offset": 1360,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "estimated_lap_time",
    "type": "[u16; 15]",
    "offset": 1364,
    "size": 30,
    "kind": "u16array",
    "count": 15
  },
  {
    "name": "i_estimated_lap_time",
    "type": "i32",
    "offset": 1396,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "is_delta_positive",
    "type": "i32",
    "offset": 1400,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "i_split",
    "type": "i32",
    "offset": 1404,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "is_valid_lap",
    "type": "i32",
    "offset": 1408,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "fuel_estimated_laps",
    "type": "f32",
    "offset": 1412,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "track_status",
    "type": "StringU16_33",
    "offset": 1416,
    "size": 66,
    "kind": "u16str",
    "count": 33
  },
  {
    "name": "missing_mandatory_pits",
    "type": "i32",
    "offset": 1484,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "clock",
    "type": "f32",
    "offset": 1488,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "direction_lights_left",
    "type": "i32",
    "offset": 1492,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "direction_lights_right",
    "type": "i32",
    "offset": 1496,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_yellow",
    "type": "i32",
    "offset": 1500,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_yellow_1",
    "type": "i32",
    "offset": 1504,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_yellow_2",
    "type": "i32",
    "offset": 1508,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_yellow_3",
    "type": "i32",
    "offset": 1512,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_white",
    "type": "i32",
    "offset": 1516,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_green",
    "type": "i32",
    "offset": 1520,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_chequered",
    "type": "i32",
    "offset": 1524,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "global_red",
    "type": "i32",
    "offset": 1528,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "mfd_tyre_set",
    "type": "i32",
    "offset": 1532,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "mfd_fuel_to_add",
    "type": "f32",
    "offset": 1536,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "mfd_tyre_pressure_lf",
    "type": "f32",
    "offset": 1540,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "mfd_tyre_pressure_rf",
    "type": "f32",
    "offset": 1544,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "mfd_tyre_pressure_lr",
    "type": "f32",
    "offset": 1548,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "mfd_tyre_pressure_rr",
    "type": "f32",
    "offset": 1552,
    "size": 4,
    "kind": "f32",
    "count": 1
  },
  {
    "name": "track_grip_status",
    "type": "i32",
    "offset": 1556,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "rain_intensity",
    "type": "i32",
    "offset": 1560,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "rain_intensity_in_10min",
    "type": "i32",
    "offset": 1564,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "rain_intensity_in_30min",
    "type": "i32",
    "offset": 1568,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "current_tyre_set",
    "type": "i32",
    "offset": 1572,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "strategy_tyre_set",
    "type": "i32",
    "offset": 1576,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "gap_ahead",
    "type": "i32",
    "offset": 1580,
    "size": 4,
    "kind": "i32",
    "count": 1
  },
  {
    "name": "gap_behind",
    "type": "i32",
    "offset": 1584,
    "size": 4,
    "kind": "i32",
    "count": 1
  }
]

def read_pages(path):
    data=path.read_bytes()
    if len(data)<HEADER.size: raise ValueError("incomplete header")
    magic,version,page_size,created,crc=HEADER.unpack_from(data)
    if magic!=MAGIC or version!=1: raise ValueError("unsupported recording")
    if zlib.crc32(data[:HEADER.size-4])!=crc: raise ValueError("header CRC mismatch")
    if page_size<1588: raise ValueError(f"page size {page_size} < candidate 1588")
    pages=[]; meta=[]; pos=HEADER.size; block_no=1; rec_no=1
    while pos<len(data):
        if len(data)-pos<BLOCK.size: raise ValueError("truncated block header")
        bm,bseq,count,payload_len,checksum=BLOCK.unpack_from(data,pos); pos+=BLOCK.size
        if bm!=BLOCK_MAGIC or bseq!=block_no or count<=0: raise ValueError(f"bad block {block_no}")
        end=pos+payload_len
        if end>len(data): raise ValueError(f"truncated block {bseq}")
        payload=data[pos:end]
        if zlib.crc32(payload)!=checksum: raise ValueError(f"block CRC mismatch {bseq}")
        q=0
        for _ in range(count):
            if len(payload)-q<RECORD.size: raise ValueError("truncated record header")
            seq,packet,started,completed,captured,size=RECORD.unpack_from(payload,q); q+=RECORD.size
            if seq!=rec_no or size!=page_size or q+size>len(payload): raise ValueError(f"invalid record {seq}")
            page=payload[q:q+size]; q+=size
            if struct.unpack_from("<i",page,0)[0]!=packet: raise ValueError(f"packet mismatch {seq}")
            pages.append(page); meta.append({"sequence":seq,"packet_id":packet,"capture_ns":captured})
            rec_no+=1
        if q!=len(payload): raise ValueError(f"trailing payload in block {bseq}")
        pos=end; block_no+=1
    if not pages: raise ValueError("no samples")
    return page_size,pages,meta,len(data)

def decode(page,f):
    o=f["offset"]; k=f["kind"]; n=f["count"]
    if k=="i32": return struct.unpack_from("<i",page,o)[0]
    if k=="f32": return struct.unpack_from("<f",page,o)[0]
    if k=="u16str":
        units=struct.unpack_from("<"+"H"*n,page,o)
        raw=bytes().join(struct.pack("<H",u) for u in units)
        return raw.decode("utf-16-le",errors="replace").split("\x00",1)[0]
    if k=="u16array": return list(struct.unpack_from("<"+"H"*n,page,o))
    if k=="i32array": return list(struct.unpack_from("<"+"i"*n,page,o))
    if k=="f32array": return list(struct.unpack_from("<"+"f"*n,page,o))
    raise ValueError(k)

def summarize_scalar(values,meta):
    nums=[v for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and (not isinstance(v,float) or math.isfinite(v))]
    changes=[]; prev=object()
    for i,v in enumerate(values):
        if i and v!=prev:
            changes.append({"sample":i,"elapsed_seconds":round((meta[i]["capture_ns"]-meta[0]["capture_ns"])/1e9,3),"from":prev,"to":v})
        prev=v
    return {"first":values[0],"last":values[-1],"min":min(nums) if nums else None,"max":max(nums) if nums else None,
            "unique_count":len(set(values)),"transitions":len(changes),"transition_examples":changes[:100],
            "most_common":Counter(values).most_common(20)}

def summarize_array(pages,f):
    o=f["offset"]; n=f["count"]; k=f["kind"]; fmt={"u16array":"H","i32array":"i","f32array":"f"}[k]
    slots=[]
    for j in range(n):
        vals=[struct.unpack_from("<"+fmt,p,o+j*4 if fmt!="H" else o+j*2)[0] for p in pages]
        finite=[x for x in vals if not isinstance(x,float) or math.isfinite(x)]
        slots.append({"index":j,"first":vals[0],"last":vals[-1],"min":min(finite) if finite else None,
                      "max":max(finite) if finite else None,"unique_count":len(set(vals)),
                      "transitions":sum(a!=b for a,b in zip(vals,vals[1:]))})
    return {"element_count":n,"slots":slots}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recording",type=Path)
    ap.add_argument("--json-out",type=Path,required=True)
    ap.add_argument("--max-transitions",type=int,default=100)
    a=ap.parse_args()
    page_size,pages,meta,file_size=read_pages(a.recording)
    report_fields={}
    for f in FIELDS:
        name=f["name"]; kind=f["kind"]
        if kind in ("i32","f32"):
            values=[decode(p,f) for p in pages]
            item=summarize_scalar(values,meta)
            item["transition_examples"]=item["transition_examples"][:a.max_transitions]
        elif kind=="u16str":
            values=[decode(p,f) for p in pages]
            changes=sum(x!=y for x,y in zip(values,values[1:]))
            item={"first":values[0],"last":values[-1],"unique_count":len(set(values)),
                  "transitions":changes,"observed_values":Counter(values).most_common(30)}
        else:
            item=summarize_array(pages,f)
        item.update({"offset":f["offset"],"offset_hex":hex(f["offset"]),"source_type":f["type"],"kind":kind,"size_bytes":f["size"]})
        report_fields[name]=item
    # Crash-oriented coarse event index: samples where any field in the selected
    # timing/flag/position/penalty/pit group changes. It is correlation, not proof of collision.
    watch=["position","flag","penalty","penalty_time",
           "global_yellow","global_yellow_1","global_yellow_2","global_yellow_3","global_red",
           "is_in_pit","is_in_pit_lane","completed_laps","current_sector_index","is_valid_lap"]
    event_samples=set()
    for name in watch:
        f=next(x for x in FIELDS if x["name"]==name)
        prev=None
        for i,p in enumerate(pages):
            v=decode(p,f)
            if i and v!=prev: event_samples.add(i)
            prev=v
    events=[]
    for i in sorted(event_samples):
        elapsed=(meta[i]["capture_ns"]-meta[0]["capture_ns"])/1e9
        events.append({"sample":i,"elapsed_seconds":round(elapsed,3),"packet_id":meta[i]["packet_id"],
                       "changed_watch_fields":[n for n in watch if decode(pages[i],next(x for x in FIELDS if x["name"]==n))!=decode(pages[i-1],next(x for x in FIELDS if x["name"]==n))]})
    report={"recording":str(a.recording),"file_size_bytes":file_size,"page_size_bytes":page_size,
            "candidate_struct_size_bytes":1588,"opaque_tail_bytes":page_size-1588,"sample_count":len(pages),
            "duration_seconds":round((meta[-1]["capture_ns"]-meta[0]["capture_ns"])/1e9,3),
            "integrity":{"blocks_crc_checked":True,"record_sequence_checked":True,"packet_id_checked":True},
            "source_layout":{"source":"Pro Engineer AccGraphics at pinned commit b33ab4b2c8dfcfeb1079cfb08197fe7e77127b26",
                             "field_count":len(FIELDS),"fields":FIELDS},
            "fields":report_fields,"event_index":{"watch_fields":watch,"event_sample_count":len(events),"events":events},
            "notes":["All offsets/types are source-derived candidate mappings, not official Kunos ABI sign-off.",
                     "Array slots are reported individually; coordinate slots are 60 cars x/y/z.",
                     "String values are decoded as UTF-16LE, NUL terminated.",
                     "Event index correlates state changes only; it cannot prove a collision or damage.",
                     "The complete raw mapping is preserved; bytes beyond candidate offset 1588 remain opaque."]}
    a.json_out.parent.mkdir(parents=True,exist_ok=True)
    a.json_out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("ACC GRAPHICS COMPLETE CANDIDATE FIELD AUDIT")
    print(f"Samples: {len(pages):,} | page: {page_size:,} bytes | candidate: 1,588 bytes | duration: {report['duration_seconds']:.1f}s")
    print(f"Fields: {len(FIELDS)} | scalar: {sum(x['kind'] in ('i32','f32') for x in FIELDS)} | arrays: {sum('array' in x['kind'] for x in FIELDS)} | strings: {sum(x['kind']=='u16str' for x in FIELDS)}")
    print("\\nFIELD | OFFSET | TYPE | FIRST | LAST | MIN | MAX | CHANGES/UNIQUE")
    for f in FIELDS:
        v=report_fields[f["name"]]
        first=v.get("first",v.get("slots",[{}])[0].get("first") if v.get("slots") else v.get("observed_values",[[""]])[0][0])
        last=v.get("last",v.get("slots",[{}])[0].get("last") if v.get("slots") else "")
        print(f'{f["name"]} | {f["offset"]:#06x} | {f["type"]} | {str(first)[:42]} | {str(last)[:42]} | {v.get("min","")} | {v.get("max","")} | {v.get("transitions",v.get("unique_count",""))}')
    print(f"\nEvent-index samples: {len(events)} (correlation only)")
    print(f"JSON report: {a.json_out}")
if __name__=="__main__": main()
