"""
拉取 A 股历史数据，保存到本地 CSV。
数据来源：baostock（免费、稳定、无需注册）

baostock 的股票代码格式：
  上海：sh.600519   深圳：sz.000001   创业板：sz.300750
"""

import baostock as bs
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _to_baostock_code(symbol: str) -> str:
    """把 600519 / 000001 转成 baostock 格式 sh.600519 / sz.000001"""
    if symbol.startswith(("sh.", "sz.")):
        return symbol
    if symbol.startswith(("6", "5")):
        return f"sh.{symbol}"
    return f"sz.{symbol}"


def fetch_stock_daily(symbol: str, start: str = "2020-01-01", end: str = "2025-12-31") -> pd.DataFrame:
    """
    拉取单只股票日线数据（前复权）。
    返回标准列: date, open, high, low, close, volume, amount
    """
    bs_code = _to_baostock_code(symbol)

    bs.login()
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount",
        start_date=start,
        end_date=end,
        frequency="d",
        adjustflag="2",          # 前复权
    )

    rows = []
    while (rs.error_code == "0") and rs.next():
        rows.append(rs.get_row_data())

    bs.logout()

    if not rows:
        raise ValueError(f"没拉到数据，检查股票代码 {symbol}（baostock: {bs_code}）")

    df = pd.DataFrame(
        rows, columns=["date", "open", "high", "low", "close", "volume", "amount"]
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["amount"] = df["amount"].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def save_to_csv(df: pd.DataFrame, symbol: str) -> Path:
    """保存到 data/ 目录下"""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{symbol}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def fetch_north_bound_holdings(symbol: str) -> dict:
    """
    拉取沪深港通（北向资金）持股数据——外资动向的近似指标。
    返回 dict，包含最近一期的持股比例、市值变化。

    注意：baostock 不提供这个数据，用 akshare 补。
    如果 akshare 也连不上（你那个代理问题），返回空 dict。
    """
    try:
        import akshare as ak

        # 构造 akshare 需要的市场标记
        if symbol.startswith(("6", "5")):
            market = "沪"
        else:
            market = "深"

        df = ak.stock_hsgt_hold_stock_em(
            symbol=symbol, market=market,
        )

        if df.empty:
            return {}

        latest = df.iloc[-1]
        return {
            "date": str(latest.get("日期", "")),
            "hold_ratio": float(latest.get("持股比例", 0)) if latest.get("持股比例") else 0,
            "hold_value": float(latest.get("持股市值", 0)) if latest.get("持股市值") else 0,
        }
    except Exception as e:
        print(f"  [!] 北向资金数据获取失败: {e}")
        return {}


if __name__ == "__main__":
    print("正在拉取 600519 贵州茅台 日线数据...")
    df = fetch_stock_daily("600519")
    path = save_to_csv(df, "600519")
    print(f"已保存 {len(df)} 条数据 -> {path}")
    print(df.head())
