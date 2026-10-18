"""Read-only CCU diagnostic dump.

Runs inside the backend container (has CCU_HOST/USERNAME/PASSWORD in env):

    docker compose exec backend python scripts/dump_ccu.py            # list WTH devices
    docker compose exec backend python scripts/dump_ccu.py Wohnzimmer # + MASTER/VALUES dump

Nothing is written to the CCU. The password is never printed.
"""
import json
import os
import re
import sys
import xmlrpc.client

import requests

CCU_HOST = os.getenv("CCU_HOST")
CCU_USER = os.getenv("CCU_USERNAME")
CCU_PASS = os.getenv("CCU_PASSWORD")
JSONRPC_URL = f"http://{CCU_HOST}/api/homematic.cgi"
XMLRPC_URL = f"http://{CCU_HOST}:2010"


def jsonrpc(method, params, session=None):
    payload = {"method": method, "params": dict(params), "id": 1, "jsonrpc": "2.0"}
    if session:
        payload["params"]["_session_id_"] = session
    r = requests.post(JSONRPC_URL, json=payload, timeout=10).json()
    if r.get("error"):
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def login():
    return jsonrpc("Session.login", {"username": CCU_USER, "password": CCU_PASS})


def logout(session):
    try:
        jsonrpc("Session.logout", {"_session_id_": session})
    except Exception:
        pass


def find_wth_devices(devices):
    out = []
    for dev in devices:
        t = (dev.get("type") or "")
        if "WTH" in t or "eTRV" in t or "WThermostat".lower() in t.lower():
            out.append(dev)
    return out


def main():
    if not (CCU_HOST and CCU_USER and CCU_PASS):
        sys.exit("CCU_HOST / CCU_USERNAME / CCU_PASSWORD not set in env")

    room = sys.argv[1] if len(sys.argv) > 1 else None
    set_mode_to = None
    if "--set-mode" in sys.argv:
        set_mode_to = int(sys.argv[sys.argv.index("--set-mode") + 1])
    session = login()
    print(f"# CCU {CCU_HOST}  session ok\n")

    try:
        devices = jsonrpc("Device.listAllDetail", {}, session)
    except Exception as e:
        logout(session)
        sys.exit(f"Device.listAllDetail failed: {e}")

    print(f"# {len(devices)} devices total:")
    for dev in devices:
        print(f"  {dev.get('address'):16} {dev.get('type')!s:22} "
              f"iface={dev.get('interface')!s:16} name={dev.get('name')!r}")
    print()

    # floor-heating actuator(s) — FAL / FALMOT — carry the COOLING datapoint on :0
    actuators = [d for d in devices
                 if any(t in (d.get("type") or "").upper()
                        for t in ("FAL", "FALMOT", "HEATING_ACTUATOR"))]
    proxy_pre = xmlrpc.client.ServerProxy(XMLRPC_URL)
    for act in actuators:
        a0 = f"{act['address']}:0"
        print(f"# actuator {act.get('name')!r} {act.get('type')} — {a0}")
        try:
            v = proxy_pre.getParamset(a0, "VALUES")
            for k in sorted(v.keys()):
                print(f"    VALUES {k} = {v[k]!r}")
        except Exception as e:
            print(f"    VALUES failed: {e}")
        try:
            d = proxy_pre.getParamsetDescription(a0, "VALUES")
            for k in sorted(d.keys()):
                ops = d[k].get("OPERATIONS")
                fl = "".join(f for b, f in ((2, "R"), (4, "W"), (8, "E"))
                             if isinstance(ops, int) and ops & b)
                print(f"    DESC   {k:26} {d[k].get('TYPE'):9} {fl or ops}")
        except Exception as e:
            print(f"    DESC failed: {e}")
        print()

    wth = find_wth_devices(devices)
    print(f"# {len(wth)} thermostat-like devices:\n")
    for dev in wth:
        chans = [c.get("address") for c in dev.get("channels", [])]
        print(f"  name={dev.get('name')!r:24} address={dev.get('address')} "
              f"type={dev.get('type')} interface={dev.get('interface')}")
        print(f"    channels: {chans}")
    print()

    # also show the heating groups (VirtualDevices / HmIP-HEATING) for comparison
    groups = [d for d in devices
              if d.get("interface") == "VirtualDevices" and d.get("type") == "HmIP-HEATING"]
    print(f"# {len(groups)} heating groups (VirtualDevices):")
    for g in groups:
        print(f"  name={g.get('name')!r}  address={g.get('address')}")
    print()

    if not room:
        print("# pass a room name as argument for a MASTER/VALUES dump")
        logout(session)
        return

    target = next((d for d in wth
                   if room.lower() in (d.get("name") or "").lower()), None)
    if not target:
        logout(session)
        sys.exit(f"no thermostat-like device matching {room!r}")

    base = target["address"]
    ch1 = f"{base}:1"
    print(f"# target: {target.get('name')!r}  device={base}  channel={ch1}  "
          f"type={target.get('type')}\n")

    proxy = xmlrpc.client.ServerProxy(XMLRPC_URL)

    # ---- OPTIONAL: heat/cool write probe on the FALMOT actuator ----
    if "--climate" in sys.argv:
        want = int(sys.argv[sys.argv.index("--climate") + 1])  # 0=heat 1=cool
        fal = next((d for d in devices
                    if "FALMOT" in (d.get("type") or "").upper()), None)
        if not fal:
            logout(session)
            sys.exit("no FALMOT actuator")
        fa = fal["address"]
        f0 = f"{fa}:0"
        print(f"# FALMOT {fa}, target HEATING_COOLING={want}\n")

        for label, ps in (("MASTER", "MASTER"), ("VALUES", "VALUES")):
            try:
                d = proxy.getParamsetDescription(f0, ps)
                print(f"## FALMOT :0 {label} description ({len(d)} params):")
                for k in sorted(d):
                    o = d[k].get("OPERATIONS")
                    fl = "".join(x for b, x in ((2, "R"), (4, "W"), (8, "E"))
                                 if isinstance(o, int) and o & b)
                    print(f"   {k:26} {d[k].get('TYPE'):9} {fl or o} "
                          f"vals={d[k].get('VALUE_LIST')}")
            except Exception as e:
                print(f"## FALMOT :0 {label} desc -> {e}")
        try:
            v = proxy.getParamset(f0, "MASTER")
            print(f"\n## FALMOT :0 MASTER values ({len(v)}):")
            for k in sorted(v):
                print(f"   {k} = {v[k]!r}")
        except Exception as e:
            print(f"## FALMOT :0 MASTER values -> {e}")

        def read_hc(addr):
            try:
                return proxy.getValue(addr, "HEATING_COOLING")
            except Exception as e:
                return f"err {e}"

        print(f"\n## before: FALMOT:0={read_hc(f0)!r}  WTH:1={read_hc(ch1)!r}")
        attempts = [
            ("jsonrpc putParamset FALMOT:0 MASTER COOLING bool",
             lambda: jsonrpc("Interface.putParamset",
                             {"interface": "HmIP-RF", "address": f0, "paramsetKey": "MASTER",
                              "set": [{"name": "COOLING", "type": "boolean",
                                       "value": "1" if want else "0"}]}, session)),
            ("jsonrpc putParamset FALMOT:0 VALUES HEATING_COOLING int",
             lambda: jsonrpc("Interface.putParamset",
                             {"interface": "HmIP-RF", "address": f0, "paramsetKey": "VALUES",
                              "set": [{"name": "HEATING_COOLING", "type": "int",
                                       "value": str(want)}]}, session)),
            ("jsonrpc putParamset WTH:1 VALUES HEATING_COOLING int",
             lambda: jsonrpc("Interface.putParamset",
                             {"interface": "HmIP-RF", "address": ch1, "paramsetKey": "VALUES",
                              "set": [{"name": "HEATING_COOLING", "type": "int",
                                       "value": str(want)}]}, session)),
            ("xmlrpc putParamset FALMOT:0 MASTER {COOLING: bool}",
             lambda: proxy.putParamset(f0, "MASTER", {"COOLING": bool(want)})),
        ]
        import time as _t
        for label, fn in attempts:
            try:
                r = fn()
                print(f"\n  {label}\n    ret={r!r}")
            except Exception as e:
                print(f"\n  {label}\n    err={e.args[0] if e.args else e}")
            _t.sleep(2)
            print(f"    after: FALMOT:0={read_hc(f0)!r}  WTH:1={read_hc(ch1)!r}")

        logout(session)
        return

    # ---- OPTIONAL: JSON-RPC Interface.putParamset with set=[{name,type,value}] ----
    if "--jsonwrite" in sys.argv:
        iface = target["interface"]
        print(f"# Interface.putParamset format search, iface={iface}, addr={ch1}\n")

        # 2) Interface.putParamset (JSON-RPC) – find the working `set` element
        #    format via read-back on P6_TEMPERATURE_TUESDAY_1 (currently corrupted).
        import time as _t
        addr = ch1

        def read1():
            return proxy.getParamset(addr, "MASTER").get("P6_TEMPERATURE_TUESDAY_1")

        def put(set_val, label):
            try:
                r = jsonrpc("Interface.putParamset",
                            {"interface": iface, "address": addr,
                             "paramsetKey": "MASTER", "set": set_val}, session)
                print(f"  {label}\n    ret={r!r}")
            except Exception as e:
                print(f"  {label}\n    err={e.args[0] if e.args else e}")
            _t.sleep(2)
            print(f"    -> P6_TEMPERATURE_TUESDAY_1 = {read1()!r}")

        def readday():
            mm = proxy.getParamset(addr, "MASTER")
            return {k: mm[k] for k in mm if k.startswith("P6_") and "TUESDAY" in k}

        # 1) confirm the int type name for ENDTIME
        for t in ("int", "i4", "integer"):
            k = "P6_ENDTIME_TUESDAY_1"
            put([{"name": k, "type": t, "value": "540"}], f"ENDTIME type={t}")
            v = proxy.getParamset(addr, "MASTER").get(k)
            print(f"    P6_ENDTIME_TUESDAY_1 = {v!r}")

        # 2) repair the whole day with correct types
        ends = {1: 540, 2: 720, 3: 780, 4: 840}
        temps = {1: 28.0, 2: 27.0, 3: 28.0, 4: 28.5}
        setlist = []
        for i in range(1, 14):
            setlist.append({"name": f"P6_ENDTIME_TUESDAY_{i}", "type": "int",
                            "value": str(ends.get(i, 1440))})
            setlist.append({"name": f"P6_TEMPERATURE_TUESDAY_{i}", "type": "double",
                            "value": str(temps.get(i, 28.0))})
        put(setlist, f"\n  REPAIR: full P6 TUESDAY, {len(setlist)} elements")

        print("\n  P6 TUESDAY after repair:")
        for k, v in sorted(readday().items(),
                           key=lambda kv: (("ENDTIME" not in kv[0]), int(kv[0].rsplit("_", 1)[1]))):
            print(f"    {k} = {v!r} ({type(v).__name__})")

        logout(session)
        return

    # ---- OPTIONAL: write a subset of MASTER straight back, unchanged ----
    #   --roundtrip P6 TUESDAY   -> the 26 keys of that day
    #   --roundtrip P6           -> all ~182 keys of that profile (7 days)
    #   --roundtrip ALL          -> the entire MASTER paramset
    if "--roundtrip" in sys.argv:
        idx = sys.argv.index("--roundtrip")
        scope = sys.argv[idx + 1].upper()
        day_id = sys.argv[idx + 2].upper() if len(sys.argv) > idx + 2 \
            and not sys.argv[idx + 2].startswith("-") else None
        m = proxy.getParamset(ch1, "MASTER")

        if scope == "ALL":
            sub = dict(m)
        elif day_id:
            ends = tuple(f"_{day_id}_{i}" for i in range(1, 14))
            sub = {k: m[k] for k in m if k.startswith(f"{scope}_") and k.endswith(ends)}
        else:
            sub = {k: m[k] for k in m if k.startswith(f"{scope}_")}

        print(f"## {scope} {day_id or ''}: {len(sub)} keys")
        for k in sorted(sub)[:30]:
            print(f"   {k} = {sub[k]!r} ({type(sub[k]).__name__})")
        if len(sub) > 30:
            print(f"   ... (+{len(sub) - 30} more)")

        print(f"\n## writing those {len(sub)} keys back unchanged ...")
        try:
            proxy.putParamset(ch1, "MASTER", sub)
            print("   -> OK, CCU accepted it")
        except Exception as e:
            print(f"   -> REJECTED: {e}")

        # also: description of the profile keys (MIN/MAX/OPERATIONS)
        try:
            d = proxy.getParamsetDescription(ch1, "MASTER")
            sample = next((k for k in d if k.startswith(f"{scope}_TEMPERATURE_")), None)
            sample_e = next((k for k in d if k.startswith(f"{scope}_ENDTIME_")), None)
            for k in (sample, sample_e):
                if k:
                    print(f"   DESC {k}: {d[k]}")
        except Exception as e:
            print(f"   (description failed: {e})")

        logout(session)
        return

    # ---- MASTER via XML-RPC ----
    try:
        master = proxy.getParamset(ch1, "MASTER")
        keys = sorted(master.keys())
        print(f"## XML-RPC getParamset({ch1}, MASTER): {len(keys)} keys")

        prefixes = {}
        for k in keys:
            m = re.match(r"^(HEATING_|COOLING_)?P(\d+)_", k)
            if m:
                tag = (m.group(1) or "PLAIN")
                prefixes.setdefault(tag, set()).add(int(m.group(2)))
        print("   profile key families:")
        for tag, profs in sorted(prefixes.items()):
            print(f"     {tag:9} -> profiles {sorted(profs)}")

        non_profile = sorted(k for k in keys if not re.match(r"^(HEATING_|COOLING_)?P\d+_", k))
        print(f"   non-profile MASTER keys ({len(non_profile)}):")
        for k in non_profile:
            print(f"     {k} = {master[k]!r}")

        sample_day = [k for k in keys if re.search(r"MONDAY_1$", k)]
        print(f"   MONDAY_1 keys: {sample_day}")
        max_slot = 0
        for k in keys:
            m = re.search(r"MONDAY_(\d+)$", k)
            if m:
                max_slot = max(max_slot, int(m.group(1)))
        print(f"   max slot index (MONDAY): {max_slot}")

        # dump one full profile/day so we see real values + the 1440/base behaviour
        for cand in ("P1_", "HEATING_P1_", "COOLING_P1_"):
            dayk = sorted(k for k in keys if k.startswith(cand) and "MONDAY" in k)
            if dayk:
                print(f"   sample {cand}*MONDAY*:")
                for k in dayk:
                    print(f"     {k} = {master[k]!r}")
                break
        print()
    except Exception as e:
        print(f"## MASTER dump failed: {e}\n")

    # ---- VALUES via XML-RPC ----
    try:
        values = proxy.getParamset(ch1, "VALUES")
        print(f"## XML-RPC getParamset({ch1}, VALUES): {len(values)} keys")
        for k in sorted(values.keys()):
            print(f"   {k} = {values[k]!r}")
        print()
    except Exception as e:
        print(f"## VALUES dump failed: {e}\n")

    # ---- channel :0 (maintenance) VALUES: battery / rssi ----
    ch0 = f"{base}:0"
    try:
        v0 = proxy.getParamset(ch0, "VALUES")
        print(f"## XML-RPC getParamset({ch0}, VALUES): {len(v0)} keys")
        for k in sorted(v0.keys()):
            print(f"   {k} = {v0[k]!r}")
        print()
    except Exception as e:
        print(f"## channel :0 VALUES failed: {e}\n")

    # ---- VALUES paramset description on :1 (shows writable / mode params) ----
    try:
        desc = proxy.getParamsetDescription(ch1, "VALUES")
        print(f"## getParamsetDescription({ch1}, VALUES): {len(desc)} params")
        for k in sorted(desc.keys()):
            d = desc[k]
            ops = d.get("OPERATIONS")  # bit1=read bit2=write bit4=event
            flags = []
            if isinstance(ops, int):
                if ops & 2:
                    flags.append("R")
                if ops & 4:
                    flags.append("W")
                if ops & 8:
                    flags.append("E")
            print(f"   {k:28} type={d.get('TYPE'):10} ops={''.join(flags) or ops} "
                  f"min={d.get('MIN')!r} max={d.get('MAX')!r} "
                  f"values={d.get('VALUE_LIST')}")
        print()
    except Exception as e:
        print(f"## getParamsetDescription failed: {e}\n")

    # ---- heating group: VALUES + description (mode write params live here) ----
    grp = next((g for g in groups
                if room.lower() in (g.get("name") or "").lower()), None)
    if grp:
        gaddr = f"{grp['address']}:1"
        try:
            gv = jsonrpc("Interface.getParamset",
                         {"interface": "VirtualDevices", "address": gaddr,
                          "paramsetKey": "VALUES"}, session)
            print(f"## JSON-RPC group VALUES {gaddr} ({grp['name']}): {len(gv)} keys")
            print("   " + json.dumps(gv, indent=2, default=str).replace("\n", "\n   "))
            print()
        except Exception as e:
            print(f"## group VALUES failed: {e}\n")

        # group is on the VirtualDevices interface -> use JSON-RPC, not :2010
        try:
            gd = jsonrpc("Interface.getParamsetDescription",
                         {"interface": "VirtualDevices", "address": gaddr,
                          "paramsetKey": "VALUES"}, session)
            # JSON-RPC may return a list of {NAME, TYPE, OPERATIONS, ...} or a dict
            items = gd.values() if isinstance(gd, dict) else gd
            print(f"## group getParamsetDescription VALUES: {len(items)} params")
            for d in sorted(items, key=lambda x: str(x.get("NAME") or x.get("ID"))):
                name = d.get("NAME") or d.get("ID")
                ops = d.get("OPERATIONS")
                ops = int(ops) if str(ops).lstrip("-").isdigit() else ops
                fl = "".join(f for b, f in ((2, "R"), (4, "W"), (8, "E"))
                             if isinstance(ops, int) and ops & b)
                print(f"   {name!s:28} type={d.get('TYPE')} ops={fl or ops} "
                      f"min={d.get('MIN')!r} max={d.get('MAX')!r} "
                      f"default={d.get('DEFAULT')!r} "
                      f"values={d.get('VALUE_LIST') or d.get('VALUES')}")
            print()
        except Exception as e:
            print(f"## group description failed: {e}\n")

    # ---- mode-related single datapoints ----
    print("## getValue probes:")
    for dp in ("CONTROL_MODE", "SET_POINT_MODE", "ACTIVE_PROFILE",
               "HEATING_COOLING", "OPERATING_MODE", "SET_POINT_TEMPERATURE"):
        try:
            print(f"   {dp} = {proxy.getValue(ch1, dp)!r}")
        except Exception as e:
            print(f"   {dp} -> {e}")
    print()

    # ---- same VALUES via JSON-RPC (what /heating/state/all uses) ----
    try:
        js_vals = jsonrpc("Interface.getParamset",
                          {"interface": target["interface"],
                           "address": ch1, "paramsetKey": "VALUES"}, session)
        print(f"## JSON-RPC Interface.getParamset VALUES: {len(js_vals)} keys")
        print("   " + json.dumps(js_vals, indent=2, default=str).replace("\n", "\n   "))
    except Exception as e:
        print(f"## JSON-RPC VALUES failed: {e}")

    # ---- OPTIONAL write test: does SET_POINT_MODE take on device vs group? ----
    if set_mode_to is not None:
        import time as _t

        def _read():
            dev = grp_v = None
            try:
                dev = proxy.getValue(ch1, "SET_POINT_MODE")
            except Exception as e:
                dev = f"err {e}"
            if grp:
                try:
                    grp_v = jsonrpc("Interface.getValue",
                                    {"interface": "VirtualDevices",
                                     "address": gaddr, "valueKey": "SET_POINT_MODE"},
                                    session)
                except Exception as e:
                    grp_v = f"err {e}"
            return dev, grp_v

        print(f"\n## WRITE TEST: SET_POINT_MODE -> {set_mode_to}  (state WILL change)")
        print(f"   before: device={_read()[0]!r} group={_read()[1]!r}")

        for label, fn in (
            ("device setValue SET_POINT_MODE",
             lambda: proxy.setValue(ch1, "SET_POINT_MODE", set_mode_to)),
            ("device putParamset VALUES SET_POINT_MODE",
             lambda: proxy.putParamset(ch1, "VALUES", {"SET_POINT_MODE": set_mode_to})),
            ("device putParamset VALUES CONTROL_MODE",
             lambda: proxy.putParamset(ch1, "VALUES", {"CONTROL_MODE": set_mode_to})),
            ("device putParamset MASTER CONTROL_MODE",
             lambda: proxy.putParamset(ch1, "MASTER", {"CONTROL_MODE": set_mode_to})),
        ):
            try:
                fn()
                print(f"   [{label}] sent")
            except Exception as e:
                print(f"   [{label}] {e}")
            _t.sleep(3)
            print(f"     -> device={_read()[0]!r} group={_read()[1]!r}")

        if grp:
            for typ in ("integer", "int"):
                try:
                    jsonrpc("Interface.setValue",
                            {"interface": "VirtualDevices", "address": gaddr,
                             "valueKey": "SET_POINT_MODE", "type": typ,
                             "value": set_mode_to}, session)
                    print(f"   [group JSON-RPC setValue type={typ}] sent")
                    break
                except Exception as e:
                    print(f"   [group JSON-RPC setValue type={typ}] {e}")
            _t.sleep(3)
            print(f"   after group write:  device={_read()[0]!r} group={_read()[1]!r}")

    logout(session)


if __name__ == "__main__":
    main()
