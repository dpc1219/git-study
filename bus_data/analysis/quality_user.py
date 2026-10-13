"""버스 교통카드 데이터 품질(하차 미태그) 및 이용자 행태 분석 스크립트.

분석 항목
1. 데이터 품질 점검 : 컬럼별 결측, 중복 행, 시각 논리 오류, 노선-정류장 정합성, 탑승시간 이상치(IQR)
2. 하차 미태그 비교 : 노선·노선유형·시간대·이용자구분·환승여부별 미태그 비율 (+ 카이제곱 검정)
3. 카드 단위 행태   : 카드별 일 이용 횟수 분포, 1회/2회/3회 이상 비중, 첫~마지막 승차 간격
4. 이용자구분       : 구성비, 평균 탑승시간, 환승 비율
5. 통행사슬 점검     : 직전 하차정류장 = 다음 승차정류장 일치율

결과는 output/quality_user/ 에 CSV(utf-8-sig)로 저장하고,
matplotlib가 설치되어 있으면 PNG 차트도 함께 저장한다.
"""

import sys
from pathlib import Path

import pandas as pd

# 상위 폴더(bus_data)의 읽기 함수 재사용
BUS_DATA_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUS_DATA_DIR))
from read_bus_data import load_alighting, load_routes  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "output" / "quality_user"

# 선택 의존성: 없으면 해당 분석/차트를 건너뛴다
try:
    from scipy.stats import chi2_contingency
except ImportError:
    chi2_contingency = None

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
except ImportError:
    plt = None


def save_csv(df: pd.DataFrame, name: str, index: bool = False) -> None:
    """결과 표를 utf-8-sig CSV로 저장한다."""
    path = OUT_DIR / f"{name}.csv"
    df.to_csv(path, index=index, encoding="utf-8-sig")
    print(f"  [저장] {path.relative_to(BUS_DATA_DIR)}")


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# ---------------------------------------------------------------------------
# 0. 데이터 준비
# ---------------------------------------------------------------------------
def prepare() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    routes, route_stops = load_routes()
    df = load_alighting()
    df["이용자구분"] = df["이용자구분"].astype(str)

    # 노선 정보 결합
    df = df.merge(routes[["노선ID", "노선번호", "노선유형"]], on="노선ID", how="left")

    # 승차/하차 정류장 순번 결합 (노선에 없는 정류장이면 NaN)
    seq = route_stops[["노선ID", "정류장ID", "정류장순번"]]
    df = df.merge(seq.rename(columns={"정류장ID": "승차정류장ID", "정류장순번": "승차순번"}),
                  on=["노선ID", "승차정류장ID"], how="left")
    df = df.merge(seq.rename(columns={"정류장ID": "하차정류장ID", "정류장순번": "하차순번"}),
                  on=["노선ID", "하차정류장ID"], how="left")

    df["미태그"] = df["하차정류장ID"].isna() | df["하차일시"].isna()
    df["탑승시간_분"] = (df["하차일시"] - df["승차일시"]).dt.total_seconds() / 60
    df["승차시"] = df["승차일시"].dt.hour
    df["시간대"] = pd.cut(
        df["승차시"],
        bins=[-1, 6, 9, 16, 19, 24],
        labels=["새벽(~06시)", "오전첨두(07~09시)", "낮(10~16시)", "오후첨두(17~19시)", "저녁(20시~)"],
    )
    return routes, route_stops, df


# ---------------------------------------------------------------------------
# 1. 데이터 품질 점검
# ---------------------------------------------------------------------------
def check_quality(raw_cols: list[str], df: pd.DataFrame) -> pd.DataFrame:
    print_section("1. 데이터 품질 점검")
    n = len(df)

    # 1-1. 컬럼별 결측
    missing = pd.DataFrame({
        "컬럼": raw_cols,
        "결측건수": [int(df[c].isna().sum()) for c in raw_cols],
    })
    missing["결측비율"] = (missing["결측건수"] / n).round(4)
    print(missing.to_string(index=False))
    save_csv(missing, "01_컬럼별_결측")

    # 1-2. 품질 규칙별 위반 건수
    tagged = df[~df["미태그"]]
    ride = tagged["탑승시간_분"]
    q1, q3 = ride.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    df["탑승시간_이상치"] = (~df["미태그"]) & ((df["탑승시간_분"] < lower) | (df["탑승시간_분"] > upper))

    rules = {
        "완전 중복 행": df.duplicated(subset=raw_cols).sum(),
        "카드ID+승차일시 중복": df.duplicated(subset=["카드ID", "승차일시"]).sum(),
        "하차일시·하차정류장 중 하나만 결측": (df["하차일시"].isna() ^ df["하차정류장ID"].isna()).sum(),
        "하차일시 < 승차일시": (df["하차일시"] < df["승차일시"]).sum(),
        "하차일시 = 승차일시": (df["하차일시"] == df["승차일시"]).sum(),
        "승차정류장이 노선에 없음": df["승차순번"].isna().sum(),
        "하차정류장이 노선에 없음(태그건)": (~df["미태그"] & df["하차순번"].isna()).sum(),
        "하차순번 <= 승차순번": (df["하차순번"] <= df["승차순번"]).sum(),
        "승차일이 기준일(2026-10-12)과 다름": (df["승차일시"].dt.normalize() != pd.Timestamp("2026-10-12")).sum(),
        f"탑승시간 IQR 이상치(<{lower:.1f}분 또는 >{upper:.1f}분)": df["탑승시간_이상치"].sum(),
    }
    quality = pd.DataFrame({"점검항목": list(rules), "건수": [int(v) for v in rules.values()]})
    quality["비율"] = (quality["건수"] / n).round(4)
    print()
    print(quality.to_string(index=False))
    save_csv(quality, "02_품질규칙_위반")

    # 1-3. 탑승시간 기술통계 + IQR 경계
    desc = ride.describe(percentiles=[0.25, 0.5, 0.75, 0.95]).round(2).to_frame("탑승시간_분")
    desc.loc["IQR_하한"] = round(lower, 2)
    desc.loc["IQR_상한"] = round(upper, 2)
    print()
    print(desc.T.to_string())
    save_csv(desc.reset_index(names="통계량"), "03_탑승시간_기술통계")

    outliers = df[df["탑승시간_이상치"]].sort_values("탑승시간_분", ascending=False)
    save_csv(outliers[raw_cols + ["노선번호", "탑승시간_분"]], "04_탑승시간_이상치_목록")
    if len(outliers):
        print("\n이상치 노선 분포:", outliers["노선번호"].value_counts().to_dict())
    return quality


# ---------------------------------------------------------------------------
# 2. 하차 미태그 비교
# ---------------------------------------------------------------------------
def compare_untagged(df: pd.DataFrame) -> pd.DataFrame:
    print_section("2. 하차 미태그 비율 비교")
    overall = df["미태그"].mean()
    print(f"전체 미태그: {df['미태그'].sum()}건 / {len(df)}건 ({overall:.2%})")

    dims = {
        "노선": "노선번호",
        "노선유형": "노선유형",
        "시간대": "시간대",
        "이용자구분": "이용자구분",
        "환승여부": "환승여부",
    }
    tables, tests = [], []
    for label, col in dims.items():
        g = (df.groupby(col, observed=True)["미태그"]
             .agg(전체건수="size", 미태그건수="sum").reset_index()
             .rename(columns={col: "구분값"}))
        g["미태그비율"] = (g["미태그건수"] / g["전체건수"]).round(4)
        g["전체대비_차이_pp"] = ((g["미태그비율"] - overall) * 100).round(2)
        g.insert(0, "비교축", label)
        tables.append(g)

        test = {"비교축": label, "범주수": len(g)}
        if chi2_contingency is not None:
            ct = pd.crosstab(df[col], df["미태그"])
            chi2, p, dof, expected = chi2_contingency(ct)
            test.update({"카이제곱": round(chi2, 3), "자유도": dof, "p값": round(p, 4),
                         "기대빈도5미만_셀비율": round((expected < 5).mean(), 3),
                         "유의(5%)": "Y" if p < 0.05 else "N"})
        tests.append(test)

    result = pd.concat(tables, ignore_index=True)
    print(result.to_string(index=False))
    save_csv(result, "05_미태그비율_비교")

    test_df = pd.DataFrame(tests)
    print()
    if chi2_contingency is None:
        print("scipy 미설치 → 카이제곱 검정 생략")
    else:
        print(test_df.to_string(index=False))
    save_csv(test_df, "06_미태그_카이제곱검정")
    return result


# ---------------------------------------------------------------------------
# 3. 카드 단위 이용 행태
# ---------------------------------------------------------------------------
def card_behavior(df: pd.DataFrame) -> pd.DataFrame:
    print_section("3. 카드 단위 이용 행태")
    card = df.groupby("카드ID").agg(
        이용횟수=("승차일시", "size"),
        첫승차=("승차일시", "min"),
        마지막승차=("승차일시", "max"),
        이용노선수=("노선ID", "nunique"),
    )
    card["첫_마지막_간격_시간"] = ((card["마지막승차"] - card["첫승차"]).dt.total_seconds() / 3600).round(2)
    print(f"카드 수: {len(card)}개, 카드당 평균 이용: {card['이용횟수'].mean():.2f}회 "
          f"(중앙값 {card['이용횟수'].median():.0f}, 최대 {card['이용횟수'].max()})")

    # 3-1. 이용 횟수 분포
    dist = card["이용횟수"].value_counts().sort_index().rename_axis("일_이용횟수").reset_index(name="카드수")
    dist["카드비율"] = (dist["카드수"] / len(card)).round(4)
    save_csv(dist, "07_카드별_이용횟수_분포")

    # 3-2. 1회 / 2회 / 3회 이상 비중
    grp = pd.cut(card["이용횟수"], bins=[0, 1, 2, float("inf")], labels=["1회", "2회", "3회 이상"])
    share = card.groupby(grp, observed=False).agg(카드수=("이용횟수", "size"), 통행수=("이용횟수", "sum"))
    share["카드비중"] = (share["카드수"] / share["카드수"].sum()).round(4)
    share["통행비중"] = (share["통행수"] / share["통행수"].sum()).round(4)
    share = share.rename_axis("이용횟수구간").reset_index()
    print(share.to_string(index=False))
    save_csv(share, "08_이용횟수구간_비중")

    # 3-3. 다회 이용 카드의 첫~마지막 승차 간격
    multi = card[card["이용횟수"] >= 2]
    span = multi["첫_마지막_간격_시간"].describe(percentiles=[0.25, 0.5, 0.75]).round(2)
    span_bins = pd.cut(multi["첫_마지막_간격_시간"], bins=[-0.01, 1, 3, 6, 9, 12, 24],
                       labels=["1시간 이하", "1~3시간", "3~6시간", "6~9시간", "9~12시간", "12시간 초과"])
    span_dist = span_bins.value_counts().sort_index().rename_axis("간격구간").reset_index(name="카드수")
    span_dist["비율"] = (span_dist["카드수"] / len(multi)).round(4)
    print(f"\n다회 이용 카드 {len(multi)}개의 첫~마지막 승차 간격(시간)")
    print(span.to_frame().T.to_string(index=False))
    print(span_dist.to_string(index=False))
    save_csv(span.to_frame("값").reset_index(names="통계량"), "09_다회이용_승차간격_기술통계")
    save_csv(span_dist, "10_다회이용_승차간격_분포")
    save_csv(card.reset_index(), "11_카드별_요약")
    return card


# ---------------------------------------------------------------------------
# 4. 이용자구분별 특성
# ---------------------------------------------------------------------------
def user_type_profile(df: pd.DataFrame) -> pd.DataFrame:
    print_section("4. 이용자구분별 특성")
    prof = df.groupby("이용자구분").agg(
        통행수=("카드ID", "size"),
        카드수=("카드ID", "nunique"),
        평균탑승시간_분=("탑승시간_분", "mean"),
        중앙탑승시간_분=("탑승시간_분", "median"),
        환승비율=("환승여부", lambda s: (s == "Y").mean()),
        미태그비율=("미태그", "mean"),
    )
    prof.insert(1, "구성비", prof["통행수"] / prof["통행수"].sum())
    prof = prof.round(4).sort_values("통행수", ascending=False).reset_index()
    print(prof.to_string(index=False))
    save_csv(prof, "12_이용자구분별_특성")

    # 카드 하나에 여러 이용자구분이 섞여 있는지(일관성) 점검
    mixed = (df.groupby("카드ID")["이용자구분"].nunique() > 1).sum()
    print(f"\n이용자구분이 2개 이상 섞인 카드: {mixed}개 / {df['카드ID'].nunique()}개")
    return prof


# ---------------------------------------------------------------------------
# 5. 통행사슬 점검 (직전 하차정류장 = 다음 승차정류장)
# ---------------------------------------------------------------------------
def trip_chain(df: pd.DataFrame) -> pd.DataFrame:
    print_section("5. 통행사슬 점검 (직전 하차 = 다음 승차)")
    s = df.sort_values(["카드ID", "승차일시"]).copy()
    g = s.groupby("카드ID")
    s["다음승차정류장ID"] = g["승차정류장ID"].shift(-1)
    s["다음승차일시"] = g["승차일시"].shift(-1)
    s["다음환승여부"] = g["환승여부"].shift(-1)
    pairs = s[s["다음승차정류장ID"].notna()].copy()
    pairs["다음승차까지_분"] = (pairs["다음승차일시"] - pairs["하차일시"]).dt.total_seconds() / 60

    valid = pairs[~pairs["미태그"]].copy()  # 직전 하차가 태그된 연결만 비교 가능
    valid["일치"] = valid["하차정류장ID"] == valid["다음승차정류장ID"]

    # 랜덤 기준선: 다음 승차정류장을 무작위로 섞었을 때 기대 일치율
    shuffled = valid["다음승차정류장ID"].sample(frac=1, random_state=0).to_numpy()
    baseline = (valid["하차정류장ID"].to_numpy() == shuffled).mean()

    rows = [
        {"구분": "전체 연속통행 쌍", "쌍수": len(pairs), "비교가능(직전하차 태그)": len(valid),
         "일치건수": int(valid["일치"].sum()), "일치율": valid["일치"].mean()},
    ]
    # 30분 이내 재승차(환승 가능 구간)만 따로
    within = valid[valid["다음승차까지_분"].between(0, 30)]
    rows.append({"구분": "하차 후 30분 이내 재승차", "쌍수": len(within), "비교가능(직전하차 태그)": len(within),
                 "일치건수": int(within["일치"].sum()),
                 "일치율": within["일치"].mean() if len(within) else float("nan")})
    # 다음 통행이 환승(Y)으로 표시된 경우
    nxt_y = valid[valid["다음환승여부"] == "Y"]
    rows.append({"구분": "다음 통행 환승여부=Y", "쌍수": len(nxt_y), "비교가능(직전하차 태그)": len(nxt_y),
                 "일치건수": int(nxt_y["일치"].sum()),
                 "일치율": nxt_y["일치"].mean() if len(nxt_y) else float("nan")})
    rows.append({"구분": "랜덤 기준선(셔플)", "쌍수": len(valid), "비교가능(직전하차 태그)": len(valid),
                 "일치건수": int(round(baseline * len(valid))), "일치율": baseline})
    result = pd.DataFrame(rows)
    result["일치율"] = result["일치율"].round(4)
    print(result.to_string(index=False))

    # 하차 미태그 건 중 다음 승차가 있어 사슬 보정 후보가 되는 비율
    untag = s[s["미태그"]]
    cand = untag["다음승차정류장ID"].notna().mean()
    print(f"\n미태그 {len(untag)}건 중 같은 카드의 다음 승차가 존재(사슬 보정 후보): {cand:.2%}")
    result.loc[len(result)] = {"구분": "미태그 중 다음 승차 존재 비율", "쌍수": len(untag),
                               "비교가능(직전하차 태그)": None, "일치건수": int(untag["다음승차정류장ID"].notna().sum()),
                               "일치율": round(cand, 4)}

    # 다음 승차까지 시간 분포 (음수 = 하차 전에 다음 승차 → 논리 충돌)
    neg = (valid["다음승차까지_분"] < 0).sum()
    print(f"직전 하차일시보다 다음 승차일시가 빠른 연결(시간 겹침): {neg}건 / {len(valid)}건")
    result.loc[len(result)] = {"구분": "직전 하차보다 다음 승차가 빠름(겹침)", "쌍수": len(valid),
                               "비교가능(직전하차 태그)": len(valid), "일치건수": int(neg),
                               "일치율": round(neg / len(valid), 4) if len(valid) else None}
    save_csv(result, "13_통행사슬_일치율")
    save_csv(pairs[["카드ID", "노선번호", "승차일시", "승차정류장ID", "하차일시", "하차정류장ID",
                    "다음승차일시", "다음승차정류장ID", "다음환승여부", "다음승차까지_분"]],
             "14_연속통행_쌍_목록")
    return result


# ---------------------------------------------------------------------------
# 6. 차트 (matplotlib 있을 때만)
# ---------------------------------------------------------------------------
def draw_charts(untag: pd.DataFrame, card: pd.DataFrame) -> None:
    if plt is None:
        print("\nmatplotlib 미설치 → 차트 생략")
        return
    print_section("6. 차트 저장")
    overall = untag.iloc[0]["미태그비율"] - untag.iloc[0]["전체대비_차이_pp"] / 100

    # 6-1. 비교축별 미태그 비율
    axes_list = untag["비교축"].unique()
    fig, axes = plt.subplots(1, len(axes_list), figsize=(4 * len(axes_list), 4), sharey=True)
    for ax, key in zip(axes, axes_list):
        sub = untag[untag["비교축"] == key]
        ax.bar(sub["구분값"].astype(str), sub["미태그비율"] * 100, color="#4C78A8")
        ax.axhline(overall * 100, color="#999999", linestyle="--", linewidth=1)
        ax.set_title(key)
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    axes[0].set_ylabel("하차 미태그 비율(%)")
    fig.suptitle("구분별 하차 미태그 비율 (점선: 전체 평균)")
    fig.tight_layout()
    path = OUT_DIR / "미태그비율_비교.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"  [저장] {path.relative_to(BUS_DATA_DIR)}")

    # 6-2. 카드별 일 이용횟수 분포
    dist = card["이용횟수"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(dist.index.astype(str), dist.values, color="#4C78A8")
    ax.set_xlabel("일 이용횟수")
    ax.set_ylabel("카드 수")
    ax.set_title("카드별 일 이용횟수 분포")
    fig.tight_layout()
    path = OUT_DIR / "카드별_이용횟수_분포.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"  [저장] {path.relative_to(BUS_DATA_DIR)}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)

    raw_cols = list(load_alighting().columns)
    _, _, df = prepare()
    print(f"하차기록 {len(df)}행 로드, 승차일시 범위: {df['승차일시'].min()} ~ {df['승차일시'].max()}")

    check_quality(raw_cols, df)
    untag = compare_untagged(df)
    card = card_behavior(df)
    user_type_profile(df)
    trip_chain(df)
    draw_charts(untag, card)
    print(f"\n완료: 결과 폴더 {OUT_DIR}")


if __name__ == "__main__":
    main()
