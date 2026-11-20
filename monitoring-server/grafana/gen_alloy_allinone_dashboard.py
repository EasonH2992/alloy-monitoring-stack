"""產生 Alloy All-in-One dashboard JSON"""
import json, sys

P = {"type": "prometheus", "uid": "prometheus"}
L = {"type": "loki", "uid": "loki"}
H = 'host=~"$host"'
UNIX = f'job="integrations/unix", {H}'
CAD = f'job="integrations/cadvisor", {H}'
SELF = f'job="integrations/self", {H}'

panels = []
_id = [0]
y = [0]


def nid():
    _id[0] += 1
    return _id[0]


def row(title):
    panels.append({"type": "row", "title": title, "collapsed": False, "id": nid(),
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y[0]}, "panels": []})
    y[0] += 1


def t(expr, legend="", ref="A", **kw):
    d = {"refId": ref, "expr": expr, "legendFormat": legend}
    d.update(kw)
    return d


def thr(*steps):
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}


def stat(title, targets, x, w, h=4, unit="short", ds=P, thresholds=None, mappings=None,
         color="value", graph="none", text="value_and_name", decimals=None, novalue=None, calcs="lastNotNull"):
    d = {"unit": unit, "thresholds": thresholds or thr(("blue", None))}
    if mappings: d["mappings"] = mappings
    if decimals is not None: d["decimals"] = decimals
    if novalue: d["noValue"] = novalue
    panels.append({"id": nid(), "type": "stat", "title": title, "datasource": ds,
                   "gridPos": {"h": h, "w": w, "x": x, "y": y[0]}, "targets": targets,
                   "fieldConfig": {"defaults": d, "overrides": []},
                   "options": {"reduceOptions": {"calcs": [calcs]}, "colorMode": color,
                               "graphMode": graph, "textMode": text}})


def ts(title, targets, x, w, h=8, unit="short", ds=P, legend="list", place="bottom",
       bars=False, stack=False, overrides=None, minv=None, calcs=None):
    custom = {"fillOpacity": 80 if bars else 10}
    if bars: custom["drawStyle"] = "bars"
    if stack: custom["stacking"] = {"mode": "normal"}
    d = {"unit": unit, "custom": custom}
    if minv is not None: d["min"] = minv
    leg = {"displayMode": legend, "placement": place}
    if calcs: leg["calcs"] = calcs
    panels.append({"id": nid(), "type": "timeseries", "title": title, "datasource": ds,
                   "gridPos": {"h": h, "w": w, "x": x, "y": y[0]}, "targets": targets,
                   "fieldConfig": {"defaults": d, "overrides": overrides or []},
                   "options": {"legend": leg, "tooltip": {"mode": "multi", "sort": "desc"}}})


def color_by(name, c, regex=False):
    return {"matcher": {"id": "byRegexp" if regex else "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}


LEVEL_COLORS = [color_by("(?i)err.*|crit.*|fatal|panic|alert|emerg", "red", True),
                color_by("(?i)warn.*", "orange", True), color_by("info", "green"),
                color_by("notice", "purple"), color_by("debug", "blue")]

# ============ 1. Alloy agent 健康 ============
row("Alloy agent 健康")
stat("最後回報", [t(f'time() - max by (host) (timestamp(up{{{UNIX}}}))', "{{host}}")], 0, 4,
     unit="s", decimals=0, color="background", novalue="已斷線 / 無資料",
     thresholds=thr(("green", None), ("orange", 60), ("red", 120)))
stat("設定載入", [t(f'max by (host) (alloy_config_last_load_successful{{{SELF}}})', "{{host}}")], 4, 3,
     color="background", thresholds=thr(("red", None), ("green", 1)),
     mappings=[{"type": "value", "options": {"0": {"text": "失敗", "color": "red"},
                                             "1": {"text": "OK", "color": "green"}}}])
stat("元件狀態", [t(f'sum by (health_type) (alloy_component_controller_running_components{{{SELF}}})',
                   "{{health_type}}")], 7, 4, color="background",
     thresholds=thr(("blue", None)),
     )
panels[-1]["fieldConfig"]["overrides"] = [
    {"matcher": {"id": "byName", "options": "healthy"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
    {"matcher": {"id": "byRegexp", "options": "unhealthy|exited"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
]
stat("Alloy 版本", [t(f'max by (host, version) (alloy_build_info{{{SELF}}})', "{{version}}")], 11, 3,
     text="name", color="none")
stat("已執行", [t(f'time() - max by (host) (alloy_resources_process_start_time_seconds{{{SELF}}})', "{{host}}")],
     14, 3, unit="dtdurations", text="value")
stat("Alloy 記憶體", [t(f'max by (host) (alloy_resources_process_resident_memory_bytes{{{SELF}}})', "{{host}}")],
     17, 3, unit="bytes", graph="area", text="value")
stat("Alloy CPU", [t(f'100 * sum by (host) (rate(alloy_resources_process_cpu_seconds_total{{{SELF}}}[$__rate_interval]))', "{{host}}")],
     20, 4, unit="percent", graph="area", text="value", decimals=1)
y[0] += 4

# ============ 2. 資料管線 ============
row("資料管線（Alloy → Prometheus / Loki）")
ts("指標推送 remote_write (samples/s)", [
    t(f'sum by (host) (rate(prometheus_remote_storage_samples_total{{{SELF}}}[$__rate_interval]))', "{{host}} 已送出", "A"),
    t(f'sum by (host) (rate(prometheus_remote_storage_samples_failed_total{{{SELF}}}[$__rate_interval]))', "{{host}} 失敗", "B"),
    t(f'sum by (host) (rate(prometheus_remote_storage_samples_retried_total{{{SELF}}}[$__rate_interval]))', "{{host}} 重試", "C"),
], 0, 8, unit="short", minv=0,
   overrides=[color_by(".*失敗", "red", True), color_by(".*重試", "orange", True)])
ts("指標推送延遲 / 待送佇列", [
    t(f'max by (host) (prometheus_remote_storage_highest_timestamp_in_seconds{{{SELF}}}) - max by (host) (prometheus_remote_storage_queue_highest_sent_timestamp_seconds{{{SELF}}})', "{{host}} 延遲 (s)", "A"),
    t(f'sum by (host) (prometheus_remote_storage_samples_pending{{{SELF}}})', "{{host}} 待送 samples", "B"),
], 8, 8, minv=0)
panels[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byRegexp", "options": ".*延遲.*"},
                                           "properties": [{"id": "unit", "value": "s"}]},
                                          {"matcher": {"id": "byRegexp", "options": ".*待送.*"},
                                           "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]
ts("Log 推送 (entries/s)", [
    t(f'sum by (host) (rate(loki_write_sent_entries_total{{{SELF}}}[$__rate_interval]))', "{{host}} 已送出", "A"),
    t(f'sum by (host) (rate(loki_write_dropped_entries_total{{{SELF}}}[$__rate_interval]))', "{{host}} 丟棄", "B"),
    t(f'sum by (host) (rate(loki_write_batch_retries_total{{{SELF}}}[$__rate_interval]))', "{{host}} 重試", "C"),
], 16, 8, minv=0, overrides=[color_by(".*丟棄", "red", True), color_by(".*重試", "orange", True)])
y[0] += 8
ts("Log 來源 (lines/s)", [
    t(f'sum by (host) (rate(loki_source_docker_target_entries_total{{{SELF}}}[$__rate_interval]))', "{{host}} docker 容器", "A"),
    t(f'sum by (host) (rate(loki_source_journal_target_lines_total{{{SELF}}}[$__rate_interval]))', "{{host}} journal", "B"),
], 0, 12, h=7, minv=0)
ts("各 exporter scrape 狀態 (1=UP)", [
    t(f'max by (host, job) (up{{job=~"integrations/.*", {H}}})', "{{host}} {{job}}"),
], 12, 12, h=7, minv=0)
panels[-1]["fieldConfig"]["defaults"]["max"] = 1.2
y[0] += 7

# ============ 3. 宿主機 ============
row("宿主機狀態（內建 node-exporter：prometheus.exporter.unix）")
CPU = (f'100 * (1 - sum by (host) (rate(node_cpu_seconds_total{{mode="idle", {UNIX}}}[$__rate_interval]))'
       f' / sum by (host) (rate(node_cpu_seconds_total{{{UNIX}}}[$__rate_interval])))')
MEM = f'100 * (1 - node_memory_MemAvailable_bytes{{{UNIX}}} / node_memory_MemTotal_bytes{{{UNIX}}})'
DISK = (f'100 * (1 - node_filesystem_avail_bytes{{mountpoint="/", {UNIX}}}'
        f' / node_filesystem_size_bytes{{mountpoint="/", {UNIX}}})')
pct = thr(("green", None), ("orange", 75), ("red", 90))
stat("CPU", [t(CPU, "{{host}}")], 0, 4, unit="percent", decimals=1, color="background", graph="area", thresholds=pct)
stat("記憶體", [t(MEM, "{{host}}")], 4, 4, unit="percent", decimals=1, color="background", graph="area", thresholds=pct)
stat("根目錄磁碟", [t(DISK, "{{host}}")], 8, 4, unit="percent", decimals=1, color="background", thresholds=pct)
stat("CPU 核數", [t(f'count by (host) (node_cpu_seconds_total{{mode="idle", {UNIX}}})', "{{host}}")], 12, 3)
stat("記憶體總量", [t(f'node_memory_MemTotal_bytes{{{UNIX}}}', "{{host}}")], 15, 3, unit="bytes")
stat("Load 1m", [t(f'node_load1{{{UNIX}}}', "{{host}}")], 18, 3, decimals=2, graph="area")
stat("執行中容器", [t(f'count by (host) (container_memory_working_set_bytes{{name!="", {CAD}}})', "{{host}}")], 21, 3)
y[0] += 4
ts("CPU / 記憶體 %", [t(CPU, "{{host}} CPU", "A"), t(MEM, "{{host}} 記憶體", "B")], 0, 8, unit="percent", minv=0)
# 實體機網卡名稱不固定 (eno1 / enp3s0 / eth0…)，改成排除虛擬網卡
NIC = 'device!~"lo|veth.*|docker.*|br-.*|virbr.*|cali.*|flannel.*|cni.*|tun.*|tap.*|wg.*|tailscale.*"'
ts("網路流量 (實體網卡)", [
    t(f'rate(node_network_receive_bytes_total{{{NIC}, {UNIX}}}[$__rate_interval])', "{{host}} {{device}} rx", "A"),
    t(f'-rate(node_network_transmit_bytes_total{{{NIC}, {UNIX}}}[$__rate_interval])', "{{host}} {{device}} tx", "B"),
], 8, 8, unit="Bps")
ts("Load average", [
    t(f'node_load1{{{UNIX}}}', "{{host}} 1m", "A"),
    t(f'node_load5{{{UNIX}}}', "{{host}} 5m", "B"),
    t(f'node_load15{{{UNIX}}}', "{{host}} 15m", "C"),
], 16, 8, minv=0)
y[0] += 8

# ============ 4. 容器 ============
row("各容器狀態（內建 cAdvisor：prometheus.exporter.cadvisor）")
CF = f'name=~"$container", {CAD}'
ts("容器 CPU (% of 1 core)", [
    t(f'100 * sum by (name) (rate(container_cpu_usage_seconds_total{{{CF}}}[$__rate_interval]))', "{{name}}")],
   0, 12, h=9, unit="percent", minv=0, legend="table", place="right", calcs=["mean", "max"])
ts("容器記憶體 (working set)", [
    t(f'sum by (name) (container_memory_working_set_bytes{{{CF}}})', "{{name}}")],
   12, 12, h=9, unit="bytes", minv=0, legend="table", place="right", calcs=["lastNotNull", "max"])
y[0] += 9
panels.append({
    "id": nid(), "type": "table", "title": "容器清單", "datasource": P,
    "gridPos": {"h": 8, "w": 24, "x": 0, "y": y[0]},
    "targets": [
        t(f'time() - max by (name, image) (container_start_time_seconds{{{CF}}})', "", "UP", format="table", instant=True),
        t(f'sum by (name) (container_memory_working_set_bytes{{{CF}}})', "", "MEM", format="table", instant=True),
        t(f'100 * sum by (name) (rate(container_cpu_usage_seconds_total{{{CF}}}[5m]))', "", "CPU", format="table", instant=True),
        t(f'sum by (name) (rate(container_network_receive_bytes_total{{{CF}}}[5m]))', "", "RX", format="table", instant=True),
        t(f'sum by (name) (rate(container_network_transmit_bytes_total{{{CF}}}[5m]))', "", "TX", format="table", instant=True),
    ],
    "transformations": [
        {"id": "merge", "options": {}},
        {"id": "organize", "options": {"excludeByName": {"Time": True},
                                       "renameByName": {"name": "容器", "image": "Image", "Value #UP": "已執行",
                                                        "Value #MEM": "記憶體", "Value #CPU": "CPU %",
                                                        "Value #RX": "網路 rx", "Value #TX": "網路 tx"}}},
    ],
    "fieldConfig": {"defaults": {}, "overrides": [
        {"matcher": {"id": "byName", "options": "已執行"}, "properties": [{"id": "unit", "value": "dtdurations"}]},
        {"matcher": {"id": "byName", "options": "記憶體"}, "properties": [{"id": "unit", "value": "bytes"}]},
        {"matcher": {"id": "byName", "options": "CPU %"}, "properties": [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 2}]},
        {"matcher": {"id": "byRegexp", "options": "網路.*"}, "properties": [{"id": "unit", "value": "Bps"}]},
    ]},
    "options": {"showHeader": True, "sortBy": [{"displayName": "記憶體", "desc": True}]},
})
y[0] += 8

# ============ 5. 容器 logs ============
row("容器 Logs（loki.source.docker）")
LQ = f'job="docker", {H}, container=~"$container"'
ts("容器 log 量 (依 level)", [
    t(f'sum by (level) (count_over_time({{{LQ}}} |~ "$search" [$__interval]))', "{{level}}")],
   0, 12, h=7, ds=L, bars=True, stack=True, overrides=LEVEL_COLORS)
ts("容器 log 量 (依容器)", [
    t(f'sum by (container) (count_over_time({{{LQ}}} |~ "$search" [$__interval]))', "{{container}}")],
   12, 12, h=7, ds=L, bars=True, stack=True)
y[0] += 7
panels.append({"id": nid(), "type": "logs", "title": "容器 Logs", "datasource": L,
               "gridPos": {"h": 14, "w": 24, "x": 0, "y": y[0]},
               "targets": [t(f'{{{LQ}}} |~ "$search"')],
               "options": {"showTime": True, "showLabels": False, "wrapLogMessage": True,
                           "enableLogDetails": True, "sortOrder": "Descending", "dedupStrategy": "none"}})
y[0] += 14

# ============ 6. 系統 logs ============
row("系統 Logs（loki.source.journal）")
JQ = f'job="journal", {H}, unit=~"$unit"'
ts("journal log 量 (依 unit)", [
    t(f'sum by (unit) (count_over_time({{{JQ}}} |~ "$search" [$__interval]))', "{{unit}}")],
   0, 12, h=7, ds=L, bars=True, stack=True, legend="list", place="right")
ts("journal log 量 (依 level)", [
    t(f'sum by (level) (count_over_time({{{JQ}}} |~ "$search" [$__interval]))', "{{level}}")],
   12, 12, h=7, ds=L, bars=True, stack=True, overrides=LEVEL_COLORS)
y[0] += 7
panels.append({"id": nid(), "type": "logs", "title": "Journal Logs", "datasource": L,
               "gridPos": {"h": 14, "w": 24, "x": 0, "y": y[0]},
               "targets": [t(f'{{{JQ}}} |~ "$search"')],
               "options": {"showTime": True, "showLabels": True, "wrapLogMessage": True,
                           "enableLogDetails": True, "sortOrder": "Descending", "dedupStrategy": "none"}})


def qvar(name, label, query, ds=P):
    return {"name": name, "label": label, "type": "query", "datasource": ds,
            "query": {"query": query, "refId": name} if ds is P else
                     {"type": 1, "label": "unit", "stream": '{job="journal", host=~"$host"}', "refId": name},
            "definition": query, "refresh": 2, "multi": True, "includeAll": True,
            "allValue": ".*", "sort": 1, "current": {"text": "All", "value": "$__all"}}


dash = {
    "uid": "alloy-allinone",
    "title": "Alloy All-in-One",
    "description": "單一 Alloy 收集指標 (unix + cadvisor exporter, remote_write) 與 log (docker + journal) 的主機",
    "tags": ["monitoring", "alloy", "all-in-one"],
    "timezone": "browser", "refresh": "30s", "schemaVersion": 39, "editable": True,
    "time": {"from": "now-1h", "to": "now"},
    "templating": {"list": [
        dict(qvar("host", "宿主機", 'label_values(up{job="integrations/unix"}, host)'), allValue=".+"),
        dict(qvar("container", "容器", 'label_values(container_memory_working_set_bytes{job="integrations/cadvisor", host=~"$host", name!=""}, name)'), allValue=".+"),
        qvar("unit", "systemd unit", "label_values(unit)", ds=L),
        {"name": "search", "label": "Log 搜尋 (regex)", "type": "textbox", "query": "",
         "current": {"text": "", "value": ""}},
    ]},
    "panels": panels,
}
json.dump(dash, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(panels), "panels")
