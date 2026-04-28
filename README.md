# simulation
Konteyner telemetri simülasyonu (IoT yerine).

Bu repo, backend’e **telemetry/ingest** endpoint’i üzerinden batch telemetri gönderen
demo odaklı bir simülasyon içerir. Amaç: uçtan uca demo senaryosunu güvenilir çalıştırmak.

---

## Hızlı Başlangıç

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

## Senaryolar

### A) backend-seed (varsayılan, ÖNERİLEN)

`Backend-DB/database/atik_yonetimi.sql` içindeki gerçek **75 konteyner** seed
verisiyle **birebir** uyumludur (id, wasteType, lat, lng). Konteynerler
Kahramanmaraş Sütçü İmam Üniversitesi çevresindedir (lat ≈ 37.585–37.590,
lng ≈ 36.808–36.832).

```bash
python simulate.py --scenario backend-seed --once
```

Veri dosyası: `data/containers_backend_seed.json` (fixed-list formatı,
`source: Backend-DB/database/atik_yonetimi.sql`).

DB seed dosyası güncellenirse JSON'u şu komutla yeniden üretebilirsin
(yalnızca `Backend-DB` repo'su simulation ile aynı üst klasörde
klonlanmışsa):

```bash
python data/_build_seed_from_db.py
```

### B) demo (sentetik 1250 konteyner — ⚠️ DB ile UYUMSUZ)

Bu dosya jenerik bir generator çıktısıdır (ID aralıkları 10001–50250).
**Backend DB seed'i ile uyumsuzdur**, ingest 404 döner. Kullanılmak
isteniyorsa öncesinde DB'ye aynı 1250 konteynerin INSERT edilmesi gerekir.
Demo / sunum amaçlı **kullanmayın**, `backend-seed` senaryosunu tercih edin.

```bash
# Sadece DB'de uygun seed varsa:
python simulate.py --scenario demo --containers-file data/containers_demo.json
```

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

`simulate.py` iki farklı format destekler. Demo için **B) Sabit liste**
formatı kullanılır (DB seed ile birebir eşleştirmek icin); generator
formatı yalnızca kullanılabilir bir referans olarak korunmuştur.

### A) Generator formatı (sentetik veri üretmek için)

Bu format, **Kahramanmaras** için 5 türde 250’şer konteyneri **deterministik** üretir.
DB seed verisiyle uyumlu DEĞİLDİR; sadece backend'in ağ/yük testleri gibi
senaryolar için faydalıdır.

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

### B) Sabit liste formatı (varsayılan, DB-uyumlu)

`data/containers_backend_seed.json` bu formattadır. ID/lat/lng değerleri
`Backend-DB/database/atik_yonetimi.sql` içindeki `containers` tablosundan
birebir kopyalanmıştır. DB güncellenirse `data/_build_seed_from_db.py`
ile yeniden üretilir.

```json
{
  "name": "backend-seed",
  "description": "Backend Seed Data ile uyumlu container seti",
  "source": "Backend-DB/database/atik_yonetimi.sql",
  "containers": [
    {
      "id": 1,
      "wasteType": "CAM",
      "lat": 37.58771,
      "lng": 36.832294,
      "fillPercent": 67.0
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

1) PostgreSQL ayağa kalkmış ve `Backend-DB/database/atik_yonetimi.sql` ile
   seed edilmiş olmalı (75 konteyner, 5 araç, 5 sürücü)
2) `Backend-DB/waste-management` Spring Boot uygulamasını başlat
   (varsayılan: `http://localhost:8080`)
3) Simülasyonu **backend-seed** senaryosu ile çalıştır:
   `python simulate.py --scenario backend-seed --once`  
   → Backend `/telemetry/ingest` 200 dönmelidir; 404 döndüğü an
   `data/containers_backend_seed.json` ile DB seed eşleşmiyor demektir
   (`data/_build_seed_from_db.py` ile yeniden üret).
4) `/routes/generate` ile rota üret  
4) Mobilde `/routes/active` ile rota doğrula  
5) Bir durak için collection kaydı gönder
