"""
海龟交易法则（Turtle Trading System）—— Richard Dennis 的传奇系统。

1983 年，Dennis 打赌：交易可以教。他招了一批普通人训练两周，
给他们账户真金白银跑这个系统，结果年均复利 80%+。

核心思想不是预测方向，而是：
  "你不知道哪次会赚，但你知道赚的时候会赚很多，亏的时候只亏一点。"

规则（简化版）：
  入场：价格突破 20 日最高价 → 买入
  止损：价格跌破 2×ATR（平均真实波幅）→ 止损
  加仓：每涨 0.5×ATR 加一次仓（最多 4 次）
  出场：价格跌破 10 日最低价 → 全部卖出

为什么有效：A 股每年通常有 1-2 波大行情，海龟靠抓住这波行情赚大钱，
其余时间小亏止损，整体正期望。
"""

import backtrader as bt


class TurtleStrategy(bt.Strategy):

    params = dict(
        entry_period=20,        # 突破 20 日高点入场
        exit_period=10,         # 跌破 10 日低点出场
        atr_period=20,          # ATR 计算周期
        risk_percent=0.02,      # 单笔风险占总资金 2%
        max_units=4,            # 最多加仓 4 次
    )

    def __init__(self):
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.donchian_high = bt.indicators.Highest(self.data.high, period=self.params.entry_period)
        self.donchian_low = bt.indicators.Lowest(self.data.low, period=self.params.exit_period)

        self.trade_count = 0
        self.trade_log = []
        self.last_buy_price = None
        self.units = 0

    def next(self):
        if not self.data.close[0]:
            return

        price = self.data.close[0]
        date = self.data.datetime.date(0)
        atr_val = self.atr[0]
        if atr_val <= 0:
            return

        cash = self.broker.getcash()
        total_value = self.broker.getvalue()

        # ===== 入场：突破 20 日最高价 =====
        if not self.position:
            if price >= self.donchian_high[-1]:
                # 基于 ATR 计算仓位（风险 2%）
                risk_amount = total_value * self.params.risk_percent
                stop_distance = 2.0 * atr_val
                size = int(risk_amount / stop_distance / 100) * 100

                if size > 0 and size * price <= cash:
                    self.buy(size=size)
                    self.last_buy_price = price
                    self.units = 1
                    print(f"[TT BUY] {date}  突破入场  价格 {price:.2f}  {size}股  "
                          f"止损≈{price - stop_distance:.2f}")
                    self.trade_log.append((date, price, "buy"))
                    self.trade_count += 1

        # ===== 持仓中 =====
        else:
            # 加仓：每涨 0.5×ATR 加一次
            if self.units < self.params.max_units and self.last_buy_price:
                add_price = self.last_buy_price + 0.5 * atr_val
                if price >= add_price:
                    risk_amount = total_value * self.params.risk_percent
                    stop_distance = 2.0 * atr_val
                    size = int(risk_amount / stop_distance / 100) * 100
                    if size > 0 and size * price <= cash:
                        self.buy(size=size)
                        self.last_buy_price = price
                        self.units += 1
                        print(f"[TT 加仓] {date}  第{self.units}次加仓  "
                              f"价格 {price:.2f}  {size}股")
                        self.trade_log.append((date, price, "buy"))
                        self.trade_count += 1

            # 出场：跌破 10 日最低价 → 全部清仓
            if price <= self.donchian_low[-1]:
                self.close()
                print(f"[TT SELL] {date}  趋势结束  价格 {price:.2f}  "
                      f"市值 {self.broker.getvalue():.0f}")
                self.trade_log.append((date, price, "sell"))
                self.trade_count += 1
                self.last_buy_price = None
                self.units = 0
