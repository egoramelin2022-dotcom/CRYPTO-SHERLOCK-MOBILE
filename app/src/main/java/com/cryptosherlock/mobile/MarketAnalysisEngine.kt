package com.cryptosherlock.mobile

import kotlin.math.abs
import kotlin.math.max

data class TimeframeState(val interval: String, val close: Double, val emaFast: Double, val emaSlow: Double, val rsi: Double, val atrPct: Double, val volumeRatio: Double, val bias: String)
data class ForecastSnapshot(val createdAt: Long, val price: Double, val horizonBars: Int, val longPct: Int, val shortPct: Int, val sidewaysPct: Int, val entryState: String, val entryLow: Double, val entryHigh: Double, val invalidation: Double, val rationale: String, val states: List<TimeframeState>)

/** Transparent rule-score prototype. Scores are NOT calibrated probabilities. */
class MarketAnalysisEngine {
    fun state(interval: String, candles: List<Candle>): TimeframeState {
        require(candles.size >= 30) { "Для " + interval + " нужно минимум 30 свечей" }
        val closes = candles.map { it.close.toDouble() }
        fun ema(period: Int): Double {
            val k = 2.0 / (period + 1.0)
            var value = closes.take(period).average()
            for (i in period until closes.size) value = closes[i] * k + value * (1.0 - k)
            return value
        }
        val gains = (closes.size - 14 until closes.size).sumOf { i -> max(0.0, closes[i] - closes[i - 1]) } / 14.0
        val losses = (closes.size - 14 until closes.size).sumOf { i -> max(0.0, closes[i - 1] - closes[i]) } / 14.0
        val rsi = if (losses <= 1e-12) 100.0 else 100.0 - 100.0 / (1.0 + gains / losses)
        val tr = candles.takeLast(14).mapIndexed { index, c ->
            val prev = candles[(candles.size - 14 + index - 1).coerceAtLeast(0)].close.toDouble()
            max(c.high.toDouble() - c.low.toDouble(), max(kotlin.math.abs(c.high.toDouble() - prev), kotlin.math.abs(c.low.toDouble() - prev)))
        }.average()
        val atrPct = tr / closes.last().coerceAtLeast(1e-9) * 100.0
        val recentVol = candles.takeLast(5).map { it.volume.toDouble() }.average()
        val baseVol = candles.takeLast(25).map { it.volume.toDouble() }.average().coerceAtLeast(1e-9)
        val fast = ema(9)
        val slow = ema(21)
        val bias = when {
            fast > slow && closes.last() > slow -> "LONG"
            fast < slow && closes.last() < slow -> "SHORT"
            else -> "NEUTRAL"
        }
        return TimeframeState(interval, closes.last(), fast, slow, rsi, atrPct, recentVol / baseVol, bias)
    }

    fun forecast(states: List<TimeframeState>, currentPrice: Double): ForecastSnapshot {
        require(states.isNotEmpty() && currentPrice > 0.0)
        var score = 0.0
        states.forEach { s ->
            score += when (s.bias) { "LONG" -> 1.0; "SHORT" -> -1.0; else -> 0.0 }
            score += when { s.rsi in 52.0..68.0 -> 0.35; s.rsi in 32.0..48.0 -> -0.35; else -> 0.0 }
            if (s.volumeRatio > 1.3 && s.bias != "NEUTRAL") score += if (s.bias == "LONG") 0.2 else -0.2
        }
        val directional = (score / (states.size * 1.5).coerceAtLeast(1.0)).coerceIn(-1.0, 1.0)
        val longRaw = 1.0 + max(0.0, directional) * 2.0
        val shortRaw = 1.0 + max(0.0, -directional) * 2.0
        val sideRaw = 1.35 + (1.0 - kotlin.math.abs(directional)) * 0.65
        val total = longRaw + shortRaw + sideRaw
        val long = (longRaw / total * 100).toInt()
        val short = (shortRaw / total * 100).toInt()
        val side = 100 - long - short
        val atr = states.first().atrPct.coerceIn(0.1, 8.0) / 100.0
        val aligned = states.count { it.bias == "LONG" } >= 2 || states.count { it.bias == "SHORT" } >= 2
        val direction = if (long > short) "LONG" else if (short > long) "SHORT" else "SIDEWAYS"
        val entry = if (aligned && direction != "SIDEWAYS" && max(long, short) >= 43) "ENTRY WINDOW · " + direction else "WAIT · подтверждения недостаточно"
        val low = currentPrice * (1.0 - atr * 0.35)
        val high = currentPrice * (1.0 + atr * 0.35)
        val invalidation = if (direction == "LONG") currentPrice * (1.0 - atr * 1.5) else currentPrice * (1.0 + atr * 1.5)
        val detail = "Сводка " + states.joinToString { it.interval + ":" + it.bias } +
            ". RSI/EMA/объём — эвристические факторы; новости и рыночная ширина пока не подключены."
        return ForecastSnapshot(System.currentTimeMillis(), currentPrice, 16, long, short, side, entry, low, high, invalidation, detail, states)
    }
}
