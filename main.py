"""
量化入门 —— 多策略回测 + 市场分析。

用法：
    python main.py                          # 默认：平安银行，RSI均值回归
    python main.py -s macd 600519           # 茅台，MACD 策略
    python main.py -s ma 000001             # 平安银行，双均线
    python main.py -s rsi 510050            # 上证50 ETF，RSI均值回归

策略：
    ma   - 双均线金叉死叉（5/20日）
    macd  - MACD 金叉死叉（区分水上水下）
    rsi   - RSI 均值回归（30超卖买，70超买卖）
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

import sys
import argparse
from pathlib import Path

import backtrader as bt
import pandas as pd
import numpy as np

from fetch_data import fetch_stock_daily, save_to_csv, DATA_DIR, fetch_north_bound_holdings
from indicators import calc_macd, check_volume_shrink, estimate_big_order_flow, big_money_summary

# ---- 策略注册表 ----
STRATEGIES = {
    "ma": ("strategies.dual_ma", "DualMAStrategy", "双均线交叉"),
    "macd": ("strategies.macd_strategy", "MACDStrategy", "MACD 金叉死叉"),
    "rsi": ("strategies.rsi_mean_revert", "RSIMeanRevertStrategy", "RSI 均值回归"),
    "tt": ("strategies.turtle_trading", "TurtleStrategy", "海龟交易法则"),
    "dm": ("strategies.dual_momentum", "DualMomentumStrategy", "双动量策略"),
}

INITIAL_CASH = 100_000
COMMISSION = 0.0003
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"


class EquityTracker(bt.analyzers.Analyzer):
    def start(self):
        self.equity = []
    def next(self):
        self.equity.append((self.data.datetime.date(0), self.strategy.broker.getvalue()))
    def get_analysis(self):
        return self.equity


def get_data(symbol: str) -> pd.DataFrame:
    csv_path = DATA_DIR / f"{symbol}.csv"
    if csv_path.exists():
        print(f"[数据] 从本地加载 {csv_path}")
        return pd.read_csv(csv_path, parse_dates=["date"])
    else:
        print(f"[数据] 从 baostock 拉取 {symbol} ...")
        df = fetch_stock_daily(symbol, start=START_DATE, end=END_DATE)
        save_to_csv(df, symbol)
        return df


def print_market_report(df: pd.DataFrame, symbol: str):
    """打印市场分析报告：MACD 状态、缩量、大单资金、北向资金"""
    close = df["close"]
    volume = df["volume"]

    # MACD
    macd_df = calc_macd(close)
    latest_macd = macd_df.iloc[-1]
    dif, dea, hist = latest_macd["DIF"], latest_macd["DEA"], latest_macd["MACD"]
    macd_position = "水上（多头）" if hist > 0 else "水下（空头）"
    macd_trend = "向上" if dif > macd_df.iloc[-2]["DIF"] else "向下"

    # 缩量
    shrink = check_volume_shrink(volume)

    # 大单资金
    df_big = estimate_big_order_flow(df.copy())
    money = big_money_summary(df_big)

    # 北向资金
    north = fetch_north_bound_holdings(symbol)

    print(f"\n{'=' * 60}")
    print(f"  {symbol} 市场分析报告（{df['date'].iloc[-1].date()}）")
    print(f"{'=' * 60}")
    print(f"  MACD 指标")
    print(f"    DIF={dif:.4f}  DEA={dea:.4f}  柱={hist:.4f}")
    print(f"    状态: {macd_position}  趋势: {macd_trend}")
    print(f"  ──────────────────")
    print(f"  成交量分析（近 10 日 vs 前 20 日）")
    print(f"    近10日均量: {shrink['recent_avg']:,.0f}")
    print(f"    前20日均量: {shrink['prev_avg']:,.0f}")
    print(f"    缩量比例: {shrink['ratio']:.2f}  {'[!!!] 明显缩量' if shrink['shrinking'] else '量能正常'}")
    print(f"  ──────────────────")
    print(f"  大单资金流向（近20日估算）")
    print(f"    净流向: {money['net_flow']:,.0f}  ({money['flow_pct']:+.2f}%)")
    print(f"    方向: {money['direction']}  (买入{money['buy_days']}天 / 卖出{money['sell_days']}天)")
    print(f"  ──────────────────")
    if north:
        print(f"  北向资金（外资）")
        print(f"    日期: {north.get('date', 'N/A')}")
        print(f"    持股比例: {north.get('hold_ratio', 0):.2f}%")
        print(f"    持股市值: {north.get('hold_value', 0)/1e8:.2f} 亿")
    else:
        print(f"  北向资金: 暂无数据")
    print(f"{'=' * 60}")


def run_backtest(df: pd.DataFrame, strategy_key: str, symbol: str):
    """通用回测引擎"""
    cerebro = bt.Cerebro()

    data = bt.feeds.PandasData(
        dataname=df, datetime="date",
        open="open", high="high", low="low", close="close", volume="volume",
    )
    cerebro.adddata(data)

    # 动态加载策略
    mod_path, class_name, display_name = STRATEGIES[strategy_key]
    mod = __import__(mod_path, fromlist=[class_name])
    StrategyClass = getattr(mod, class_name)
    cerebro.addstrategy(StrategyClass)
    cerebro.addanalyzer(EquityTracker, _name="equity")
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)

    start_value = cerebro.broker.getvalue()
    avg_price = df["close"].mean()

    print(f"\n{'=' * 55}")
    print(f"  股票: {symbol}  |  策略: {display_name}")
    print(f"  初始资金: {start_value:,.0f}  |  均价: {avg_price:.2f}")
    print(f"{'=' * 55}")

    result = cerebro.run()
    strat = result[0]

    end_value = cerebro.broker.getvalue()
    total_return = (end_value / start_value - 1) * 100

    equity = strat.analyzers.equity.get_analysis()
    dates = [e[0] for e in equity]
    values = [e[1] for e in equity]

    peak = values[0]
    max_drawdown = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100
        if dd < max_drawdown:
            max_drawdown = dd

    years = len(values) / 252
    annual_return = ((end_value / start_value) ** (1 / years) - 1) * 100 if years > 0 else 0

    print(f"\n{'=' * 55}")
    print(f"  最终资金:    {end_value:,.2f}")
    print(f"  总收益率:    {total_return:+.2f}%")
    print(f"  年化收益率:  {annual_return:+.2f}%")
    print(f"  最大回撤:    {max_drawdown:+.2f}%")
    print(f"  交易次数:    {strat.trade_count}")
    print(f"{'=' * 55}")

    # ============================================================
    # 画图：四面板 — 价格+均线 / MACD / 成交量 / 资金曲线
    # ============================================================
    close = df["close"].values[-len(dates):]
    volume = df["volume"].values[-len(dates):]

    fig, axes = plt.subplots(4, 1, figsize=(18, 14),
                              gridspec_kw={"height_ratios": [3, 1.5, 1, 1.5]})
    ax_price, ax_macd, ax_vol, ax_eq = axes

    # --- 面板 1: 价格 ---
    ax_price.plot(dates, close, label="收盘价", color="#333", linewidth=1, alpha=0.7)
    ax_price.set_ylabel("价格 (元)")
    ax_price.legend(loc="upper left")
    ax_price.grid(True, alpha=0.3)

    # 买卖点
    if hasattr(strat, "trade_log"):
        buy_dates = [t[0] for t in strat.trade_log if t[2] in ("buy",)]
        buy_prices = [t[1] for t in strat.trade_log if t[2] in ("buy",)]
        sell_dates = [t[0] for t in strat.trade_log if t[2] in ("sell",)]
        sell_prices = [t[1] for t in strat.trade_log if t[2] in ("sell",)]
        if buy_dates:
            ax_price.scatter(buy_dates, buy_prices, marker="^", s=80,
                             color="red", zorder=5, label=f"买入({len(buy_dates)})")
        if sell_dates:
            ax_price.scatter(sell_dates, sell_prices, marker="v", s=80,
                             color="green", zorder=5, label=f"卖出({len(sell_dates)})")
        ax_price.legend(loc="upper left")

    # --- 面板 2: MACD ---
    macd_df = calc_macd(pd.Series(close))
    ax_macd.fill_between(dates, 0, macd_df["MACD"].values,
                          where=macd_df["MACD"].values >= 0,
                          color="#F44336", alpha=0.3, label="MACD柱(正)")
    ax_macd.fill_between(dates, 0, macd_df["MACD"].values,
                          where=macd_df["MACD"].values < 0,
                          color="#4CAF50", alpha=0.3, label="MACD柱(负)")
    ax_macd.plot(dates, macd_df["DIF"].values, color="#2196F3", linewidth=0.8, label="DIF")
    ax_macd.plot(dates, macd_df["DEA"].values, color="#FF5722", linewidth=0.8, label="DEA")
    ax_macd.axhline(y=0, color="#999", linestyle="--", linewidth=0.5)
    ax_macd.set_ylabel("MACD")
    ax_macd.legend(loc="upper left", fontsize=7)
    ax_macd.grid(True, alpha=0.3)

    # --- 面板 3: 成交量 ---
    ax_vol.bar(dates, volume, color="#90CAF9", width=1, alpha=0.7)
    vol_ma20 = pd.Series(volume).rolling(20).mean()
    ax_vol.plot(dates, vol_ma20, color="#FF5722", linewidth=1, label="20日均量")
    ax_vol.set_ylabel("成交量")
    ax_vol.legend(loc="upper left")
    ax_vol.grid(True, alpha=0.3)

    # 缩量区间高亮
    shrink = check_volume_shrink(pd.Series(volume))
    if shrink["shrinking"]:
        recent_n = 10
        ax_vol.axvspan(dates[-recent_n], dates[-1], color="orange", alpha=0.15)
        ax_vol.text(dates[-recent_n], volume[-recent_n:].max() * 0.9,
                    "缩量区间", fontsize=9, color="orange", fontweight="bold")

    # --- 面板 4: 资金曲线 ---
    ax_eq.plot(dates, values, color="#4CAF50", linewidth=1.5)
    ax_eq.axhline(y=start_value, color="#999", linestyle="--", linewidth=0.8)
    ax_eq.fill_between(dates, start_value, values,
                       where=[v >= start_value for v in values],
                       color="#4CAF50", alpha=0.1)
    ax_eq.fill_between(dates, start_value, values,
                       where=[v < start_value for v in values],
                       color="#F44336", alpha=0.1)
    ax_eq.set_ylabel("资金 (元)")
    ax_eq.set_xlabel("日期")
    ax_eq.grid(True, alpha=0.3)

    fig.suptitle(
        f"{symbol}  {display_name}  |  "
        f"收益 {total_return:+.2f}%  年化 {annual_return:+.2f}%  最大回撤 {max_drawdown:+.2f}%",
        fontsize=14, fontweight="bold",
    )
    plt.tight_layout()

    img_path = Path(__file__).parent / f"backtest_{symbol}_{strategy_key}.png"
    fig.savefig(img_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[图表] 已保存 -> {img_path}")


def parse_args():
    """简陋的命令行解析，不想引入 argparse 太重"""
    args = {"strategy": "rsi", "symbol": "000001"}  # 默认 RSI + 平安银行
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "-s" and i + 1 < len(argv):
            args["strategy"] = argv[i + 1]
            i += 2
        else:
            args["symbol"] = argv[i]
            i += 1
    return args


if __name__ == "__main__":
    args = parse_args()
    strategy_key = args["strategy"]
    symbol = args["symbol"]

    if strategy_key not in STRATEGIES:
        print(f"未知策略: {strategy_key}。可选: {', '.join(STRATEGIES.keys())}")
        sys.exit(1)

    # 1. 拿数据
    df = get_data(symbol)
    print(f"[数据] {symbol} 共 {len(df)} 条日线  "
          f"({df['date'].min().date()} ~ {df['date'].max().date()})")

    # 2. 市场分析报告（MACD、缩量、大单、北向资金）
    print_market_report(df, symbol)

    # 3. 回测
    run_backtest(df, strategy_key, symbol)
