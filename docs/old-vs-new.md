# 舊方案 vs 新方案

- **舊方案**：Loki Docker logging driver（每台主機裝 Docker plugin，每個 compose 的 service 加 `logging: driver: loki`）
- **新方案**：Grafana Alloy all-in-one（本 repo：每台主機一個 Alloy 容器）

## 比較表

| 項目 | 舊：Loki Docker logging driver | 新：Alloy all-in-one |
|---|---|---|
| **運作方式** | dockerd 透過 plugin 把容器 log 直接推給 Loki | 獨立的 Alloy 容器透過 docker.sock 找到容器、讀 log 再推給 Loki |
| **收得到什麼** | 只有容器 stdout/stderr | 容器 log ＋ 系統 log（journald）＋ 宿主機指標（內建 node-exporter）＋ 容器指標（內建 cAdvisor） |
| **主機 / 容器狀態** | 不包含，要另外裝 node-exporter、cAdvisor，並在 Prometheus 列出每台 IP | 內建，推送到 Prometheus，Prometheus 不用知道主機 IP |
| **主機上要裝什麼** | `docker plugin install ... --grant-all-permissions`（直接裝進 dockerd） | 一份 `docker compose`（一個容器） |
| **應用程式的 compose** | **每個 service 都要加** `logging:` 區塊（或在 daemon.json 設成整台預設） | **不用改**，新容器自動被收 |
| **Loki 位址寫在哪** | 散在每個 compose（或 daemon.json） | 只在 Alloy 的 `.env` 一處 |
| **忘了設定的容器** | 沒加 `logging:` 就收不到 log | 不會發生，全部自動收 |
| **Loki 掛掉 / 連不到時** | log 卡在 dockerd 那層，可能拖慢容器啟動或停止；要調 `mode`、`max-buffer-size`、`loki-retries` 等參數 | 只影響 Alloy；應用容器不受影響，log 留在本機 json 檔，恢復後從記錄的位置繼續送 |
| **`docker logs` 指令** | 依賴 Docker 的 dual logging 快取 | 正常（容器用預設 json-file） |
| **Log 標籤（label）** | plugin 內建的固定幾個（container_name、compose_project、compose_service、host 等） | 自訂：host、container、compose_project、compose_service、stream、**level（已正規化）** |
| **Log 加工** | 有限（`loki-pipeline-stages`） | 完整的處理流程（抽 level、改格式、過濾、丟棄雜訊等） |
| **升級 / 移除** | plugin 綁在 dockerd 上：要先停掉所有用它的容器才能 disable / 升級 | 改映像版本號，`docker compose up -d` |
| **收集端壞了看得出來嗎** | 不容易，plugin 本身沒有健康狀態指標 | 有：dashboard 上的「最後回報」、元件健康、送出/失敗/丟棄數量；Alloy UI（:12345）可看每個元件 |
| **新增一台主機** | 裝 plugin → 改該台所有 compose → 另外處理指標 → 改 Prometheus 設定 | 複製 `docker-host/`、改 `.env`、`docker compose up -d`，監控中心不用動 |
| **資源用量** | 在 dockerd 內，幾乎沒有額外容器 | 每台一個 Alloy，約 100–140 MB 記憶體 |
| **權限** | plugin 要求 all permissions | Alloy 容器要 privileged、pid/network host、docker.sock（為了收主機和容器指標） |
| **官方方向** | 還能用，但不是 Grafana 主推的路線 | Grafana 目前主推的收集器（Promtail 已 EOL，新文件、新功能都以 Alloy 為主） |
| **適合** | 只要容器 log、主機很少、不想多跑一個容器 | 要 log ＋ 指標一起看、主機會增加、希望應用 compose 不用動 |

## 一句話結論

舊方案只管「容器 log」，而且設定散在每個應用的 compose 裡；新方案一個 agent 收齊 log 和指標，應用完全不用改。既然整套要重做，就改用新方案。

## 從舊方案換過來要注意

既有應用的 compose 裡如果還留著 `logging: driver: loki`，要照這個順序處理：

1. 找出還在用 loki driver 的容器：
   ```bash
   docker ps -aq | xargs docker inspect -f '{{.Name}} {{.HostConfig.LogConfig.Type}}' | grep loki
   ```
2. 從各應用的 compose **刪掉 `logging:` 區塊**；若 `/etc/docker/daemon.json` 有 `"log-driver": "loki"` 也一併改掉（參考本 repo 的 `docker-host/daemon.json`，改完 `systemctl restart docker`）。
3. 各應用 `docker compose up -d`，讓容器用新的 log driver 重建。
4. 再跑一次第 1 步，確認沒有容器還在用 loki driver。
5. 移除 plugin：
   ```bash
   docker plugin disable loki
   docker plugin rm loki
   ```
6. 照 README 部署 `docker-host/`。

> 順序不能反過來：還有容器在用時，plugin 移不掉；強制移除的話，那些容器下次啟動會因為找不到 log driver 而失敗。
> 還在用 loki driver 的容器，Alloy 收不到它的 log（log 直接被 plugin 送走了，不會寫到本機）。
