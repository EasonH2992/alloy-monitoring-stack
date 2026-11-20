# demo（選用）

一組**假的服務**，唯一的用途是讓 dashboard 上有東西可以看，用來確認監控整條路是通的。
跟監控本身無關，**不裝也完全不影響** `monitoring-server/` 和 `docker-host/`。

## 四個容器在做什麼

| 容器 | 映像 | 做什麼 | 在 Grafana 上看得到 |
|---|---|---|---|
| `demo-web` | nginx | 一般網頁伺服器，對外開 `DEMO_WEB_PORT`（預設 **8088**） | 大量 access log；`/notfound`、`/api/users` 不存在 → 404 與 nginx 的 `[error]` log；容器網路流量 |
| `demo-traffic` | curl | 每 2 秒對 `demo-web` 打 5 個網址，製造流量 | **沒有 log**（curl 是靜音模式），只看得到 CPU / 網路；用來驗證「沒 log 的容器也會出現在容器指標」 |
| `demo-app` | busybox | 假的應用程式，每秒印一行 `level=... msg=...` | 各種 level 的 log：info 約 60%、debug 20%、warn 10%、**error 10%（寫到 stderr）** → 測試 level 篩選、`stream="stderr"`、log 量圖的顏色 |
| `demo-redis` | redis | 一個正常跑但很安靜的資料庫 | 只有啟動時幾行 log（含 `WARNING`）；記憶體用量；代表「平常沒什麼 log 的服務」 |

```
demo-traffic ──HTTP──► demo-web (nginx)      ← access log / 404 / 網路流量
demo-app                                       ← info / debug / warn / error log
demo-redis                                     ← 安靜的服務
```

四個加起來約 20MB 記憶體，CPU 幾乎是 0。

## 用法

裝在任一台已經跑 `docker-host/` 的機器上：

```bash
cd /opt/monitoring/demo
# 選用：改 port（預設 8088）
echo "DEMO_WEB_PORT=8088" > .env
docker compose up -d
```

約 10–30 秒後在 Grafana「Alloy All-in-One」：
- **容器**選單出現 `demo-web`、`demo-app`、`demo-redis`、`demo-traffic`
- **容器 Logs** 區塊：log 量圖出現紅（error）/ 橙（warn）/ 綠（info）/ 藍（debug）
- Explore → Loki 試試：
  ```logql
  {container="demo-app", level="error"}
  {container="demo-web"} |= "404"
  {container="demo-app", stream="stderr"}
  ```

## 移除

```bash
cd /opt/monitoring/demo && docker compose down
```

拿掉之後，Loki 裡已收到的 log 會照保留期限（預設 7 天）自然過期，Prometheus 的指標約 5 分鐘後從圖上消失。
