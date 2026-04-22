# simulation
Konteyner telemetri simülasyonu (IoT yerine).

Bu repo, backend’e **telemetry/ingest** endpoint’i üzerinden batch telemetri gönderen
demo odaklı bir simülasyon içerir. Amaç: uçtan uca demo senaryosunu güvenilir çalıştırmak.

---

## Hızlı Başlangıç için 

### 1) Kurulum
Python 3.10+ önerilir.

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

> Bu proje sadece standart kütüphaneleri kullanır, ek paket gerekmez.

### 2) Tek seferlik demo gönderimi

```bash
python simulate.py --once
```

### 3) Sürekli akış (2 sn tick)

```bash
python simulate.py --tick-seconds 2
```

Varsayılan hedef:
- Base URL: `http://localhost:8080`
- Endpoint: `/telemetry/ingest`

---

## Senaryolars

### A) backend-seed (varsayılan)
Backend’in **in-memory seed** verisiyle uyumludur.

```bash
python simulate.py --scenario backend-seed
```

### B) demo (5 atık türü)
Gerçek demo senaryosu için hazırlanmış tam 5 tür seti içerir.

```bash
python simulate.py --scenario demo --containers-file data/containers_demo.json
```

> Not: backend tarafında bu container ID’leri yoksa ingest 404 döner.
> Bu senaryoyu kullanmadan önce backend/DB’de aynı container kayıtları olmalıdır.

---

## Konfigürasyon (CLI + Env)

| Ayar | Env | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `--api-base-url` | `SIM_API_BASE_URL` | `http://localhost:8080` | Backend base URL |
| `--telemetry-path` | `SIM_TELEMETRY_PATH` | `/telemetry/ingest` | Telemetry endpoint |
| `--scenario` | `SIM_SCENARIO` | `backend-seed` | `backend-seed` veya `demo` |
| `--containers-file` | `SIM_CONTAINERS_FILE` | (senaryo bazlı) | Container set JSON |
| `--tick-seconds` | `SIM_TICK_SECONDS` | `2` | Tick aralığı (sn) |
| `--batch-size` | `SIM_BATCH_SIZE` | `10` | Batch başına item |
| `--seed` | `SIM_SEED` | `20260325` | Deterministik RNG |
| `--min-increment` | `SIM_MIN_INCREMENT` | `0.5` | Doluluk artışı min |
| `--max-increment` | `SIM_MAX_INCREMENT` | `5.0` | Doluluk artışı max |
| `--max-retries` | `SIM_MAX_RETRIES` | `5` | Retry sayısı |
| `--backoff-base` | `SIM_BACKOFF_BASE` | `1.0` | Backoff başlangıcı (sn) |
| `--backoff-max` | `SIM_BACKOFF_MAX` | `30.0` | Backoff üst sınır (sn) |
| `--timeout-seconds` | `SIM_TIMEOUT_SECONDS` | `10` | HTTP timeout |
| `--dry-run` | `SIM_DRY_RUN` | `false` | HTTP gönderme, sadece log |
| `--save-batches` | `SIM_SAVE_BATCHES` | `false` | Batch payload dosyaya yaz |

---

## Container dosya formatı

### A) Generator formatı (önerilen)

Bu format, **Kahramanmaras** için 5 türde 250’şer konteyneri **deterministik** üretir.

```json
{
  "name": "kahramanmaras-demo",
  "description": "Kahramanmaras sehir ici demo veri seti",
  "generator": {
    "city": "Kahramanmaras",
    "types": ["CAM", "PLASTIK", "KAGIT", "IKINCI_EL_ESYA", "METAL"],
    "countPerType": 250,
    "idBaseByType": {
      "CAM": 10000,
      "PLASTIK": 20000,
      "KAGIT": 30000,
      "IKINCI_EL_ESYA": 40000,
      "METAL": 50000
    },
    "latRange": [37.45, 37.70],
    "lngRange": [36.80, 37.10],
    "grid": { "rows": 25, "cols": 10 },
    "typeOffset": 0.0002,
    "fillPercent": { "min": 60, "max": 95 }
  }
}
```

### B) Sabit liste formatı

```json
{
  "name": "backend-seed",
  "description": "Backend Seed Data ile uyumlu container seti",
  "containers": [
    {
      "id": 1,
      "wasteType": "CAM",
      "lat": 41.015,
      "lng": 28.984,
      "fillPercent": 78
    }
  ]
}
```

---

## Telemetry payload örneği

```json
{
  "items": [
    {
      "containerId": 1,
      "fillPercent": 78.5,
      "lat": 41.015,
      "lng": 28.984,
      "recordedAt": "2026-03-25T10:00:00Z"
    }
  ]
}
```

---

## Sık karşılaşılan hatalar

- **404 Container bulunamadı** → Container ID backend’de yok.
- **400 Validation hatası** → `fillPercent` 0–100 dışında veya `recordedAt` boş.
- **Network timeout** → backend kapalı veya URL yanlış.

---

## Önerilen demo akışı

1) Backend’i çalıştır  
2) `python simulate.py --scenario backend-seed --once`  
3) `/routes/generate` ile rota üret  
4) Mobilde `/routes/active` ile rota doğrula  
5) Bir durak için collection kaydı gönder
