"""
双均线交叉策略（你最早的那个，从根目录挪进来了）
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
        self.trade_log = []

    def next(self):
        if not self.data.close[0]:
            return

        price = self.data.close[0]
        date = self.data.datetime.date(0)

        if self.crossover > 0 and not self.position:
            size = int(self.broker.getcash() / price / 100) * 100
            if size > 0:
                self.buy(size=size)
                self.trade_log.append((date, price, "buy"))
                self.trade_count += 1

        elif self.crossover < 0 and self.position:
            self.close()
            self.trade_log.append((date, price, "sell"))
            self.trade_count += 1
