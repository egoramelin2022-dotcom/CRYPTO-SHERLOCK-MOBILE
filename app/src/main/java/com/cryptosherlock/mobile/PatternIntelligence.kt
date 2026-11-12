package com.cryptosherlock.mobile

import kotlin.math.sqrt

data class PatternMatch(
    val startTime: Long,
    val endTime: Long,
    val similarity: Double,
    val forwardReturnPct: Double,
    val maxFavorablePct: Double,
    val maxAdversePct: Double
)

data class PatternReport(
    val sampleCount: Int,
    val matches: List<PatternMatch>,
    val averageForwardPct: Double,
    val positiveRatePct: Double,
    val note: String
)

class PatternIntelligence {
    fun search(history: List<StoredCandle>, window: Int = 40, horizon: Int = 16, top: Int = 10): PatternReport {
        require(window >= 10 && horizon >= 1)
        if (history.size < window * 3 + horizon) {
            return PatternReport(0, emptyList(), 0.0, 0.0, "Недостаточно истории. Сначала загрузите больше BTCUSDT 15m.")
        }
        val targetStart = history.size - window
        val target = history.subList(targetStart, history.size)
        val targetVector = vector(target)
        val candidates = ArrayList<PatternMatch>()
        val step = maxOf(1, window / 4)
        var i = 0
        while (i + window + horizon <= targetStart) {
            val sample = history.subList(i, i + window)
            val score = similarity(targetVector, vector(sample))
            val base = sample.last().close
            val future = history.subList(i + window, i + window + horizon)
            val end = future.last().close
            val maxHigh = future.maxOf { it.high }
            val minLow = future.minOf { it.low }
            candidates.add(PatternMatch(
                sample.first().openTime, sample.last().openTime, score,
                (end / base - 1.0) * 100.0,
                (maxHigh / base - 1.0) * 100.0,
                (minLow / base - 1.0) * 100.0
            ))
            i += step
        }
        val ranked = candidates.sortedByDescending { it.similarity }.take(top)
        val avg = if (ranked.isEmpty()) 0.0 else ranked.map { it.forwardReturnPct }.average()
        val win = if (ranked.isEmpty()) 0.0 else ranked.count { it.forwardReturnPct > 0 }.toDouble() / ranked.size * 100.0
        return PatternReport(candidates.size, ranked, avg, win,
            "Сравнение по нормализованной структуре свечных изменений. Это исследовательский рейтинг, не вероятность будущей прибыли.")
    }

    private fun vector(c: List<StoredCandle>): DoubleArray {
        val returns = DoubleArray(c.size - 1) { i ->
            if (c[i].close <= 0.0) 0.0 else kotlin.math.ln(c[i + 1].close / c[i].close)
        }
        val mean = returns.average()
        val variance = returns.map { (it - mean) * (it - mean) }.average()
        val sd = sqrt(variance).coerceAtLeast(1e-9)
        return DoubleArray(returns.size) { (returns[it] - mean) / sd }
    }

    private fun similarity(a: DoubleArray, b: DoubleArray): Double {
        if (a.size != b.size || a.isEmpty()) return 0.0
        var dot = 0.0
        var aa = 0.0
        var bb = 0.0
        for (i in a.indices) {
            dot += a[i] * b[i]
            aa += a[i] * a[i]
            bb += b[i] * b[i]
        }
        if (aa == 0.0 || bb == 0.0) return 0.0
        return (dot / sqrt(aa * bb)).coerceIn(-1.0, 1.0) * 100.0
    }
}