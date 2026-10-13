"""버스 교통카드 더미 데이터로 노선별 운영 성과를 분석하는 스크립트.

분석 항목
- 노선별 일 이용 건수, 점유율, 고유 카드 수
- 노선별 평균 통행 정류장 수(하차순번 - 승차순번)와 노선 길이 대비 비율
- 노선별 평균 탑승시간(분)
- 운행시간(첫차~막차)과 배차간격으로 산출한 일 운행 횟수 → 회당 평균 승객 수
- 추정 요금 수입(기본요금 × 이용자구분 할인율, 환승 Y는 0원) → 일 수입, 운행 1회당 수입
- 정류장 순번별 재차인원(load profile) → 노선별 최대 재차 구간

실행: PYTHONIOENCODING=utf-8 python bus_data/analysis/route_performance.py
"""

import sys
from pathlib import Path

import pandas as pd

# read_bus_data.py 재사용 (bus_data 폴더를 import 경로에 추가)
BUS_DATA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUS_DATA_DIR))
from read_bus_data import load_alighting, load_routes  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "route_performance"

# ---------------------------------------------------------------------------
# 가정 상수
# ---------------------------------------------------------------------------
# 이용자구분별 요금 비율 (기본요금 대비). 목록에 없는 구분은 기본값 적용
요금비율 = {
    "일반": 1.0,
    "청소년": 0.8,
    "어린이": 0.5,
    "경로": 0.0,
}
요금비율_기본값 = 1.0
# 환승여부 'Y'인 승차는 요금 0원으로 가정 (환승 할인 단순화)
환승_요금 = 0
# 일 운행 횟수 = (막차 - 첫차) / 배차간격 + 1  (한 방향 기준 출발 횟수로 가정)
FONT_FAMILY = "Malgun Gothic"


def add_stop_sequence(trips: pd.DataFrame, route_stops: pd.DataFrame) -> pd.DataFrame:
    """승차/하차 정류장ID를 노선정류장 시트의 정류장순번으로 매핑한다."""
    seq = route_stops[["노선ID", "정류장ID", "정류장순번"]]
    trips = trips.merge(
        seq.rename(columns={"정류장ID": "승차정류장ID", "정류장순번": "승차순번"}),
        on=["노선ID", "승차정류장ID"], how="left",
    ).merge(
        seq.rename(columns={"정류장ID": "하차정류장ID", "정류장순번": "하차순번"}),
        on=["노선ID", "하차정류장ID"], how="left",
    )
    trips["통행정류장수"] = trips["하차순번"] - trips["승차순번"]
    trips["탑승시간_분"] = (trips["하차일시"] - trips["승차일시"]).dt.total_seconds() / 60
    return trips


def add_fare(trips: pd.DataFrame, routes: pd.DataFrame) -> pd.DataFrame:
    """기본요금 × 이용자구분 비율로 추정 요금을 계산한다 (환승 Y는 0원)."""
    trips = trips.merge(routes[["노선ID", "기본요금"]], on="노선ID", how="left")
    비율 = trips["이용자구분"].astype(str).map(요금비율).fillna(요금비율_기본값)
    trips["추정요금"] = (trips["기본요금"] * 비율).where(trips["환승여부"] != "Y", 환승_요금)
    return trips


def daily_runs(routes: pd.DataFrame) -> pd.DataFrame:
    """첫차~막차 운행시간과 배차간격으로 일 운행 횟수를 산출한다."""
    첫차 = pd.to_datetime(routes["첫차"].astype(str), format="%H:%M")
    막차 = pd.to_datetime(routes["막차"].astype(str), format="%H:%M")
    운행분 = (막차 - 첫차).dt.total_seconds() / 60
    out = routes[["노선ID"]].copy()
    out["운행시간_분"] = 운행분.astype(int)
    out["일운행횟수"] = (운행분 // routes["배차간격_분"] + 1).astype(int)
    return out


def load_profile(trips: pd.DataFrame, route_stops: pd.DataFrame) -> pd.DataFrame:
    """정류장 순번별 재차인원: 승차 +1, 하차 -1 누적 (하차 결측 행 제외).

    하차순번 < 승차순번인 통행(역방향)이 있으면 방향을 나눠 따로 누적한다.
    """
    valid = trips.dropna(subset=["승차순번", "하차순번"])
    valid = valid[valid["통행정류장수"] != 0].copy()
    valid["방향"] = valid["통행정류장수"].gt(0).map({True: "정방향", False: "역방향"})

    rows = []
    for (노선ID, 방향), g in valid.groupby(["노선ID", "방향"]):
        stops = route_stops[route_stops["노선ID"] == 노선ID].sort_values("정류장순번")
        승차 = g["승차순번"].value_counts()
        하차 = g["하차순번"].value_counts()
        순번목록 = stops["정류장순번"].tolist()
        if 방향 == "역방향":
            순번목록 = 순번목록[::-1]
        재차 = 0
        for i, 순번 in enumerate(순번목록):
            on = int(승차.get(순번, 0))
            off = int(하차.get(순번, 0))
            재차 += on - off
            다음순번 = 순번목록[i + 1] if i + 1 < len(순번목록) else None
            rows.append({
                "노선ID": 노선ID, "방향": 방향, "정류장순번": 순번,
                "정류장명": stops.loc[stops["정류장순번"] == 순번, "정류장명"].iloc[0],
                "승차": on, "하차": off,
                "재차인원": 재차 if 다음순번 is not None else 0,
                "다음정류장순번": 다음순번,
            })
    return pd.DataFrame(rows)


def max_load_section(profile: pd.DataFrame, route_stops: pd.DataFrame) -> pd.DataFrame:
    """노선(·방향)별 재차인원이 최대인 구간을 뽑는다."""
    names = route_stops.set_index(["노선ID", "정류장순번"])["정류장명"]
    idx = profile.groupby(["노선ID", "방향"])["재차인원"].idxmax()
    top = profile.loc[idx].copy()
    top["구간"] = [
        f"{a}({int(s)}) → {names[(r, int(n))]}({int(n)})"
        for r, s, n, a in zip(top["노선ID"], top["정류장순번"], top["다음정류장순번"], top["정류장명"])
    ]
    return top[["노선ID", "방향", "구간", "재차인원"]].rename(columns={"재차인원": "최대재차인원"})


def build_summary(trips, routes, runs, max_load) -> pd.DataFrame:
    g = trips.groupby("노선ID")
    summary = pd.DataFrame({
        "일이용건수": g.size(),
        "고유카드수": g["카드ID"].nunique(),
        "하차결측건수": g["하차정류장ID"].apply(lambda s: s.isna().sum()),
        "평균통행정류장수": g["통행정류장수"].mean(),
        "평균탑승시간_분": g["탑승시간_분"].mean(),
        "환승승차비율": g["환승여부"].apply(lambda s: (s == "Y").mean()),
        "일추정수입_원": g["추정요금"].sum(),
    }).reset_index()
    summary["점유율"] = summary["일이용건수"] / summary["일이용건수"].sum()

    summary = (
        routes[["노선ID", "노선번호", "노선유형", "정류장수", "배차간격_분", "기본요금"]]
        .merge(summary, on="노선ID", how="left")
        .merge(runs, on="노선ID", how="left")
    )
    # 노선 길이 = 정류장수 - 1 (정류장 간 구간 수)
    summary["노선길이대비_통행비율"] = summary["평균통행정류장수"] / (summary["정류장수"] - 1)
    summary["회당평균승객수"] = summary["일이용건수"] / summary["일운행횟수"]
    summary["운행1회당수입_원"] = summary["일추정수입_원"] / summary["일운행횟수"]
    summary["건당평균수입_원"] = summary["일추정수입_원"] / summary["일이용건수"]

    # 정방향 기준 최대 재차 구간 (정방향이 없으면 역방향)
    ml = max_load.sort_values("방향", key=lambda s: s.ne("정방향")).drop_duplicates("노선ID")
    summary = summary.merge(
        ml.rename(columns={"방향": "최대재차_방향", "구간": "최대재차구간"}), on="노선ID", how="left"
    )

    cols = [
        "노선ID", "노선번호", "노선유형", "정류장수", "배차간격_분", "기본요금",
        "일이용건수", "점유율", "고유카드수", "하차결측건수",
        "평균통행정류장수", "노선길이대비_통행비율", "평균탑승시간_분",
        "운행시간_분", "일운행횟수", "회당평균승객수",
        "환승승차비율", "일추정수입_원", "운행1회당수입_원", "건당평균수입_원",
        "최대재차_방향", "최대재차구간", "최대재차인원",
    ]
    summary = summary[cols].sort_values("일이용건수", ascending=False)
    round_cols = {
        "점유율": 4, "평균통행정류장수": 2, "노선길이대비_통행비율": 3, "평균탑승시간_분": 1,
        "회당평균승객수": 2, "환승승차비율": 3, "운행1회당수입_원": 0, "건당평균수입_원": 0,
    }
    return summary.round(round_cols)


def save_charts(summary: pd.DataFrame, profile: pd.DataFrame) -> list[Path]:
    """matplotlib가 있으면 PNG 차트를 저장한다. 없으면 빈 목록 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[안내] matplotlib가 설치되어 있지 않아 차트 저장을 생략합니다.")
        return []

    plt.rcParams["font.family"] = FONT_FAMILY
    plt.rcParams["axes.unicode_minus"] = False
    saved = []

    # 1) 노선별 회당 평균 승객 수 / 운행 1회당 수입
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    labels = summary["노선번호"] + "(" + summary["노선유형"] + ")"
    axes[0].bar(labels, summary["회당평균승객수"], color="#4C78A8")
    axes[0].set_title("노선별 회당 평균 승객 수")
    axes[1].bar(labels, summary["운행1회당수입_원"], color="#F58518")
    axes[1].set_title("노선별 운행 1회당 추정 수입(원)")
    for ax in axes:
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    path = OUTPUT_DIR / "route_efficiency.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    saved.append(path)

    # 2) 노선별 재차인원 프로파일 (정방향)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    fwd = profile[profile["방향"] == "정방향"]
    for 노선ID, g in fwd.groupby("노선ID"):
        ax.plot(g["정류장순번"], g["재차인원"], marker="o", label=노선ID)
    ax.set_xlabel("정류장순번")
    ax.set_ylabel("재차인원(일 누적)")
    ax.set_title("노선별 정류장 순번별 재차인원 (정방향, 하차 결측 제외)")
    ax.legend()
    fig.tight_layout()
    path = OUTPUT_DIR / "load_profile.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    saved.append(path)
    return saved


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)

    routes, route_stops = load_routes()
    trips = load_alighting()

    trips = add_stop_sequence(trips, route_stops)
    trips = add_fare(trips, routes)
    runs = daily_runs(routes)

    # 데이터 점검
    n_missing = trips["하차정류장ID"].isna().sum()
    n_unmapped = trips["승차순번"].isna().sum() + (trips["하차순번"].isna() & trips["하차정류장ID"].notna()).sum()
    n_reverse = (trips["통행정류장수"] < 0).sum()
    n_zero = (trips["통행정류장수"] == 0).sum()
    print(f"전체 {len(trips)}건 | 하차 미태그 {n_missing}건 ({n_missing / len(trips):.1%}) | "
          f"순번 매핑 실패 {n_unmapped}건 | 역방향(하차순번<승차순번) {n_reverse}건 | 동일정류장 하차 {n_zero}건\n")

    profile = load_profile(trips, route_stops)
    max_load = max_load_section(profile, route_stops)
    summary = build_summary(trips, routes, runs, max_load)

    # 이용자구분별 수입 구성
    fare_mix = (
        trips.assign(이용자구분=trips["이용자구분"].astype(str))
        .groupby(["노선ID", "이용자구분", "환승여부"], observed=True)
        .agg(건수=("카드ID", "size"), 추정수입_원=("추정요금", "sum"))
        .reset_index()
    )

    outputs = {
        "route_summary.csv": summary,
        "load_profile.csv": profile,
        "max_load_section.csv": max_load,
        "fare_by_user_type.csv": fare_mix,
    }
    for name, df in outputs.items():
        df.to_csv(OUTPUT_DIR / name, index=False, encoding="utf-8-sig")

    print("=== 노선별 운영 성과 요약 ===")
    print(summary.drop(columns=["최대재차구간"]).to_string(index=False), end="\n\n")
    print("=== 노선별 최대 재차 구간 ===")
    print(max_load.to_string(index=False), end="\n\n")
    total = summary["일추정수입_원"].sum()
    print(f"전체 일 추정 수입: {total:,.0f}원 | 전체 일 운행 횟수: {summary['일운행횟수'].sum()}회\n")

    charts = save_charts(summary, profile)
    print("저장된 파일:")
    for p in [OUTPUT_DIR / n for n in outputs] + charts:
        print(f"  {p.relative_to(BUS_DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
