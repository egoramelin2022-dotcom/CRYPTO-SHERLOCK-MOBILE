package com.cryptosherlock.mobile

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

data class FiveStageMatch(
    val startTime: Long,
    val endTime: Long,
    val declinePct: Double,
    val recoveryPct: Double,
    val peakGainPct: Double,
    val collapsePct: Double,
    val sidewaysRangePct: Double,
    val forwardReturnPct: Double
)

data class FiveStageReport(
    val testedWindows: Int,
    val totalMatches: Int,
    val averageForwardPct: Double,
    val positiveRatePct: Double,
    val medianForwardPct: Double,
    val matches: List<FiveStageMatch>,
    val message: String
)

/**
 * Independent, rule-based detector for the user's five-stage formation.
 * Candidate window is split into five equal sections:
 * decline -> recovery -> local peak -> sharp collapse -> sideways with lower wicks.
 * Future candles are used only to evaluate what happened after a historical match,
 * never to decide whether the candidate itself matches.
 */
class FiveStageStrategy {
    fun search(history: List<StoredCandle>, window: Int = 100, horizon: Int = 16, top: Int = 10): FiveStageReport {
        if (window < 50 || horizon < 1 || history.size < window + horizon + 20) {
            return FiveStageReport(0, 0, 0.0, 0.0, 0.0, emptyList(), "Недостаточно данных для пятиэтапного поиска.")
        }
        val matches = ArrayList<FiveStageMatch>()
        var tested = 0
        val stride = max(1, window / 10)
        var start = 0
        val lastCandidateStart = history.size - window - horizon
        while (start <= lastCandidateStart) {
            val w = history.subList(start, start + window)
            val fifth = window / 5
            val a = w.subList(0, fifth)
            val b = w.subList(fifth, fifth * 2)
            val c = w.subList(fifth * 2, fifth * 3)
            val d = w.subList(fifth * 3, fifth * 4)
            val e = w.subList(fifth * 4, window)
            val p0 = a.first().open
            val lowA = a.minOf { it.low }
            val highB = b.maxOf { it.high }
            val peakC = c.maxOf { it.high }
            val closeD = d.last().close
            val closesE = e.map { it.close }
            val rangeE = (e.maxOf { it.high } - e.minOf { it.low }) / max(e.first().close, 1e-9) * 100.0
            val lowerWickShare = e.count { candle ->
                val bodyLow = min(candle.open, candle.close)
                val lowerWick = bodyLow - candle.low
                val fullRange = max(candle.high - candle.low, 1e-9)
                lowerWick / fullRange >= 0.35
            }.toDouble() / e.size
            val decline = (lowA / p0 - 1.0) * 100.0
            val recovery = (highB / max(lowA, 1e-9) - 1.0) * 100.0
            val peakGain = (peakC / max(p0, 1e-9) - 1.0) * 100.0
            val collapse = (closeD / max(peakC, 1e-9) - 1.0) * 100.0
            val sidewaysDrift = abs(closesE.last() / max(closesE.first(), 1e-9) - 1.0) * 100.0
            tested++
            val passes = decline <= -1.0 &&
                recovery >= 0.4 &&
                peakGain >= 0.2 &&
                collapse <= -1.0 &&
                rangeE <= 4.0 &&
                sidewaysDrift <= 2.5 &&
                lowerWickShare >= 0.25
            if (passes) {
                val future = history.subList(start + window, start + window + horizon)
                val base = w.last().close
                matches.add(FiveStageMatch(
                    w.first().openTime, w.last().openTime,
                    decline, recovery, peakGain, collapse, rangeE,
                    (future.last().close / max(base, 1e-9) - 1.0) * 100.0
                ))
            }
            start += stride
        }
        val sortedReturns = matches.map { it.forwardReturnPct }.sorted()
        val average = if (sortedReturns.isEmpty()) 0.0 else sortedReturns.average()
        val positive = if (sortedReturns.isEmpty()) 0.0 else sortedReturns.count { it > 0.0 }.toDouble() / sortedReturns.size * 100.0
        val median = if (sortedReturns.isEmpty()) 0.0 else if (sortedReturns.size % 2 == 1) sortedReturns[sortedReturns.size / 2] else (sortedReturns[sortedReturns.size / 2 - 1] + sortedReturns[sortedReturns.size / 2]) / 2.0
        // Show examples in chronological order, not cherry-picked by best future return.
        val examples = matches.sortedByDescending { it.startTime }.take(top)
        val note = if (matches.isEmpty()) "Пока не найдено окон, соответствующих текущим порогам." else "Статистика рассчитана по всем найденным формациям. Примеры показаны по времени, не отобраны по будущей доходности. Без комиссий и проскальзывания."
        return FiveStageReport(tested, matches.size, average, positive, median, examples, note)
    }
}