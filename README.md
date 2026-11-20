# Docker 主機監控：Grafana + Loki + Prometheus + Alloy all-in-one

兩種角色，各自一個資料夾：

| 資料夾 | 裝在哪 | 內容 |
|---|---|---|
| `monitoring-server/` | **監控中心**（一台） | Grafana、Loki、Prometheus |
| `docker-host/` | **每台被監控的 docker 主機** | 一個 Alloy（宿主機指標 + 容器指標 + 容器 log + 系統 log） |
| `demo/`（選用） | 任一台 docker 主機 | 4 個假服務，讓 dashboard 有資料可看、驗證監控是通的；說明見 [demo/README.md](demo/README.md) |

```
   docker 主機 A ─ Alloy ─┐
   docker 主機 B ─ Alloy ─┼── 指標 → Prometheus :9090/api/v1/write ─┐
   （監控中心自己）Alloy ─┘   log  → Loki       :3100/loki/api/v1/push ┤
                                                                      └─ Grafana :3000
```

> 監控中心本身通常也跑 docker，建議**也裝一份 `docker-host/`**，這樣監控中心自己壞了也看得到前兆。
> 兩台機器的話就是：機器 1 = `monitoring-server/` + `docker-host/`，機器 2 = `docker-host/`。

---

## 事前檢查（兩台都要）

1. 裝好 Docker 與 docker compose plugin。
2. **Docker 29 以上**：預設改用 containerd image store，內建 cAdvisor 會抓不到容器名稱。
   把 `docker-host/daemon.json` 放到 `/etc/docker/daemon.json`，然後 `systemctl restart docker`。
   - ⚠️ 切換 storage 後，**現有的映像和容器會「看不見」**（它們在另一個 store 裡），要重新 `docker compose pull && docker compose up -d`。
     在已經有服務在跑的機器上，請排在維護時段做。
   - Docker 28 以下、`docker info` 顯示 `Storage Driver: overlay2` 的機器，這步可以略過，但 log 輪替設定（max-size）仍建議加上。
   - 若 `/etc/docker/daemon.json` 已經有內容，用合併的方式加上去，不要直接覆蓋。
3. 防火牆：監控中心要開放 docker 主機連入 **3100**（Loki）、**9090**（Prometheus），使用者連入 **3000**（Grafana）。docker 主機不需要開放任何 port（push 模式）。


### Ubuntu 實體機要多注意的

這份包在 LXC 和實體機都適用，設定不用改，但實體機多檢查這幾點：

1. **Docker 是不是 snap 裝的**：`snap list docker` 有東西的話，資料目錄不在 `/var/lib/docker`，cAdvisor 會抓不到容器。
   用 `docker info --format '{{.DockerRootDir}}'` 確認是 `/var/lib/docker`；不是的話建議改用官方 apt 版（docker-ce），或把 `docker-host/docker-compose.yml` 裡 `/var/lib/docker` 的掛載改成實際路徑。
2. **ufw 擋不住 docker 開的 port**：Docker 直接改 iptables，`ports:` 開出來的 3000 / 3100 / 9090 會**繞過 ufw**，ufw 顯示 deny 也照樣連得到。
   要限制來源，可以二選一：
   - compose 裡綁定內網 IP：`"10.0.0.5:3100:3100"`（只聽那張網卡）
   - 用 `DOCKER-USER` chain，例如只允許 10.0.0.0/24 連 Loki / Prometheus：
     ```bash
     iptables -I DOCKER-USER -p tcp -m multiport --dports 3100,9090 ! -s 10.0.0.0/24 -j DROP
     ```
     （重開機會消失，要用 iptables-persistent 等方式保存）
3. **時間同步**：Loki 會拒收時間差太多的 log。兩台都確認 `timedatectl` 顯示 `System clock synchronized: yes`。
4. **網卡名稱**：實體機通常是 `eno1` / `enp3s0`，dashboard 的「網路流量」已改成自動排除 lo、veth、docker、bridge 等虛擬網卡，不用改。
5. **實體機看得到更多**：多顆磁碟、磁碟 IO、溫度（hwmon）等；想看完整細節可以匯入 Node Exporter Full（grafana.com 1860）。LXC 才有的 `disabling udev` 警告在實體機不會出現。

---

## 機器 1：監控中心

```bash
# 把 monitoring-server/ 複製到例如 /opt/monitoring/monitoring-server
cd /opt/monitoring/monitoring-server
cp .env.example .env
vi .env                       # 設定 GRAFANA_ADMIN_PASSWORD
docker compose up -d
docker compose ps             # 三個都 Up
curl -s localhost:3100/ready  # Loki 顯示 ready
```

Grafana：`http://<監控中心IP>:3000`，帳號 `admin`。首頁就是「Alloy All-in-One」dashboard（在 Monitoring 資料夾）。

## 機器 2（以及監控中心自己）：docker 主機

```bash
# 把 docker-host/ 複製到例如 /opt/monitoring/docker-host
cd /opt/monitoring/docker-host
cp .env.example .env
vi .env                       # HOST_NAME 每台不同；MONITOR_IP 換成監控中心 IP
mkdir -p /var/log/journal /run/log/journal   # 沒有的話先建，避免掛載失敗
docker compose up -d
docker logs --tail 20 alloy   # 不應有持續出現的 level=error
```

在監控中心那台上，`.env` 的 `MONITOR_IP` 也可以填 `127.0.0.1`。

### 驗證

- 開 `http://<docker主機IP>:12345`：Alloy UI，所有元件應為綠色 healthy。
- Grafana「Alloy All-in-One」上方「宿主機」選單出現該台的 `HOST_NAME`，「最後回報」在 30 秒內。
- Grafana → Explore → Loki：`{host="<HOST_NAME>", job="docker"}` 有容器 log，`{host="<HOST_NAME>", job="journal"}` 有系統 log。

新增主機：重複「docker 主機」步驟即可，監控中心**不用改任何設定**。

想先看到 dashboard 有東西：在任一台 docker 主機裝 `demo/`（選用，見 [demo/README.md](demo/README.md)），驗證完 `docker compose down` 即可移除。

---

## 上線前建議再補

這份包預設適合內網、小規模。正式環境依需求調整：

- **認證**：Loki、Prometheus 目前沒有驗證，任何連得到 3100/9090 的人都能寫入和查詢。至少用防火牆限制來源網段，或前面加 reverse proxy（nginx/Caddy）做 basic auth / mTLS；Alloy 的 `loki.write` 和 `prometheus.remote_write` 都支援 `basic_auth { }`。
- **儲存與保留**：Loki 用本機檔案系統，保留 7 天（`loki/loki.yml`）；Prometheus 保留 15 天（`.env`）。log 量大或要保留較久時，考慮把 Loki 換成 S3 / MinIO。磁碟用量要監控。
- **告警**：push 模式下主機斷線時 `up` 不會變 0，而是沒資料。斷線告警用：
  ```promql
  absent_over_time(up{job="integrations/unix", host="app-server-01"}[5m])
  ```
  或對所有主機：`time() - max by (host) (timestamp(up{job="integrations/unix"})) > 120`（注意斷線超過 5 分鐘後 series 會消失，用前者較可靠）。
- **版本**：映像版本都已固定，不用 `latest`（避免兩台裝到不同版本、或在不知情下跳大版本）。目前版本（2026-11 驗證過）：

  | 元件 | 映像 |
  |---|---|
  | Prometheus | `prom/prometheus:v3.16.0` |
  | Loki | `grafana/loki:3.7.10` |
  | Grafana | `grafana/grafana:13.3.1` |
  | Alloy | `grafana/alloy:v1.22.0` |

  升級流程：改 compose 的版本號 → 先在測試環境 `docker compose pull && docker compose up -d` → 看 log 有沒有 error / deprecated、dashboard 是否正常 → 再套到正式環境。
  Grafana 跨大版本會遷移內部資料庫、**無法降版**，升級前先備份 `grafana-data` volume。
- **Grafana 資料**：dashboard 由檔案 provision，UI 上改的會存在 grafana-data volume；要永久保留請匯出 JSON 放回 `grafana/dashboards/`。

## 修改 dashboard

`monitoring-server/grafana/gen_alloy_allinone_dashboard.py` 產生 `grafana/dashboards/alloy-allinone.json`：

```bash
python grafana/gen_alloy_allinone_dashboard.py grafana/dashboards/alloy-allinone.json
```

Grafana 約 10 秒內自動重新載入。也可以另外匯入社群 dashboard，例如 Node Exporter Full（grafana.com ID 1860），選 Prometheus datasource 即可（job 選 `integrations/unix`）。

## 疑難排解

| 現象 | 原因 / 處理 |
|---|---|
| 容器 CPU/記憶體圖沒有容器名稱，cAdvisor log 有 `failed to identify the read-write layer ID` | Docker 29 containerd snapshotter，見「事前檢查 2」 |
| Alloy log 有 `remote_write ... 404` | Prometheus 沒加 `--web.enable-remote-write-receiver` |
| Alloy log 有 `connection refused` 到 3100/9090 | 防火牆或 `.env` 的 MONITOR_IP 錯 |
| 記憶體/CPU 數字跟主機不符 | `config.alloy` 的 `procfs_path` 要指向 `/host/proc`（已設定），且 compose 要有 `pid: host` |
| 啟動時 `disabling udev`、`OOM detection` 警告 | LXC 環境限制，可忽略（實體機一般不會出現） |
| 容器 CPU/記憶體圖完全沒有容器 | Docker 是 snap 版或資料目錄不在 `/var/lib/docker`，見「實體機要多注意的 1」 |
| 宿主機選單沒有某台 | 看該台 `docker logs alloy`；確認 `.env` 的 HOST_NAME、PROM_URL |
