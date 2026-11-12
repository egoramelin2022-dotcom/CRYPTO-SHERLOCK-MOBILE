package com.cryptosherlock.mobile

import kotlin.math.ln
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
    val averageFavorablePct: Double,
    val averageAdversePct: Double,
    val note: String
)

/**
 * Searches the full supplied history. Candidate windows and their forward outcomes
 * must end before the current target window starts (no look-ahead into the target).
 * Similarity combines return path, candle body/wicks, range and relative volume.
 */
class PatternIntelligence {
    fun search(history: List<StoredCandle>, window: Int = 40, horizon: Int = 16, top: Int = 10): PatternReport {
        require(window >= 10 && horizon >= 1 && top >= 1)
        if (history.size < window * 3 + horizon) {
            return PatternReport(0, emptyList(), 0.0, 0.0, 0.0, 0.0,
                "Недостаточно истории. Сначала загрузите BTCUSDT 15m.")
        }
        val targetStart = history.size - window
        val targetVector = vector(history.subList(targetStart, history.size))
        val candidates = ArrayList<PatternMatch>()
        // One non-overlapping step reduces duplicate near-identical historical samples.
        var i = 0
        while (i + window + horizon <= targetStart) {
            val sample = history.subList(i, i + window)
            val score = similarity(targetVector, vector(sample))
            val base = sample.last().close
            val future = history.subList(i + window, i + window + horizon)
            val high = future.maxOf { it.high }
            val low = future.minOf { it.low }
            candidates.add(PatternMatch(
                sample.first().openTime, sample.last().openTime, score,
                (future.last().close / base - 1.0) * 100.0,
                (high / base - 1.0) * 100.0,
                (low / base - 1.0) * 100.0
            ))
            i += window
        }
        val ranked = candidates.sortedByDescending { it.similarity }.take(top)
        val avg = ranked.map { it.forwardReturnPct }.averageOrZero()
        val win = if (ranked.isEmpty()) 0.0 else ranked.count { it.forwardReturnPct > 0.0 }.toDouble() / ranked.size * 100.0
        val favorable = ranked.map { it.maxFavorablePct }.averageOrZero()
        val adverse = ranked.map { it.maxAdversePct }.averageOrZero()
        return PatternReport(candidates.size, ranked, avg, win, favorable, adverse,
            "Полный доступный массив; неперекрывающиеся кандидаты. Сходство — исследовательский рейтинг, не вероятность прибыли. Будущие свечи используются только для оценки исхода.")
    }

    private fun List<Double>.averageOrZero(): Double = if (isEmpty()) 0.0 else average()

    private fun vector(c: List<StoredCandle>): DoubleArray {
        val raw = ArrayList<Double>(c.size * 5)
        val avgVolume = c.map { it.volume.coerceAtLeast(1e-12) }.average().coerceAtLeast(1e-12)
        for (i in c.indices) {
            val x = c[i]
            val range = (x.high - x.low).coerceAtLeast(x.close * 1e-8).coerceAtLeast(1e-12)
            val body = (x.close - x.open) / range
            val upper = (x.high - maxOf(x.open, x.close)) / range
            val lower = (minOf(x.open, x.close) - x.low) / range
            val rangePct = range / x.close.coerceAtLeast(1e-12)
            val relVol = ln((x.volume.coerceAtLeast(1e-12)) / avgVolume)
            val ret = if (i == 0 || c[i - 1].close <= 0.0) 0.0 else ln(x.close / c[i - 1].close)
            raw.add(ret); raw.add(body); raw.add(upper); raw.add(lower)
            raw.add(rangePct); raw.add(relVol)
        }
        // Normalize each feature channel independently within the window.
        val channels = 6
        val out = DoubleArray(raw.size)
        for (ch in 0 until channels) {
            var mean = 0.0
            for (i in c.indices) mean += raw[i * channels + ch]
            mean /= c.size
            var variance = 0.0
            for (i in c.indices) { val d = raw[i * channels + ch] - mean; variance += d * d }
            val sd = sqrt(variance / c.size).coerceAtLeast(1e-8)
            for (i in c.indices) out[i * channels + ch] = ((raw[i * channels + ch] - mean) / sd).coerceIn(-5.0, 5.0)
        }
        return out
    }

    private fun similarity(a: DoubleArray, b: DoubleArray): Double {
        if (a.size != b.size || a.isEmpty()) return 0.0
        var dot = 0.0; var aa = 0.0; var bb = 0.0
        for (i in a.indices) { dot += a[i] * b[i]; aa += a[i] * a[i]; bb += b[i] * b[i] }
        if (aa == 0.0 || bb == 0.0) return 0.0
        return (dot / sqrt(aa * bb)).coerceIn(-1.0, 1.0) * 100.0
    }
}
