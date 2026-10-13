"""버스 교통카드 더미 데이터로 시간대별 수요 패턴을 분석하는 스크립트.

분석 항목
1. 승차 시각 기준 시간대별 이용 건수, 오전/오후 첨두시간 식별 및 첨두 집중률
2. 노선유형별 × 시간대 이용 분포
3. 이용자구분별 시간대 분포 차이 (피크 시간)
4. 시간대별 평균 탑승시간(분) (하차 결측 행 제외)
5. 노선별 시간당 수요 ÷ 시간당 운행 횟수(60 / 배차간격) → 첨두시 회당 평균 승객 수

결과 CSV는 output/time_demand/ 에 utf-8-sig로 저장한다.
matplotlib가 설치되어 있으면 PNG 차트도 저장하고, 없으면 생략한다.
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent
OUT_DIR = BASE_DIR / "output" / "time_demand"

sys.path.insert(0, str(DATA_DIR))
from read_bus_data import load_alighting, load_routes  # noqa: E402

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "Malgun Gothic"  # Windows 한글 폰트
    plt.rcParams["axes.unicode_minus"] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

HOURS = list(range(24))
PEAK_WINDOW = 2  # 첨두시간 폭(시간)


def save_csv(df: pd.DataFrame, name: str, index: bool = True) -> None:
    """결과 표를 utf-8-sig CSV로 저장한다."""
    df.to_csv(OUT_DIR / f"{name}.csv", encoding="utf-8-sig", index=index)


def find_peak(hourly: pd.Series, start: int, end: int, width: int = PEAK_WINDOW) -> tuple[int, int]:
    """[start, end) 구간에서 연속 width시간 합계가 최대인 시작 시각과 그 합계를 반환한다."""
    best_hour, best_sum = start, -1
    for h in range(start, end - width + 1):
        s = int(hourly.loc[h:h + width - 1].sum())
        if s > best_sum:
            best_hour, best_sum = h, s
    return best_hour, best_sum


def hourly_counts(df: pd.DataFrame) -> pd.DataFrame:
    """1. 시간대별 이용 건수와 비중, 오전/오후 첨두 식별."""
    hourly = df["승차시"].value_counts().reindex(HOURS, fill_value=0).sort_index()
    total = int(hourly.sum())

    am_start, am_sum = find_peak(hourly, 0, 12)
    pm_start, pm_sum = find_peak(hourly, 12, 24)

    table = pd.DataFrame({"이용건수": hourly, "비중_%": (hourly / total * 100).round(2)})
    table.index.name = "시간대"
    table["첨두구분"] = ""
    table.loc[am_start:am_start + PEAK_WINDOW - 1, "첨두구분"] = "오전첨두"
    table.loc[pm_start:pm_start + PEAK_WINDOW - 1, "첨두구분"] = "오후첨두"
    save_csv(table, "01_시간대별_이용건수")

    summary = pd.DataFrame([
        {"구분": "오전첨두", "시간": f"{am_start:02d}:00-{am_start + PEAK_WINDOW:02d}:00",
         "이용건수": am_sum, "집중률_%": round(am_sum / total * 100, 2)},
        {"구분": "오후첨두", "시간": f"{pm_start:02d}:00-{pm_start + PEAK_WINDOW:02d}:00",
         "이용건수": pm_sum, "집중률_%": round(pm_sum / total * 100, 2)},
        {"구분": "첨두합계(4시간)", "시간": "-",
         "이용건수": am_sum + pm_sum, "집중률_%": round((am_sum + pm_sum) / total * 100, 2)},
        {"구분": "참고: 균등분포시 2시간 비중", "시간": "-",
         "이용건수": None, "집중률_%": round(PEAK_WINDOW / hourly.gt(0).sum() * 100, 2)},
    ])
    save_csv(summary, "02_첨두시간_집중률", index=False)

    print("=== 1. 시간대별 이용 건수 ===")
    print(table, end="\n\n")
    print(summary, end="\n\n")
    return table


def route_type_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """2. 노선유형별 × 시간대 이용 분포 (건수 및 유형 내 비중)."""
    counts = pd.crosstab(df["승차시"], df["노선유형"]).reindex(HOURS, fill_value=0)
    counts.index.name = "시간대"
    share = (counts / counts.sum() * 100).round(2)
    save_csv(counts, "03_노선유형별_시간대_건수")
    save_csv(share, "04_노선유형별_시간대_비중")

    peak = pd.DataFrame({
        "피크시간대": counts.idxmax(),
        "피크건수": counts.max(),
        "피크비중_%": share.max(),
        "총건수": counts.sum(),
    })
    save_csv(peak, "05_노선유형별_피크시간")
    print("=== 2. 노선유형별 피크 시간대 ===")
    print(peak, end="\n\n")
    return share


def user_type_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """3. 이용자구분별 시간대 분포 차이."""
    counts = pd.crosstab(df["승차시"], df["이용자구분"]).reindex(HOURS, fill_value=0)
    counts.index.name = "시간대"
    share = (counts / counts.sum() * 100).round(2)
    save_csv(counts, "06_이용자구분별_시간대_건수")
    save_csv(share, "07_이용자구분별_시간대_비중")

    # 일반 대비 비중 차이(%p): 어느 시간대에 상대적으로 몰리는지
    diff = share.sub(share["일반"], axis=0).drop(columns="일반").round(2)
    save_csv(diff, "08_이용자구분별_일반대비_비중차이_pp")

    top2 = {}
    for col in counts.columns:
        hours = counts[col].nlargest(2).index.tolist()
        top2[col] = ", ".join(f"{h:02d}시" for h in hours)

    am = list(range(7, 10))
    pm = list(range(17, 20))
    peak = pd.DataFrame({
        "피크시간대": counts.idxmax(),
        "상위2시간대": pd.Series(top2),
        "피크비중_%": share.max(),
        "오전7-9시_비중_%": share.loc[am].sum().round(2),
        "오후17-19시_비중_%": share.loc[pm].sum().round(2),
        "낮10-16시_비중_%": share.loc[10:16].sum().round(2),
        "총건수": counts.sum(),
    })
    save_csv(peak, "09_이용자구분별_피크시간")
    print("=== 3. 이용자구분별 피크 시간대 ===")
    print(peak, end="\n\n")
    return share


def ride_time_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """4. 시간대별 평균 탑승시간(분), 하차 결측 행 제외."""
    valid = df.dropna(subset=["하차일시"]).copy()
    valid["탑승시간_분"] = (valid["하차일시"] - valid["승차일시"]).dt.total_seconds() / 60
    table = (
        valid.groupby("승차시")["탑승시간_분"]
        .agg(건수="count", 평균="mean", 중앙값="median", 최대="max")
        .reindex(HOURS)
        .round(1)
    )
    table.index.name = "시간대"
    save_csv(table, "10_시간대별_평균탑승시간")

    by_type = valid.pivot_table(index="승차시", columns="노선유형",
                                values="탑승시간_분", aggfunc="mean").reindex(HOURS).round(1)
    by_type.index.name = "시간대"
    save_csv(by_type, "11_노선유형별_시간대_평균탑승시간")

    print(f"=== 4. 시간대별 평균 탑승시간 (하차 결측 {len(df) - len(valid)}건 제외) ===")
    print(f"전체 평균: {valid['탑승시간_분'].mean():.1f}분")
    print(table, end="\n\n")
    return table


def load_per_run(df: pd.DataFrame, routes: pd.DataFrame, peak_hours: list[int]) -> pd.DataFrame:
    """5. 노선별 시간당 수요 ÷ 시간당 운행 횟수 → 회당 평균 승객 수."""
    demand = pd.crosstab(df["노선ID"], df["승차시"]).reindex(columns=HOURS, fill_value=0)
    info = routes.set_index("노선ID")
    runs_per_hour = 60 / info["배차간격_분"]

    per_run = demand.div(runs_per_hour, axis=0).round(2)
    per_run.columns.name = "시간대"
    per_run.insert(0, "노선번호", info["노선번호"])
    save_csv(per_run, "12_노선별_시간대_회당승객수")

    peak_demand = demand[peak_hours].mean(axis=1)
    offpeak_hours = [h for h in range(10, 17) if h not in peak_hours]
    offpeak_demand = demand[offpeak_hours].mean(axis=1)

    table = pd.DataFrame({
        "노선번호": info["노선번호"],
        "노선유형": info["노선유형"],
        "배차간격_분": info["배차간격_분"],
        "시간당운행횟수": runs_per_hour.round(2),
        "일수요": demand.sum(axis=1),
        "최대수요시간대": demand.idxmax(axis=1),
        "최대시간당수요": demand.max(axis=1),
        "첨두시간당평균수요": peak_demand.round(1),
        "첨두회당평균승객": (peak_demand / runs_per_hour).round(2),
        "낮시간당평균수요": offpeak_demand.round(1),
        "낮회당평균승객": (offpeak_demand / runs_per_hour).round(2),
        "최대시회당승객": (demand.max(axis=1) / runs_per_hour).round(2),
    })
    table.index.name = "노선ID"
    table = table.sort_values("첨두회당평균승객", ascending=False)
    save_csv(table, "13_노선별_첨두시_회당평균승객")

    hours_txt = ", ".join(f"{h:02d}시" for h in peak_hours)
    print(f"=== 5. 노선별 첨두시({hours_txt}) 회당 평균 승객 수 ===")
    print(table, end="\n\n")
    return table


def draw_charts(hourly: pd.DataFrame, user_share: pd.DataFrame) -> None:
    """matplotlib가 있으면 PNG 차트 2개 저장."""
    if not HAS_MPL:
        print("matplotlib 미설치 → 차트 생략\n")
        return

    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = ["#d62728" if p else "#4c72b0" for p in hourly["첨두구분"]]
    ax.bar(hourly.index, hourly["이용건수"], color=colors)
    ax.set_xticks(HOURS)
    ax.set_xlabel("승차 시간대")
    ax.set_ylabel("이용 건수")
    ax.set_title("시간대별 버스 이용 건수 (빨강: 첨두 2시간)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "chart_시간대별_이용건수.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for col in user_share.columns:
        ax.plot(user_share.index, user_share[col], marker="o", ms=3, label=str(col))
    ax.set_xticks(HOURS)
    ax.set_xlabel("승차 시간대")
    ax.set_ylabel("구분 내 비중(%)")
    ax.set_title("이용자구분별 시간대 분포")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "chart_이용자구분별_시간대분포.png", dpi=120)
    plt.close(fig)
    print("차트 2개 저장 완료\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)

    routes, _ = load_routes()
    alighting = load_alighting()

    df = alighting.merge(routes[["노선ID", "노선번호", "노선유형"]], on="노선ID", how="left")
    df["승차시"] = df["승차일시"].dt.hour
    df["이용자구분"] = df["이용자구분"].astype(str)

    print(f"분석 대상: {len(df)}건, 승차일 {df['승차일시'].dt.date.min()}"
          f" ~ {df['승차일시'].dt.date.max()}\n")

    hourly = hourly_counts(df)
    route_type_by_hour(df)
    user_share = user_type_by_hour(df)
    ride_time_by_hour(df)
    peak_hours = hourly.index[hourly["첨두구분"] != ""].tolist()
    load_per_run(df, routes, peak_hours)
    draw_charts(hourly, user_share)

    print(f"결과 저장 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
