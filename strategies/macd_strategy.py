"""
MACD 金叉死叉策略 —— 区分水上/水下。

规则：
  - MACD 在零轴上方 + DIF 上穿 DEA（水上金叉）→ 强买入信号
  - MACD 在零轴下方 + DIF 上穿 DEA（水下金叉）→ 弱买入信号，可买可不买
  - DIF 下穿 DEA（死叉）→ 卖出

MACD 零轴 = DIF 和 DEA 的交点。零轴上方 = 多头市场（水上），下方 = 空头市场（水下）。
水上金叉的可靠性显著高于水下金叉。
"""

import backtrader as bt


class MACDStrategy(bt.Strategy):

    params = dict(
        fast=12,        # 快线周期
        slow=26,        # 慢线周期
        signal=9,       # 信号线周期
        above_zero_only=False,   # True=只做水上金叉（更保守，信号少但更可靠）
    )

    def __init__(self):
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.fast,
            period_me2=self.params.slow,
            period_signal=self.params.signal,
        )
        # macd.macd  = DIF (快慢线差值)
        # macd.signal = DEA (信号线)
        # macd.macd - macd.signal = MACD 柱

        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.trade_count = 0
        self.trade_log = []

    def next(self):
        if not self.data.close[0]:
            return

        price = self.data.close[0]
        date = self.data.datetime.date(0)

        # DIF (macd.macd) 和 DEA (macd.signal)
        dif = self.macd.macd[0]
        dea = self.macd.signal[0]
        is_above_zero = dif > 0 and dea > 0      # 水上（零轴上方）

        # ---- 买入：金叉 ----
        if self.crossover > 0 and not self.position:
            # 如果设置了只做水上，那就跳过水下金叉
            if self.params.above_zero_only and not is_above_zero:
                return

            size = int(self.broker.getcash() / price / 100) * 100
            if size > 0:
                self.buy(size=size)
                tag = "水上金叉" if is_above_zero else "水下金叉"
                print(f"[MACD BUY] {date}  {tag}  价格 {price:.2f}  {size}股")
                self.trade_log.append((date, price, "buy", tag))
                self.trade_count += 1

        # ---- 卖出：死叉 ----
        elif self.crossover < 0 and self.position:
            self.close()
            tag = "水上死叉" if is_above_zero else "水下死叉"
            print(f"[MACD SELL] {date}  {tag}  价格 {price:.2f}")
            self.trade_log.append((date, price, "sell", tag))
            self.trade_count += 1
