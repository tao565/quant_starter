"""
多因子选股回测 —— 动量轮动策略。

逻辑很简单：
  1. 拿一个股票池（沪深300里挑了40只蓝筹，各行各业的）
  2. 每个月算一遍每只股票的动量（过去1/3/6个月的涨幅）
  3. 综合打分排名，买最强的N只，等权持有
  4. 下个月重新排名、换仓
  5. 跟"全部等权持有"比，看有没有超额收益

跑法：
  python multi_factor.py           # 默认Top10
  python multi_factor.py --top 5   # Top5
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

from fetch_data import fetch_stock_daily, save_to_csv, DATA_DIR

# ---- 股票池 ----
POOL = [
    "000001", "600036", "601318", "600030", "000002",   # 金融
    "600519", "000858", "002304", "600887", "000568",   # 消费
    "600276", "000538", "300015", "002001", "600085",   # 医药
    "002415", "300750", "000725", "688981", "002230",   # 科技
    "600031", "000338", "002594", "601012", "600585",   # 制造
    "601857", "600028", "000630", "600900", "600809",   # 能源
    "601111", "600029", "600009", "600048", "001979",   # 交通地产
    "600050", "688111", "300124", "002714", "601899",   # 其他
]

# ---- 因子权重（默认纯动量，可以自己调）----
# 正数=越大越好，负数=越小越好
FACTOR_WEIGHTS = {
    "mom_1m": 0.33,         # 1个月动量
    "mom_3m": 0.33,         # 3个月动量
    "mom_6m": 0.34,         # 6个月动量
    "volatility": 0.0,       # 波动率（负=低波好）
    "reversal": 0.0,         # 短期反转（负=抄底）
    "turnover_change": 0.0,  # 换手率变化
    "rsi": 0.0,              # RSI（负=避开超买）
}


def calc_factors(df: pd.DataFrame) -> dict | None:
    """从日线数据算因子，返回dict或None（数据不够）"""
    close = df["close"]
    if len(close) < 130:
        return None

    f = {}
    f["mom_1m"] = close.iloc[-1] / close.iloc[-21] - 1
    f["mom_3m"] = close.iloc[-1] / close.iloc[-63] - 1
    f["mom_6m"] = close.iloc[-1] / close.iloc[-126] - 1

    ret = close.pct_change().dropna()
    f["volatility"] = ret.iloc[-20:].std() if len(ret) >= 20 else 1

    f["reversal"] = close.iloc[-1] / close.iloc[-5] - 1 if len(close) >= 5 else 0

    # 换手率变化
    vol = df["volume"].replace(0, np.nan)
    amt = df["amount"]
    to = amt / (close * vol)
    to = to.replace([np.inf, -np.inf], np.nan)
    if len(to) >= 30:
        f["turnover_change"] = to.iloc[-10:].mean() / to.iloc[-20:-10].mean() - 1
    else:
        f["turnover_change"] = 0

    # RSI 14日
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
    f["rsi"] = 100 - 100 / (1 + gain / loss) if loss > 0 else 50

    return f


def _zscore(series: pd.Series) -> pd.Series:
    """Z-score标准化"""
    s = series.std()
    return (series - series.mean()) / s if s > 0 else pd.Series(0.0, index=series.index)


def rank(all_factors: dict, weights: dict = None) -> pd.Series:
    """多因子打分排名，返回从高到低排好的Series"""
    if weights is None:
        weights = FACTOR_WEIGHTS

    df = pd.DataFrame(all_factors).T
    score = pd.Series(0.0, index=df.index)

    for name, w in weights.items():
        if name in df.columns and w != 0:
            score += _zscore(df[name]) * w

    return score.sort_values(ascending=False)


def backtest(pool, top_n=10, start="2020-01-01", end="2025-12-31", freq=21):
    """主函数：拉数据→逐期打分换仓→算收益→画图"""
    print(f"股票池{len(pool)}只 | Top{top_n} | 月频调仓 | {start[:4]}-{end[:4]}\n")

    # ---- 拉数据 ----
    data = {}
    for code in pool:
        try:
            path = DATA_DIR / f"{code}.csv"
            if path.exists():
                df = pd.read_csv(path, parse_dates=["date"])
            else:
                df = fetch_stock_daily(code, start, end)
                save_to_csv(df, code)
            if len(df) > 130:
                data[code] = df
        except Exception:
            pass

    print(f"有效股票: {len(data)}只（部分新股/数据异常的跳过了）")

    # ---- 调仓日 ----
    sample_dates = sorted(list(data.values())[0]["date"].unique())
    rebal_dates = sample_dates[freq::freq]

    # ---- 逐期回测 ----
    strat_rets = []
    bench_rets = []

    for i, today in enumerate(rebal_dates):
        if i + 1 >= len(rebal_dates):
            break
        next_day = rebal_dates[i + 1]

        # 算因子（只用今天之前的数据，防未来信息泄露）
        factors = {}
        valid = []
        for code, df_all in data.items():
            df_slice = df_all[df_all["date"] <= today]
            f = calc_factors(df_slice)
            if f is not None:
                factors[code] = f
                valid.append(code)

        if len(valid) < top_n:
            continue

        # 排名、挑Top N
        scores = rank(factors)
        picks = scores.index[:top_n].tolist()

        # 算这期收益率
        s_ret = 0.0
        cnt = 0
        for code in picks:
            chunk = data[code]
            chunk = chunk[(chunk["date"] >= today) & (chunk["date"] <= next_day)]
            if len(chunk) >= 2:
                s_ret += chunk["close"].iloc[-1] / chunk["close"].iloc[0] - 1
                cnt += 1
        strat_rets.append(s_ret / cnt if cnt else 0)

        # 基准（全部等权）
        b_ret = 0.0
        bc = 0
        for code in valid:
            chunk = data[code]
            chunk = chunk[(chunk["date"] >= today) & (chunk["date"] <= next_day)]
            if len(chunk) >= 2:
                b_ret += chunk["close"].iloc[-1] / chunk["close"].iloc[0] - 1
                bc += 1
        bench_rets.append(b_ret / bc if bc else 0)

    # ---- 算指标 ----
    strat_curve = np.cumprod([1] + [1 + r for r in strat_rets])
    bench_curve = np.cumprod([1] + [1 + r for r in bench_rets])
    dates = [rebal_dates[0]] + [rebal_dates[i + 1] for i in range(len(strat_rets))]

    strat_total = (strat_curve[-1] - 1) * 100
    bench_total = (bench_curve[-1] - 1) * 100
    alpha = strat_total - bench_total

    years = len(strat_curve) * 21 / 252
    strat_ann = ((strat_curve[-1]) ** (1 / years) - 1) * 100
    bench_ann = ((bench_curve[-1]) ** (1 / years) - 1) * 100

    peak = 1.0
    max_dd = 0.0
    for v in strat_curve:
        peak = max(peak, v)
        max_dd = min(max_dd, (v - peak) / peak * 100)

    wins = sum(1 for s, b in zip(strat_rets, bench_rets) if s > b)
    win_rate = wins / len(strat_rets) * 100

    print(f"策略: {strat_total:+.2f}%  基准: {bench_total:+.2f}%  Alpha: {alpha:+.2f}%")
    print(f"年化: {strat_ann:+.2f}% / {bench_ann:+.2f}%  回撤: {max_dd:+.2f}%  胜率: {win_rate:.0f}%")
    print(f"调仓{len(strat_rets)}次\n")

    # ---- 画图 ----
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10),
                                    gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(dates, strat_curve, color="#F44336", lw=2, label=f"动量轮动 Top{top_n}")
    ax1.plot(dates, bench_curve, color="#999", lw=1, ls="--", label="全部等权")
    ax1.fill_between(dates, bench_curve, strat_curve,
                     where=strat_curve >= bench_curve,
                     color="#F44336", alpha=0.08)
    ax1.legend(loc="upper left", fontsize=10)
    ax1.set_ylabel("净值")
    ax1.grid(alpha=0.3)

    excess = strat_curve - bench_curve
    ax2.plot(dates, excess, color="#333", lw=1)
    ax2.fill_between(dates, 0, excess, where=excess >= 0, color="#F44336", alpha=0.2)
    ax2.fill_between(dates, 0, excess, where=excess < 0, color="#4CAF50", alpha=0.2)
    ax2.axhline(0, color="#999", ls="--", lw=0.8)
    ax2.set_ylabel("超额收益")
    ax2.set_xlabel("日期")
    ax2.grid(alpha=0.3)

    fig.suptitle(
        f"动量轮动 (Top{top_n}/{len(data)})  |  "
        f"{strat_total:+.1f}% vs {bench_total:+.1f}%  |  Alpha {alpha:+.1f}%  |  胜率{win_rate:.0f}%",
        fontsize=13, fontweight="bold")
    plt.tight_layout()

    path = Path(__file__).parent / "backtest_multi_factor.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"图已保存: {path}")


if __name__ == "__main__":
    top_n = 10
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
    backtest(POOL, top_n=top_n)
