package com.cryptosherlock.mobile

import kotlin.math.abs
import kotlin.math.max

data class CandlePatternHit(val name: String, val bias: Int, val strength: Double, val bars: Int)
data class CandlestickSnapshot(
    val score: Double,
    val bias: String,
    val patterns: List<CandlePatternHit>,
    val bodyToRange: Double,
    val upperWickToRange: Double,
    val lowerWickToRange: Double,
    val volumeRatio: Double,
    val priorTrendPct: Double
)

/**
 * Deterministic OHLC candlestick feature extractor.
 * All thresholds are scale-free ratios; only completed candles supplied by caller are used.
 * Pattern hits are descriptive features, not standalone trade recommendations.
 */
class CandlestickIntelligence {
    fun analyze(data: List<StoredCandle>, endExclusive: Int = data.size): CandlestickSnapshot {
        val end = endExclusive.coerceIn(0, data.size)
        if (end < 6) return CandlestickSnapshot(0.0, "NEUTRAL", emptyList(), 0.0, 0.0, 0.0, 1.0, 0.0)
        val a = data[end - 1]
        val range = (a.high - a.low).coerceAtLeast(1e-12)
        val body = abs(a.close - a.open)
        val upper = (a.high - max(a.open, a.close)).coerceAtLeast(0.0)
        val lower = (minOf(a.open, a.close) - a.low).coerceAtLeast(0.0)
        val bodyR = body / range
        val upperR = upper / range
        val lowerR = lower / range
        val prior = data[end - 6].close
        val trend = if (prior > 0.0) (data[end - 2].close / prior - 1.0) * 100.0 else 0.0
        val avgVol = data.subList(end - 6, end - 1).map { it.volume }.average().coerceAtLeast(1e-12)
        val volRatio = a.volume / avgVol
        val hits = mutableListOf<CandlePatternHit>()
        fun add(name: String, bias: Int, strength: Double, bars: Int = 1) {
            hits.add(CandlePatternHit(name, bias, strength.coerceIn(0.0, 1.0), bars))
        }
        val bullish = a.close > a.open
        val bearish = a.close < a.open
        if (bodyR <= 0.10) add("DOJI", 0, 0.35)
        if (bodyR <= 0.30 && upperR > 0.25 && lowerR > 0.25) add("SPINNING_TOP", 0, 0.25)
        if (lowerR >= 0.55 && bodyR <= 0.35 && upperR <= 0.20) {
            add(if (trend < 0) "HAMMER" else "HANGING_MAN", if (trend < 0) 1 else -1, 0.65)
        }
        if (upperR >= 0.55 && bodyR <= 0.35 && lowerR <= 0.20) {
            add(if (trend > 0) "SHOOTING_STAR" else "INVERTED_HAMMER", if (trend > 0) -1 else 1, 0.65)
        }
        if (bodyR >= 0.85) add(if (bullish) "BULLISH_MARUBOZU" else "BEARISH_MARUBOZU", if (bullish) 1 else -1, 0.55)

        val p = data[end - 2]
        val pBody = abs(p.close - p.open)
        if (bullish && p.close < p.open && a.open <= p.close && a.close >= p.open && body >= pBody * 0.9)
            add("BULLISH_ENGULFING", 1, 0.85, 2)
        if (bearish && p.close > p.open && a.open >= p.close && a.close <= p.open && body >= pBody * 0.9)
            add("BEARISH_ENGULFING", -1, 0.85, 2)
        if (p.close < p.open && body <= pBody * 0.55 && max(a.open, a.close) <= max(p.open, p.close) && minOf(a.open, a.close) >= minOf(p.open, p.close))
            add("BULLISH_HARAMI", 1, 0.45, 2)
        if (p.close > p.open && body <= pBody * 0.55 && max(a.open, a.close) <= max(p.open, p.close) && minOf(a.open, a.close) >= minOf(p.open, p.close))
            add("BEARISH_HARAMI", -1, 0.45, 2)
        val p2 = data[end - 3]
        val p1 = data[end - 2]
        val mid = (p2.open + p2.close) / 2.0
        if (p2.close < p2.open && abs(p1.close - p1.open) < abs(p2.close - p2.open) * 0.55 && bullish && a.close > mid)
            add("MORNING_STAR", 1, 0.9, 3)
        if (p2.close > p2.open && abs(p1.close - p1.open) < abs(p2.close - p2.open) * 0.55 && bearish && a.close < mid)
            add("EVENING_STAR", -1, 0.9, 3)
        if (p2.close > p2.open && p1.close > p1.open && bullish && p1.close > p2.close && a.close > p1.close)
            add("THREE_WHITE_SOLDIERS", 1, 0.75, 3)
        if (p2.close < p2.open && p1.close < p1.open && bearish && p1.close < p2.close && a.close < p1.close)
            add("THREE_BLACK_CROWS", -1, 0.75, 3)

        val weighted = hits.sumOf { it.bias * it.strength }
        val contextMultiplier = when {
            trend > 0.35 && weighted > 0 -> 1.15
            trend < -0.35 && weighted < 0 -> 1.15
            trend > 0.35 && weighted < 0 -> 0.85
            trend < -0.35 && weighted > 0 -> 0.85
            else -> 1.0
        }
        val volumeMultiplier = if (volRatio >= 1.5) 1.15 else 1.0
        val score = (weighted * contextMultiplier * volumeMultiplier).coerceIn(-2.0, 2.0)
        val bias = when { score >= 0.45 -> "BULLISH"; score <= -0.45 -> "BEARISH"; else -> "NEUTRAL" }
        return CandlestickSnapshot(score, bias, hits, bodyR, upperR, lowerR, volRatio, trend)
    }
}
