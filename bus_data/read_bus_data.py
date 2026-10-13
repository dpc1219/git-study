"""버스 노선 / 하차 xlsx를 pandas로 읽어서 간단히 살펴보는 스크립트."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent


def load_routes(path: Path = DATA_DIR / "bus_routes.xlsx") -> tuple[pd.DataFrame, pd.DataFrame]:
    """노선정보, 노선정류장 시트를 읽어 반환한다."""
    sheets = pd.read_excel(
        path,
        sheet_name=["노선정보", "노선정류장"],
        dtype={"노선번호": str},  # '0101' 같은 번호가 숫자로 바뀌지 않도록
    )
    return sheets["노선정보"], sheets["노선정류장"]


def load_alighting(path: Path = DATA_DIR / "bus_alighting.xlsx") -> pd.DataFrame:
    """하차기록 시트를 읽고 일시 컬럼을 datetime으로 변환한다."""
    df = pd.read_excel(path, sheet_name="하차기록")
    for col in ["승차일시", "하차일시"]:
        df[col] = pd.to_datetime(df[col])
    df["이용자구분"] = df["이용자구분"].astype("category")
    return df


def main() -> None:
    routes, route_stops = load_routes()
    alighting = load_alighting()

    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)

    print("=== 노선정보 ===")
    print(routes, end="\n\n")

    print("=== 하차기록 (상위 5행) ===")
    print(alighting.head(), end="\n\n")
    alighting.info()
    print()

    # 하차 미태그 현황
    n_missing = alighting["하차정류장ID"].isna().sum()
    print(f"하차 미태그: {n_missing}건 ({n_missing / len(alighting):.1%})\n")

    # 정류장명 붙이기: 노선ID + 정류장ID 기준으로 노선정류장과 조인
    stop_names = route_stops[["노선ID", "정류장ID", "정류장명", "정류장순번"]]
    merged = (
        alighting
        .merge(routes[["노선ID", "노선번호", "노선유형"]], on="노선ID", how="left")
        .merge(stop_names.add_prefix("하차_"), left_on=["노선ID", "하차정류장ID"],
               right_on=["하차_노선ID", "하차_정류장ID"], how="left")
        .drop(columns=["하차_노선ID", "하차_정류장ID"])
    )

    print("=== 노선별 하차 건수 ===")
    print(merged.groupby(["노선번호", "노선유형"])["하차정류장ID"].count()
          .sort_values(ascending=False), end="\n\n")

    print("=== 하차 상위 10개 정류장 ===")
    print(merged["하차_정류장명"].value_counts().head(10), end="\n\n")

    print("=== 시간대별 하차 건수 ===")
    print(merged["하차일시"].dropna().dt.hour.value_counts().sort_index(), end="\n\n")

    merged["탑승시간_분"] = (merged["하차일시"] - merged["승차일시"]).dt.total_seconds() / 60
    print("=== 노선유형별 평균 탑승시간(분) ===")
    print(merged.groupby("노선유형")["탑승시간_분"].mean().round(1))


if __name__ == "__main__":
    main()
