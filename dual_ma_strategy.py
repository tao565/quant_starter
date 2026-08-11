"""
双均线策略 —— 量化入门第一课。

规则：
  - 短期均线上穿长期均线（金叉）→ 买入
  - 短期均线下穿长期均线（死叉）→ 卖出
  - 永远满仓或空仓

金叉：短期均线从下往上穿过长期均线，说明最近涨得比之前快，可能趋势转涨。
死叉：短期均线从上往下穿过长期均线，说明最近跌得比之前快，可能趋势转跌。
"""

import backtrader as bt


class DualMAStrategy(bt.Strategy):

    params = dict(short_period=5, long_period=20)

    def __init__(self):
        self.short_ma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.short_period
        )
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.long_period
        )
        self.crossover = bt.indicators.CrossOver(self.short_ma, self.long_ma)

        self.trade_count = 0
        self.trade_log = []          # 记录每笔交易的日期,价格,类型,供画图用
        self.signal_log = []         # 记录金叉/死叉信号（包括没钱买的情况）

    def next(self):
        if not self.data.close[0]:
            return

        price = self.data.close[0]
        date = self.data.datetime.date(0)

        # ---- 买入信号：金叉 + 空仓 ----
        if self.crossover > 0 and not self.position:
            size = int(self.broker.getcash() / price / 100) * 100
            if size > 0:
                self.buy(size=size)
                print(f"[BUY] {date}  价格 {price:.2f}  {size}股")
                self.trade_log.append((date, price, "buy"))
                self.trade_count += 1
            else:
                print(f"[!!!] {date}  金叉信号！但资金不够买 1 手 "
                      f"(需要 {price * 100:.0f}，只有 {self.broker.getcash():.0f})")

        # ---- 卖出信号：死叉 + 持仓 ----
        elif self.crossover < 0 and self.position:
            self.close()
            print(f"[SELL] {date}  价格 {price:.2f}")
            self.trade_log.append((date, price, "sell"))
            self.trade_count += 1

    def stop(self):
        print(f"\n总交易次数: {self.trade_count}")
