# seed_smartwatch.py
import json
import numpy as np
import random
from db_access import init_db_schema, get_conn

print("⌚ INITIALIZING SMARTWATCH DATABASE (1000 UNITS)...")
init_db_schema()

conn = get_conn()
cur = conn.cursor()

# CONFIGURATION
BRANDS = {
    "Apple": ["Watch Series 7", "Watch Series 8", "Watch Ultra"],
    "Garmin": ["Fenix 7", "Venu 2", "Forerunner 965"],
    "Samsung": ["Galaxy Watch 5", "Galaxy Watch 6 Classic"]
}

CONDITIONS = ["New Open Box", "Grade A", "Grade B", "Grade C (Fail)"]
BAND_TYPES = ["Silicone", "Milanese Loop", "Leather Link", "Alpine Loop"]

# DEFECT POOL (For the 30% bad units)
DEFECTS = [
    "Salt corrosion on charging contacts",
    "Weak Taptic Engine (Haptic failure)",
    "Micro-abrasions on Heart Rate Sensor",
    "Digital Crown stuck/sticky",
    "Oleophobic coating delamination",
    "Sweat ingress in barometer port"
]

print("🏭 Fabricating 1000 Smartwatches...")

for i in range(1, 1001):
    # 1. Select Identity
    brand = random.choice(list(BRANDS.keys()))
    model = random.choice(BRANDS[brand])
    did = f"{brand.upper()}-{model.replace(' ', '')}-{i:04d}"
    
    # 2. Determine Fate (70% Good, 30% Flawed)
    is_defective = random.random() < 0.30
    
    if is_defective:
        condition = "Grade C (Fail)"
        defect = random.choice(DEFECTS)
        sensor_status = "Degraded (Signal Noise)"
        haptic_health = random.randint(40, 70) # Low score
        band_cond = "Worn / Discolored"
    else:
        condition = random.choice(["New Open Box", "Grade A", "Grade B"])
        defect = "None"
        sensor_status = "Optimal"
        haptic_health = random.randint(90, 100)
        band_cond = "Good"

    # 3. Telemetry Generation (Simulated)
    # Heart Rate Sensor Noise (Higher variance = worse sensor)
    hr_variance = random.uniform(0.1, 0.5) if not is_defective else random.uniform(1.5, 5.0)
    fft_samples = np.random.normal(0, hr_variance, 100).tolist()
    
    # Battery decay curve
    cycles = random.randint(5, 500)
    health = max(80, 100 - (cycles * 0.05))

    payload = {
        "brand": brand,
        "model": model,
        "type": "Smartwatch",
        "specs": {
            "case_size_mm": random.choice([40, 41, 44, 45, 49]),
            "band_type": random.choice(BAND_TYPES),
            "housing_material": random.choice(["Aluminum", "Stainless Steel", "Titanium"])
        },
        "r2v3_flags": {
            "cosmetic_grade": condition,
            "band_condition": band_cond,
            "primary_defect": defect,
            "battery_health_percent": int(health),
            "cycle_count": cycles
        },
        "telemetry": {
            "haptic_motor_score": haptic_health,
            "sensor_oxidation_check": sensor_status,
            "water_seal_integrity": "Pass" if not is_defective else random.choice(["Pass", "Fail"])
        },
        "fft_samples": fft_samples
    }
    
    # 4. Insert Device
    cur.execute("INSERT INTO device_registry (device_id, device_payload) VALUES (%s, %s)", 
                (did, json.dumps(payload)))
    
    # 5. Insert Initial Audit Log (Ingest)
    run_id = f"RUN-INGEST-{i:04d}"
    cur.execute("INSERT INTO runs (run_id, device_id) VALUES (%s, %s)", (run_id, did))
    
    log_text = f"Unit received. Visual inspection: {defect}. Battery Cycles: {cycles}."
    cur.execute("INSERT INTO audit_log (run_id, event_type, payload_json) VALUES (%s, %s, %s)",
                (run_id, "LOGISTICS_RECEIVE", json.dumps({"text": log_text})))

conn.commit()
conn.close()
print("✅ SUCCESS: 1000 Smartwatches seeded into Neon DB.")