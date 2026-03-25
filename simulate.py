import argparse
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class Container:
    id: int
    waste_type: str
    lat: float
    lng: float
    fill_percent: float


@dataclass
class Config:
    api_base_url: str
    telemetry_path: str
    scenario: str
    containers_file: str
    tick_seconds: float
    batch_size: int
    seed: int
    min_increment: float
    max_increment: float
    max_retries: int
    backoff_base: float
    backoff_max: float
    timeout_seconds: float
    dry_run: bool
    save_batches: bool
    log_dir: str
    duration_seconds: float
    once: bool


RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


def env_or_default(name: str, default: str) -> str:
    return os.getenv(name, default)


def env_or_default_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y"}


def env_or_default_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    return int(val)


def env_or_default_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None:
        return default
    return float(val)


def setup_logger(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("simulation")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(os.path.join(log_dir, "simulation.log"), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def generate_containers_from_spec(spec: Dict) -> List[Container]:
    types = spec.get("types", [])
    if not types:
        raise ValueError("Generator 'types' bos olamaz.")

    count_per_type = int(spec.get("countPerType", 0))
    if count_per_type <= 0:
        raise ValueError("Generator 'countPerType' gecersiz.")

    grid = spec.get("grid", {})
    rows = int(grid.get("rows", count_per_type))
    cols = int(grid.get("cols", 1))
    if rows * cols != count_per_type:
        raise ValueError("Grid rows*cols, countPerType ile eslesmeli.")

    lat_range = spec.get("latRange", [])
    lng_range = spec.get("lngRange", [])
    if len(lat_range) != 2 or len(lng_range) != 2:
        raise ValueError("Generator latRange/lngRange format hatasi.")

    lat_min, lat_max = float(lat_range[0]), float(lat_range[1])
    lng_min, lng_max = float(lng_range[0]), float(lng_range[1])
    lat_step = (lat_max - lat_min) / (rows - 1) if rows > 1 else 0.0
    lng_step = (lng_max - lng_min) / (cols - 1) if cols > 1 else 0.0

    type_offset = float(spec.get("typeOffset", 0.0))
    fill_cfg = spec.get("fillPercent", {})
    fill_min = float(fill_cfg.get("min", 0))
    fill_max = float(fill_cfg.get("max", 100))
    if fill_min > fill_max:
        raise ValueError("fillPercent min/max hatasi.")

    id_base_map = spec.get("idBaseByType", {})
    containers: List[Container] = []

    for type_index, waste_type in enumerate(types):
        waste_type_str = str(waste_type)
        base_id = int(id_base_map.get(waste_type_str, 10000 + type_index * 10000))

        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c + 1
                lat = lat_min + (lat_step * r) + (type_offset * type_index)
                lng = lng_min + (lng_step * c) + (type_offset * type_index)
                span = int(fill_max - fill_min + 1)
                fill_percent = fill_min + ((r * 7 + c * 11 + type_index * 5) % span)

                containers.append(
                    Container(
                        id=base_id + idx,
                        waste_type=waste_type_str,
                        lat=round(lat, 6),
                        lng=round(lng, 6),
                        fill_percent=round(fill_percent, 2),
                    )
                )

    return containers


def load_containers(path: str) -> Tuple[str, List[Container]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    name = data.get("name", "unknown")
    if "generator" in data:
        containers = generate_containers_from_spec(data["generator"])
        return name, containers

    raw_items = data.get("containers", [])
    containers = []

    seen_ids = set()
    for item in raw_items:
        container_id = int(item["id"])
        if container_id in seen_ids:
            raise ValueError(f"Tekrarlanan container id: {container_id}")
        seen_ids.add(container_id)

        containers.append(
            Container(
                id=container_id,
                waste_type=str(item["wasteType"]),
                lat=float(item["lat"]),
                lng=float(item["lng"]),
                fill_percent=float(item.get("fillPercent", 0)),
            )
        )

    return name, containers


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_telemetry_items(
    containers: List[Container],
    rng: random.Random,
    min_increment: float,
    max_increment: float,
) -> List[dict]:
    recorded_at = iso_now()
    items = []

    for container in containers:
        delta = rng.uniform(min_increment, max_increment)
        new_fill = max(0.0, min(100.0, container.fill_percent + delta))
        container.fill_percent = new_fill

        items.append(
            {
                "containerId": container.id,
                "fillPercent": round(new_fill, 2),
                "lat": container.lat,
                "lng": container.lng,
                "recordedAt": recorded_at,
            }
        )

    return items


def chunk_items(items: List[dict], batch_size: int) -> List[List[dict]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def post_json(url: str, payload: dict, timeout: float) -> Tuple[Optional[int], str]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            text = resp.read().decode("utf-8")
            return status, text
    except HTTPError as e:
        text = e.read().decode("utf-8") if e.fp else ""
        return e.code, text
    except URLError as e:
        return None, str(e)


def save_payload(payload: dict, out_dir: str, filename: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def send_batch_with_retry(
    logger: logging.Logger,
    url: str,
    payload: dict,
    rng: random.Random,
    max_retries: int,
    backoff_base: float,
    backoff_max: float,
    timeout_seconds: float,
    save_batches: bool,
    batch_id: int,
    dry_run: bool,
    log_dir: str,
) -> bool:
    if dry_run:
        logger.info("DRY RUN | batch=%s | items=%s", batch_id, len(payload["items"]))
        return True

    attempt = 0
    while True:
        status, body = post_json(url, payload, timeout_seconds)

        if status is not None and 200 <= status < 300:
            logger.info("OK | batch=%s | status=%s | body=%s", batch_id, status, body.strip())
            if save_batches:
                save_payload(payload, os.path.join(log_dir, "batches"), f"batch_{batch_id}.json")
            return True

        should_retry = status is None or status in RETRY_STATUSES
        status_display = "NETWORK" if status is None else str(status)
        logger.warning("FAIL | batch=%s | status=%s | body=%s", batch_id, status_display, body.strip())

        if not should_retry or attempt >= max_retries:
            if save_batches:
                save_payload(payload, os.path.join(log_dir, "failed"), f"failed_batch_{batch_id}.json")
            return False

        delay = min(backoff_max, backoff_base * (2 ** attempt))
        delay = delay + rng.uniform(0, delay * 0.25)
        logger.info("RETRY | batch=%s | attempt=%s | sleep=%.2fs", batch_id, attempt + 1, delay)
        time.sleep(delay)
        attempt += 1


def resolve_containers_file(base_dir: str, scenario: str, override_path: Optional[str]) -> str:
    if override_path:
        return override_path

    if scenario == "demo":
        return os.path.join(base_dir, "data", "containers_demo.json")

    return os.path.join(base_dir, "data", "containers_backend_seed.json")


def build_config() -> Config:
    base_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="Atik Yonetimi Telemetri Simulasyonu")
    parser.add_argument("--api-base-url", default=env_or_default("SIM_API_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--telemetry-path", default=env_or_default("SIM_TELEMETRY_PATH", "/telemetry/ingest"))
    parser.add_argument("--scenario", choices=["backend-seed", "demo"], default=env_or_default("SIM_SCENARIO", "backend-seed"))
    parser.add_argument("--containers-file", default=env_or_default("SIM_CONTAINERS_FILE", ""))
    parser.add_argument("--tick-seconds", type=float, default=env_or_default_float("SIM_TICK_SECONDS", 2.0))
    parser.add_argument("--batch-size", type=int, default=env_or_default_int("SIM_BATCH_SIZE", 10))
    parser.add_argument("--seed", type=int, default=env_or_default_int("SIM_SEED", 20260325))
    parser.add_argument("--min-increment", type=float, default=env_or_default_float("SIM_MIN_INCREMENT", 0.5))
    parser.add_argument("--max-increment", type=float, default=env_or_default_float("SIM_MAX_INCREMENT", 5.0))
    parser.add_argument("--max-retries", type=int, default=env_or_default_int("SIM_MAX_RETRIES", 5))
    parser.add_argument("--backoff-base", type=float, default=env_or_default_float("SIM_BACKOFF_BASE", 1.0))
    parser.add_argument("--backoff-max", type=float, default=env_or_default_float("SIM_BACKOFF_MAX", 30.0))
    parser.add_argument("--timeout-seconds", type=float, default=env_or_default_float("SIM_TIMEOUT_SECONDS", 10.0))
    parser.add_argument("--dry-run", action="store_true", default=env_or_default_bool("SIM_DRY_RUN", False))
    parser.add_argument("--save-batches", action="store_true", default=env_or_default_bool("SIM_SAVE_BATCHES", False))
    parser.add_argument("--log-dir", default=env_or_default("SIM_LOG_DIR", os.path.join(base_dir, "logs")))
    parser.add_argument("--duration-seconds", type=float, default=env_or_default_float("SIM_DURATION_SECONDS", 0.0))
    parser.add_argument("--once", action="store_true", default=False)

    args = parser.parse_args()

    containers_file = resolve_containers_file(base_dir, args.scenario, args.containers_file or None)

    return Config(
        api_base_url=args.api_base_url.rstrip("/"),
        telemetry_path=args.telemetry_path,
        scenario=args.scenario,
        containers_file=containers_file,
        tick_seconds=args.tick_seconds,
        batch_size=args.batch_size,
        seed=args.seed,
        min_increment=args.min_increment,
        max_increment=args.max_increment,
        max_retries=args.max_retries,
        backoff_base=args.backoff_base,
        backoff_max=args.backoff_max,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
        save_batches=args.save_batches,
        log_dir=args.log_dir,
        duration_seconds=args.duration_seconds,
        once=args.once,
    )


def main() -> None:
    config = build_config()
    logger = setup_logger(config.log_dir)

    if not os.path.exists(config.containers_file):
        logger.error("Container dosyasi bulunamadi: %s", config.containers_file)
        sys.exit(1)

    data_name, containers = load_containers(config.containers_file)
    logger.info("Containers loaded | name=%s | count=%s", data_name, len(containers))

    rng = random.Random(config.seed)
    url = f"{config.api_base_url}{config.telemetry_path}"

    start_time = time.time()
    tick = 0
    batch_id = 0

    while True:
        tick += 1
        items = build_telemetry_items(containers, rng, config.min_increment, config.max_increment)
        batches = chunk_items(items, config.batch_size)

        logger.info("TICK %s | items=%s | batches=%s", tick, len(items), len(batches))

        for batch in batches:
            batch_id += 1
            payload = {"items": batch}
            send_batch_with_retry(
                logger=logger,
                url=url,
                payload=payload,
                rng=rng,
                max_retries=config.max_retries,
                backoff_base=config.backoff_base,
                backoff_max=config.backoff_max,
                timeout_seconds=config.timeout_seconds,
                save_batches=config.save_batches,
                batch_id=batch_id,
                dry_run=config.dry_run,
                log_dir=config.log_dir,
            )

        if config.once:
            break

        if config.duration_seconds > 0 and (time.time() - start_time) >= config.duration_seconds:
            break

        time.sleep(config.tick_seconds)


if __name__ == "__main__":
    main()
