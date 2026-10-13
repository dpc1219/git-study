"""버스 노선 / 하차 더미 데이터를 xlsx로 생성하는 스크립트.

생성 파일
- bus_routes.xlsx
    - 노선정보   : 노선 단위 기본 정보
    - 노선정류장 : 노선별 경유 정류장 순서
- bus_alighting.xlsx
    - 하차기록   : 교통카드 승·하차 기록 (일부 하차 미태그 포함)
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_TRIPS = 5000
BASE_DATE = "2026-10-12"
MISSING_ALIGHT_RATE = 0.05  # 하차 미태그 비율

OUT_DIR = Path(__file__).parent

rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# 1. 정류장 마스터
# ---------------------------------------------------------------------------
STOP_NAMES = [
    "시청앞", "중앙시장", "역전광장", "시외버스터미널", "대학교정문", "종합병원",
    "구청", "문화예술회관", "체육공원", "신도시입구", "산업단지", "물류센터",
    "아파트단지", "초등학교", "도서관", "법원", "세무서", "우체국",
    "호수공원", "고속버스터미널", "농협", "소방서", "경찰서", "공영주차장",
    "전통시장", "환승센터", "주민센터", "보건소", "과학관", "박물관",
]

stops = pd.DataFrame({
    "정류장ID": [f"ST{i:04d}" for i in range(1, len(STOP_NAMES) + 1)],
    "정류장명": STOP_NAMES,
    "위도": np.round(rng.uniform(37.45, 37.60, len(STOP_NAMES)), 6),
    "경도": np.round(rng.uniform(126.90, 127.10, len(STOP_NAMES)), 6),
})

# ---------------------------------------------------------------------------
# 2. 노선 정보
# ---------------------------------------------------------------------------
ROUTE_SPECS = [
    # 노선번호, 노선유형, 정류장 수, 배차간격(분), 요금
    ("101", "간선", 14, 8, 1500),
    ("150", "간선", 12, 10, 1500),
    ("2012", "지선", 9, 12, 1500),
    ("3315", "지선", 10, 15, 1500),
    ("9401", "광역", 6, 20, 3000),
    ("마을01", "마을", 5, 15, 1200),
]

routes, route_stops = [], []
for idx, (no, kind, n_stops, headway, fare) in enumerate(ROUTE_SPECS, start=1):
    route_id = f"R{idx:03d}"
    path = stops.sample(n=n_stops, random_state=SEED + idx).reset_index(drop=True)
    routes.append({
        "노선ID": route_id,
        "노선번호": no,
        "노선유형": kind,
        "기점": path.loc[0, "정류장명"],
        "종점": path.loc[n_stops - 1, "정류장명"],
        "정류장수": n_stops,
        "배차간격_분": headway,
        "첫차": "05:30",
        "막차": "23:30" if kind != "마을" else "22:00",
        "기본요금": fare,
    })
    for seq, row in path.iterrows():
        route_stops.append({
            "노선ID": route_id,
            "정류장순번": seq + 1,
            "정류장ID": row["정류장ID"],
            "정류장명": row["정류장명"],
            "위도": row["위도"],
            "경도": row["경도"],
        })

routes = pd.DataFrame(routes)
route_stops = pd.DataFrame(route_stops)

# ---------------------------------------------------------------------------
# 3. 하차 기록 (승차 정보 포함)
# ---------------------------------------------------------------------------
# 출퇴근 시간대에 몰리도록 시간대별 가중치 부여 (05시 ~ 23시)
hours = np.arange(5, 24)
hour_weight = np.array([1, 3, 9, 10, 6, 4, 4, 5, 4, 4, 5, 6, 8, 10, 7, 5, 4, 3, 1], dtype=float)
hour_weight /= hour_weight.sum()

# 간선 노선 이용이 많도록 노선별 가중치
route_weight = np.array([0.28, 0.24, 0.15, 0.13, 0.12, 0.08])

stops_by_route = {rid: g.reset_index(drop=True) for rid, g in route_stops.groupby("노선ID")}

records = []
base = pd.Timestamp(BASE_DATE)
for i in range(N_TRIPS):
    route_id = rng.choice(routes["노선ID"], p=route_weight)
    path = stops_by_route[route_id]
    n = len(path)

    board_seq = rng.integers(1, n)                 # 마지막 정류장에서는 승차 X
    ride_len = min(rng.geometric(0.3), n - board_seq)  # 짧은 통행이 많도록
    alight_seq = board_seq + ride_len

    board_time = base + pd.Timedelta(
        hours=int(rng.choice(hours, p=hour_weight)),
        minutes=int(rng.integers(0, 60)),
        seconds=int(rng.integers(0, 60)),
    )
    # 정류장 간 2~4분 소요
    alight_time = board_time + pd.Timedelta(minutes=float(ride_len * rng.uniform(2, 4)))

    records.append({
        "카드ID": f"C{rng.integers(1, 1500):06d}",
        "노선ID": route_id,
        "승차일시": board_time,
        "승차정류장ID": path.loc[board_seq - 1, "정류장ID"],
        "하차일시": alight_time.floor("s"),
        "하차정류장ID": path.loc[alight_seq - 1, "정류장ID"],
        "이용자구분": rng.choice(["일반", "청소년", "어린이", "경로"], p=[0.75, 0.13, 0.04, 0.08]),
        "환승여부": rng.choice(["N", "Y"], p=[0.7, 0.3]),
    })

alighting = pd.DataFrame(records).sort_values("승차일시").reset_index(drop=True)

# 하차 미태그 모사: 하차 정보 결측 처리
missing = rng.random(len(alighting)) < MISSING_ALIGHT_RATE
alighting.loc[missing, ["하차일시", "하차정류장ID"]] = None

# ---------------------------------------------------------------------------
# 4. xlsx 저장
# ---------------------------------------------------------------------------
routes_path = OUT_DIR / "bus_routes.xlsx"
alighting_path = OUT_DIR / "bus_alighting.xlsx"

with pd.ExcelWriter(routes_path, engine="openpyxl") as writer:
    routes.to_excel(writer, sheet_name="노선정보", index=False)
    route_stops.to_excel(writer, sheet_name="노선정류장", index=False)

with pd.ExcelWriter(alighting_path, engine="openpyxl", datetime_format="yyyy-mm-dd hh:mm:ss") as writer:
    alighting.to_excel(writer, sheet_name="하차기록", index=False)

print(f"[생성] {routes_path.name}    노선 {len(routes)}개 / 노선정류장 {len(route_stops)}행")
print(f"[생성] {alighting_path.name} 하차기록 {len(alighting)}행 (미태그 {missing.sum()}건)")
