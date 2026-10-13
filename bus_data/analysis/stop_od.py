"""정류장 및 OD(출발-도착) 분석 스크립트.

- 정류장별 승차·하차·순유입, 경유 노선 수
- 오전/오후 첨두 순유입 비교 → 주거지형·업무지형 정류장 분류
- 정류장 OD 행렬, 상위 OD 쌍
- OD 직선거리(haversine) 및 거리대별 분포
- 환승(Y) 이용자 승차 정류장 → 환승 거점 후보

실행: PYTHONIOENCODING=utf-8 python bus_data/analysis/stop_od.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent
OUT_DIR = BASE_DIR / "output" / "stop_od"

sys.path.insert(0, str(DATA_DIR))
from read_bus_data import load_alighting, load_routes  # noqa: E402

# 첨두 시간대 정의 (시 단위, 시작 포함·끝 미포함) → 07:00~08:59, 17:00~18:59
오전첨두 = (7, 9)
오후첨두 = (17, 19)
# 첨두 분류 시 너무 적은 이용량 정류장은 '판단보류'로 둔다
분류_최소건수 = 20


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """위경도(도) 두 점 사이의 대원 거리(km)."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def build_stop_master(route_stops: pd.DataFrame) -> pd.DataFrame:
    """정류장ID 단위 마스터(정류장명·좌표·경유 노선 수)."""
    stops = (
        route_stops.groupby("정류장ID")
        .agg(정류장명=("정류장명", "first"), 위도=("위도", "first"), 경도=("경도", "first"),
             경유노선수=("노선ID", "nunique"),
             경유노선=("노선ID", lambda s: ",".join(sorted(s.unique()))))
        .reset_index()
    )
    return stops


def in_hours(ts: pd.Series, hours: tuple[int, int]) -> pd.Series:
    h = ts.dt.hour
    return (h >= hours[0]) & (h < hours[1])


def stop_volume(trips: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    """정류장별 승차·하차·합계·순유입."""
    board = trips["승차정류장ID"].value_counts().rename("승차")
    alight = trips["하차정류장ID"].dropna().value_counts().rename("하차")
    vol = stops.set_index("정류장ID").join([board, alight]).fillna({"승차": 0, "하차": 0})
    vol[["승차", "하차"]] = vol[["승차", "하차"]].astype(int)
    vol["합계"] = vol["승차"] + vol["하차"]
    vol["순유입"] = vol["하차"] - vol["승차"]
    return vol.reset_index().sort_values("합계", ascending=False)


def peak_net_inflow(trips: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    """첨두별 순유입 비교 및 주거지형/업무지형 분류."""
    rows = {}
    for 이름, hrs in [("오전", 오전첨두), ("오후", 오후첨두)]:
        b = trips.loc[in_hours(trips["승차일시"], hrs), "승차정류장ID"].value_counts()
        a = trips.loc[in_hours(trips["하차일시"], hrs), "하차정류장ID"].value_counts()
        rows[f"{이름}_승차"] = b
        rows[f"{이름}_하차"] = a
    pk = stops.set_index("정류장ID")[["정류장명", "경유노선수"]].join(pd.DataFrame(rows)).fillna(0)
    num_cols = [c for c in pk.columns if c.endswith(("_승차", "_하차"))]
    pk[num_cols] = pk[num_cols].astype(int)
    pk["오전_순유입"] = pk["오전_하차"] - pk["오전_승차"]
    pk["오후_순유입"] = pk["오후_하차"] - pk["오후_승차"]
    pk["오전_이용량"] = pk["오전_하차"] + pk["오전_승차"]
    # 오전 순유입 비율(-1~1): 정류장 규모 차이를 보정한 지표
    pk["오전_순유입비율"] = (pk["오전_순유입"] / pk["오전_이용량"].replace(0, np.nan)).round(3)

    def classify(r) -> str:
        if r["오전_이용량"] < 분류_최소건수:
            return "판단보류"
        if r["오전_순유입"] < 0 and r["오후_순유입"] > 0:
            return "주거지형"
        if r["오전_순유입"] > 0 and r["오후_순유입"] < 0:
            return "업무지형"
        if r["오전_순유입"] < 0:
            return "주거지형(약)"  # 오전 유출이지만 오후 대칭 패턴은 아님
        if r["오전_순유입"] > 0:
            return "업무지형(약)"
        return "혼합"

    pk["유형"] = pk.apply(classify, axis=1)
    return pk.reset_index().sort_values("오전_순유입")


def od_analysis(trips: pd.DataFrame, stops: pd.DataFrame):
    """OD 행렬, OD 쌍 목록(거리 포함)."""
    od = trips.dropna(subset=["하차정류장ID"])
    m = stops.set_index("정류장ID")[["정류장명", "위도", "경도"]]
    od = (od.join(m.add_prefix("승차_"), on="승차정류장ID")
            .join(m.add_prefix("하차_"), on="하차정류장ID"))
    matrix = pd.crosstab(od["승차_정류장명"], od["하차_정류장명"])

    pairs = (od.groupby(["승차정류장ID", "승차_정류장명", "하차정류장ID", "하차_정류장명"])
               .agg(통행수=("카드ID", "size"),
                    승차_위도=("승차_위도", "first"), 승차_경도=("승차_경도", "first"),
                    하차_위도=("하차_위도", "first"), 하차_경도=("하차_경도", "first"))
               .reset_index())
    pairs["직선거리_km"] = haversine_km(pairs["승차_위도"], pairs["승차_경도"],
                                    pairs["하차_위도"], pairs["하차_경도"]).round(3)
    pairs = pairs.drop(columns=["승차_위도", "승차_경도", "하차_위도", "하차_경도"])
    pairs = pairs.sort_values("통행수", ascending=False).reset_index(drop=True)
    pairs["통행비중"] = (pairs["통행수"] / pairs["통행수"].sum()).round(4)

    od["직선거리_km"] = haversine_km(od["승차_위도"], od["승차_경도"],
                                 od["하차_위도"], od["하차_경도"])
    return od, matrix, pairs


def distance_bands(od: pd.DataFrame) -> pd.DataFrame:
    bins = [0, 1, 2, 3, 5, 7, 10, np.inf]
    labels = ["1km 미만", "1~2km", "2~3km", "3~5km", "5~7km", "7~10km", "10km 이상"]
    band = pd.cut(od["직선거리_km"], bins=bins, labels=labels, right=False)
    dist = band.value_counts().reindex(labels).rename("통행수").to_frame()
    share = dist["통행수"] / dist["통행수"].sum()
    dist["비중"] = share.round(4)
    dist["누적비중"] = share.cumsum().round(4)
    dist.index.name = "거리대"
    return dist.reset_index()


def transfer_hubs(trips: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    """환승 Y 이용자 승차 정류장 → 환승 거점 후보."""
    tr = trips.loc[trips["환승여부"] == "Y", "승차정류장ID"].value_counts().rename("환승승차")
    all_b = trips["승차정류장ID"].value_counts().rename("전체승차")
    hub = stops.set_index("정류장ID")[["정류장명", "경유노선수", "경유노선"]].join([tr, all_b]).fillna(0)
    hub[["환승승차", "전체승차"]] = hub[["환승승차", "전체승차"]].astype(int)
    hub["환승비율"] = (hub["환승승차"] / hub["전체승차"].replace(0, np.nan)).round(3)
    hub["환승승차_비중"] = (hub["환승승차"] / hub["환승승차"].sum()).round(4)
    return hub.reset_index().sort_values("환승승차", ascending=False)


def save_charts(vol: pd.DataFrame, pk: pd.DataFrame) -> list[Path]:
    """matplotlib이 있을 때만 차트를 저장한다."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[안내] matplotlib 미설치 → 차트 생략")
        return []

    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    saved = []

    # 1) 정류장 위치 산점도 (크기=합계 이용량, 색=순유입)
    fig, ax = plt.subplots(figsize=(9, 7))
    lim = vol["순유입"].abs().max() or 1
    sc = ax.scatter(vol["경도"], vol["위도"], s=vol["합계"] / vol["합계"].max() * 1500 + 20,
                    c=vol["순유입"], cmap="coolwarm", vmin=-lim, vmax=lim,
                    alpha=0.75, edgecolors="k", linewidths=0.5)
    for _, r in vol.iterrows():
        ax.annotate(r["정류장명"], (r["경도"], r["위도"]), fontsize=8,
                    xytext=(4, 4), textcoords="offset points")
    fig.colorbar(sc, ax=ax, label="순유입(하차−승차)")
    ax.set_title("정류장별 이용량(원 크기)과 순유입(색)")
    ax.set_xlabel("경도")
    ax.set_ylabel("위도")
    fig.tight_layout()
    p = OUT_DIR / "stop_volume_map.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    saved.append(p)

    # 2) 오전/오후 첨두 순유입 비교 막대
    d = pk.sort_values("오전_순유입")
    fig, ax = plt.subplots(figsize=(10, 8))
    y = np.arange(len(d))
    ax.barh(y - 0.2, d["오전_순유입"], height=0.4, label="오전 첨두(07~09시)", color="#d62728")
    ax.barh(y + 0.2, d["오후_순유입"], height=0.4, label="오후 첨두(17~19시)", color="#1f77b4")
    ax.set_yticks(y, d["정류장명"] + " [" + d["유형"] + "]", fontsize=8)
    ax.axvline(0, color="k", linewidth=0.8)
    ax.set_xlabel("순유입(하차−승차)")
    ax.set_title("첨두 시간대별 정류장 순유입")
    ax.legend()
    fig.tight_layout()
    p = OUT_DIR / "peak_net_inflow.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    saved.append(p)
    return saved


def main() -> None:
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _, route_stops = load_routes()
    trips = load_alighting()
    stops = build_stop_master(route_stops)

    n_all = len(trips)
    n_miss = trips["하차정류장ID"].isna().sum()
    print(f"전체 통행 {n_all}건, 하차 미태그 {n_miss}건({n_miss / n_all:.1%}), 정류장 {len(stops)}개\n")
    print("※ 승차 집계는 전체, 하차·OD·거리 집계는 하차 태그된 통행만 사용\n")

    # 1. 정류장별 이용량
    vol = stop_volume(trips, stops)
    print("=== 1. 정류장별 이용량 상위 10 (합계 기준) ===")
    print(vol[["정류장명", "경유노선수", "승차", "하차", "합계", "순유입"]].head(10).to_string(index=False), "\n")
    print("순유입 상위 3:", ", ".join(f"{r.정류장명}({r.순유입:+d})" for r in vol.nlargest(3, "순유입").itertuples()))
    print("순유출 상위 3:", ", ".join(f"{r.정류장명}({r.순유입:+d})" for r in vol.nsmallest(3, "순유입").itertuples()))
    print(f"경유 노선 수 vs 합계 이용량 상관계수: {vol['경유노선수'].corr(vol['합계']):.3f}\n")

    # 2. 첨두 순유입
    pk = peak_net_inflow(trips, stops)
    print("=== 2. 첨두 순유입 및 정류장 유형 ===")
    print(pk[["정류장명", "오전_승차", "오전_하차", "오전_순유입", "오후_순유입", "오전_순유입비율", "유형"]]
          .to_string(index=False), "\n")
    print("유형별 정류장 수:", pk["유형"].value_counts().to_dict(), "\n")

    # 3. OD
    od, matrix, pairs = od_analysis(trips, stops)
    print(f"=== 3. OD 행렬 {matrix.shape[0]}×{matrix.shape[1]}, 관측 OD 쌍 {len(pairs)}개 ===")
    print("상위 10개 OD 쌍")
    print(pairs[["승차_정류장명", "하차_정류장명", "통행수", "통행비중", "직선거리_km"]].head(10).to_string(), "\n")
    top10_share = pairs["통행비중"].head(10).sum()
    print(f"상위 10개 OD 쌍이 전체 OD 통행의 {top10_share:.1%}\n")

    # 4. 거리
    dist = distance_bands(od)
    d = od["직선거리_km"]
    print("=== 4. OD 직선거리 ===")
    print(f"통행 가중 평균 {d.mean():.2f}km, 중앙값 {d.median():.2f}km, 최대 {d.max():.2f}km")
    print(f"OD 쌍 단순 평균 {pairs['직선거리_km'].mean():.2f}km")
    print(dist.to_string(index=False), "\n")
    by_type = od.groupby("이용자구분", observed=True)["직선거리_km"].agg(["count", "mean"]).round(2)
    print("이용자구분별 평균 직선거리(km)")
    print(by_type, "\n")

    # 5. 환승 거점
    hub = transfer_hubs(trips, stops)
    print(f"=== 5. 환승 거점 후보 (환승 Y {int((trips['환승여부'] == 'Y').sum())}건) ===")
    print(hub[["정류장명", "경유노선수", "환승승차", "전체승차", "환승비율", "환승승차_비중"]].head(10).to_string(index=False))
    print(f"경유 노선 수 vs 환승승차 상관계수: {hub['경유노선수'].corr(hub['환승승차']):.3f}\n")

    # 저장
    outputs = {
        "stop_volume.csv": vol,
        "peak_net_inflow.csv": pk,
        "od_pairs.csv": pairs,
        "od_top10.csv": pairs.head(10),
        "od_distance_bands.csv": dist,
        "transfer_hubs.csv": hub,
    }
    for name, df in outputs.items():
        df.to_csv(OUT_DIR / name, index=False, encoding="utf-8-sig")
    matrix.to_csv(OUT_DIR / "od_matrix.csv", encoding="utf-8-sig")
    charts = save_charts(vol, pk)

    print("=== 저장 파일 ===")
    for p in sorted(OUT_DIR.iterdir()):
        print(" -", p.relative_to(DATA_DIR.parent))


if __name__ == "__main__":
    main()
