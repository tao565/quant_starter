"""
技术指标 & 市场分析工具。
包含：MACD、成交量缩量检测、大单资金流向估算。
"""

import pandas as pd
import numpy as np


# ================================================================
# MACD 指标
# ================================================================
def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    """
    计算 MACD 指标。
    返回 DataFrame，列：DIF, DEA, MACD_hist

    MACD 柱 > 0 = 在零轴上方（水上），多头区域
    MACD 柱 < 0 = 在零轴下方（水下），空头区域
    DIF 上穿 DEA  = 金叉
    DIF 下穿 DEA  = 死叉
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = 2 * (dif - dea)

    return pd.DataFrame({"DIF": dif, "DEA": dea, "MACD": macd_hist})


def macd_cross(dif: pd.Series, dea: pd.Series) -> pd.Series:
    """
    判断 MACD 金叉/死叉。
    返回: 1=金叉, -1=死叉, 0=无交叉
    """
    cross = pd.Series(0, index=dif.index)
    for i in range(1, len(dif)):
        if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
            cross.iloc[i] = 1   # 金叉
        elif dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
            cross.iloc[i] = -1  # 死叉
    return cross


# ================================================================
# 缩量检测
# ================================================================
def check_volume_shrink(volume: pd.Series, recent_days=10, compare_days=20) -> dict:
    """
    检测最近一段时间是否在缩量。

    参数:
        volume: 成交量序列
        recent_days: 最近多少天（默认 10 个交易日 ≈ 2 周）
        compare_days: 对比前多少天的均值

    返回:
        dict，包含缩量比例、是否明显缩量（缩到 70% 以下）、均量对比
    """
    if len(volume) < recent_days + compare_days:
        return {"shrinking": False, "ratio": 1.0, "recent_avg": 0, "prev_avg": 0}

    recent_avg = volume.iloc[-recent_days:].mean()
    prev_avg = volume.iloc[-(recent_days + compare_days):-recent_days].mean()

    ratio = recent_avg / prev_avg if prev_avg > 0 else 1.0

    return {
        "shrinking": ratio < 0.7,          # 缩到 70% 以下算明显缩量
        "ratio": round(ratio, 3),
        "recent_avg": round(recent_avg, 0),
        "prev_avg": round(prev_avg, 0),
    }


# ================================================================
# 大单资金流向估算（暗盘的近似替代）
# ================================================================
def estimate_big_order_flow(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据量价关系估算大单资金流向。

    原理：
      成交量放大 + 价格上涨 → 大资金在买
      成交量放大 + 价格下跌 → 大资金在卖
      成交量缩小 → 散户在交易，主力没动

    返回 DataFrame，新增列：
      big_money_flow: 每日大单资金流估算值（正=流入，负=流出）
      big_money_cum:  累计大单资金流
    """
    df = df.copy()

    # 量比：当日成交量 / 前 5 日均量
    vol_ma5 = df["volume"].rolling(5).mean()
    vol_ratio = df["volume"] / vol_ma5.replace(0, np.nan)

    # 涨跌幅
    price_change = df["close"].pct_change()

    # 大单估算 = 量比 × 涨跌幅 × 成交额
    # 量比 > 1.2 且涨 → 大资金流入；量比 > 1.2 且跌 → 大资金流出
    df["big_money_flow"] = df["amount"] * price_change * (vol_ratio - 1)

    # 平滑处理（3 日移动平均）
    df["big_money_flow"] = df["big_money_flow"].rolling(3, min_periods=1).mean()

    # 累计
    df["big_money_cum"] = df["big_money_flow"].cumsum()

    return df


def big_money_summary(df: pd.DataFrame, recent_days=20) -> dict:
    """
    统计最近 N 天的大单资金动向。

    返回 dict:
      net_flow: 近 N 天净流向
      direction: "大幅流入" / "流入" / "流出" / "大幅流出" / "平衡"
      buy_days: 流入天数
      sell_days: 流出天数
    """
    recent = df.iloc[-recent_days:] if len(df) >= recent_days else df

    net_flow = recent["big_money_flow"].sum()
    total_amount = recent["amount"].sum()
    flow_pct = net_flow / total_amount * 100 if total_amount > 0 else 0

    buy_days = int((recent["big_money_flow"] > 0).sum())
    sell_days = int((recent["big_money_flow"] < 0).sum())

    if flow_pct > 5:
        direction = "大幅流入"
    elif flow_pct > 1:
        direction = "流入"
    elif flow_pct > -1:
        direction = "平衡"
    elif flow_pct > -5:
        direction = "流出"
    else:
        direction = "大幅流出"

    return {
        "net_flow": round(net_flow, 0),
        "flow_pct": round(flow_pct, 2),
        "direction": direction,
        "buy_days": buy_days,
        "sell_days": sell_days,
    }


if __name__ == "__main__":
    # 自测
    from fetch_data import fetch_stock_daily
    df = fetch_stock_daily("000001", "20250601", "20250801")
    print(f"数据: {len(df)} 条")

    macd = calc_macd(df["close"])
    print("\nMACD 最后 5 天:")
    print(macd.tail())

    shrink = check_volume_shrink(df["volume"])
    print(f"\n缩量检测: {shrink}")

    df = estimate_big_order_flow(df)
    summary = big_money_summary(df)
    print(f"\n大单资金: {summary}")
