"""
RSI 均值回归策略 —— 入门策略中少有的、可能跑出正收益的策略。

核心逻辑：
  股票/ETF 不会一直涨也不会一直跌。极端超卖后会反弹，极端超买后会回调。

规则：
  - RSI < 超卖阈值（如 30）→ 分批买入（恐慌时买）
  - RSI > 超买阈值（如 70）→ 分批卖出（狂热时卖）
  - 持仓期间 RSI 回到中性区间 → 不动

这个策略在指数 ETF（如 510050 上证50）上通常比个股效果好，
因为指数天然具有均值回归特性，不容易像个股一样单边暴跌。
"""

import backtrader as bt


class RSIMeanRevertStrategy(bt.Strategy):

    params = dict(
        rsi_period=14,          # RSI 计算周期
        oversold=30,            # 超卖线（低于此值买入）
        overbought=70,          # 超买线（高于此值卖出）
        position_pct=0.3,       # 每次买入占总资金的 30%（分批建仓）
        sell_pct=0.5,           # 每次卖出持仓的 50%（分批出货）
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(
            self.data.close, period=self.params.rsi_period
        )
        self.trade_count = 0
        self.trade_log = []

    def next(self):
        if not self.data.close[0]:
            return

        rsi = self.rsi[0]
        price = self.data.close[0]
        date = self.data.datetime.date(0)

        # ---- 买入：RSI 进入超卖区 ----
        if rsi < self.params.oversold:
            cash = self.broker.getcash()
            alloc = cash * self.params.position_pct
            size = int(alloc / price / 100) * 100
            if size > 0:
                self.buy(size=size)
                print(f"[RSI BUY] {date}  RSI={rsi:.0f}(超卖)  价格 {price:.2f}  "
                      f"{size}股  仓位 {self.broker.getvalue():.0f}")
                self.trade_log.append((date, price, "buy"))
                self.trade_count += 1

        # ---- 卖出：RSI 进入超买区 ----
        elif rsi > self.params.overbought and self.position:
            size = int(self.position.size * self.params.sell_pct / 100) * 100
            if size > 0:
                self.sell(size=size)
                print(f"[RSI SELL] {date}  RSI={rsi:.0f}(超买)  价格 {price:.2f}  "
                      f"{size}股  仓位 {self.broker.getvalue():.0f}")
                self.trade_log.append((date, price, "sell"))
                self.trade_count += 1
