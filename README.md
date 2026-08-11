# Quant Starter — 量化交易入门项目

多因子动量轮动选股回测系统。

## 做了什么

拿沪深 300 里 40 只蓝筹股，每个月计算动量因子（过去 1/3/6 个月涨幅），综合排名，买最强的 Top 10，下个月重新排名换仓。跟"全部等权持有"对比，看能不能跑出 Alpha。

## 怎么跑

```bash
# 装依赖
pip install -r requirements.txt

# 多因子轮动（主程序）
python multi_factor.py

# 持有 Top 5
python multi_factor.py --top 5

# 单股票策略回测（学习用）
python main.py -s rsi 600036     # RSI 均值回归
python main.py -s macd 600036    # MACD 金叉死叉
python main.py -s ma 600036      # 双均线交叉
python main.py -s tt 600036      # 海龟交易法则
python main.py -s dm 600036      # 双动量策略
```

## 项目结构

```
├── multi_factor.py      # 多因子选股轮动（主程序）
├── main.py              # 单股票策略回测
├── fetch_data.py        # 数据层（baostock）
├── indicators.py        # 技术指标（MACD/缩量/大单分析）
├── strategies/          # 策略库
│   ├── dual_ma.py           # 双均线
│   ├── macd_strategy.py     # MACD 水上水下
│   ├── rsi_mean_revert.py   # RSI 均值回归
│   ├── turtle_trading.py    # 海龟交易法则
│   └── dual_momentum.py     # 双动量
├── requirements.txt     # 依赖
└── data/                # 股票数据缓存
```

## 回测结果（2020-2025）

| 策略 | 总收益 | 基准 | Alpha |
|------|:---:|:---:|:---:|
| 动量轮动 Top10 | +40.30% | +37.59% | +2.71% |
| RSI 均值回归 (600036) | +38.71% | — | — |
| 海龟交易 (600036) | -7.47% | — | — |

## 环境

Python 3.11 + baostock + backtrader + pandas + matplotlib

数据来源：baostock（免费，无需注册）
