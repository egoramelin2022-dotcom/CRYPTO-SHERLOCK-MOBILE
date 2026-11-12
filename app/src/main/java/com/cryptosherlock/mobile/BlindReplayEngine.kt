package com.cryptosherlock.mobile

import kotlin.math.ln
import kotlin.math.sqrt

data class BlindReplayPoint(
    val decisionTime: Long,
    val predicted: String,
    val actual: String,
    val confidence: Double,
    val predictedReturnPct: Double,
    val actualReturnPct: Double,
    val analogCount: Int
)

data class BlindReplayReport(
    val tested: Int,
    val traded: Int,
    val correct: Int,
    val accuracyPct: Double,
    val coveragePct: Double,
    val averageActualPct: Double,
    val cumulativeReturnPct: Double,
    val maxDrawdownPct: Double,
    val points: List<BlindReplayPoint>,
    val notes: String
)

/**
 * Last-14-day BTCUSDT 15m walk-forward replay.
 * A forecast is issued every five closed candles for the next five candles.
 * At decision index t, analogs are eligible only when their complete window
 * AND five-candle outcome ended before the current target window began.
 */
class BlindReplayEngine {
    fun run(
        history: List<StoredCandle>,
        window: Int = 40,
        horizon: Int = 5,
        step: Int = 5,
        minSimilarity: Double = 35.0,
        topK: Int = 20,
        lookbackCandles: Int = 1344,
        asOfTime: Long = System.currentTimeMillis(),
        progress: (Int, Int) -> Unit = { _, _ -> }
    ): BlindReplayReport {
        require(window >= 10 && horizon >= 1 && step >= 1 && topK >= 1 && lookbackCandles >= horizon)
        // Ignore the currently forming 15m candle. openTime is aligned to 15m.
        val closed = history.filter { it.openTime + 15L * 60L * 1000L <= asOfTime }
        if (closed.size < window * 4 + horizon * 3) {
            return empty("Недостаточно закрытой истории BTCUSDT 15m для независимого walk-forward теста.")
        }
        val evaluationStart = (closed.size - lookbackCandles).coerceAtLeast(window * 3 + horizon)
        val firstDecision = evaluationStart.coerceAtLeast(window * 3 + horizon)
        val totalSteps = ((closed.size - horizon - firstDecision) / step + 1).coerceAtLeast(0)
        if (totalSteps <= 0) return empty("Нет полного 14-дневного окна для прогнозов.")
        val points = ArrayList<BlindReplayPoint>(totalSteps)
        var cursor = firstDecision
        var completed = 0
        while (cursor + horizon <= closed.size) {
            val targetStart = cursor - window
            val targetVector = returnVector(closed, targetStart, window)
            val analogs = ArrayList<Pair<Double, Double>>()
            var candidate = 0
            // Candidate's full five-candle outcome must be known before target window starts.
            val candidateLimit = targetStart - window - horizon
            while (candidate <= candidateLimit) {
                val similarity = similarity(targetVector, closed, candidate, window)
                if (similarity >= minSimilarity) {
                    val base = closed[candidate + window - 1].close
                    if (base > 0.0) {
                        val outcome = (closed[candidate + window + horizon - 1].close / base - 1.0) * 100.0
                        analogs.add(similarity to outcome)
                    }
                }
                candidate += window
            }
            val best = analogs.sortedByDescending { it.first }.take(topK)
            if (best.size >= 3) {
                var totalWeight = 0.0
                var expected = 0.0
                var positiveWeight = 0.0
                var negativeWeight = 0.0
                for ((sim, outcome) in best) {
                    val w = (sim.coerceAtLeast(0.0) / 100.0).let { it * it + 0.01 }
                    totalWeight += w
                    expected += outcome * w
                    if (outcome > 0.0) positiveWeight += w
                    if (outcome < 0.0) negativeWeight += w
                }
                expected /= totalWeight
                positiveWeight /= totalWeight
                negativeWeight /= totalWeight
                val direction = when {
                    expected > 0.12 && positiveWeight >= 0.55 -> "LONG"
                    expected < -0.12 && negativeWeight >= 0.55 -> "SHORT"
                    else -> "SIDEWAYS"
                }
                val base = closed[cursor - 1].close
                val actualReturn = if (base > 0.0) (closed[cursor + horizon - 1].close / base - 1.0) * 100.0 else 0.0
                val actual = when {
                    actualReturn > 0.12 -> "LONG"
                    actualReturn < -0.12 -> "SHORT"
                    else -> "SIDEWAYS"
                }
                points.add(BlindReplayPoint(
                    closed[cursor - 1].openTime, direction, actual,
                    maxOf(positiveWeight, negativeWeight) * 100.0,
                    expected, actualReturn, best.size
                ))
            }
            completed++
            if (completed % 5 == 0 || completed == totalSteps) progress(completed, totalSteps)
            cursor += step
        }
        if (points.isEmpty()) return empty("Не найдено достаточно исторических аналогов. Проверьте полноту истории или порог сходства.")
        val directional = points.filter { it.predicted != "SIDEWAYS" }
        val correct = points.count { it.predicted == it.actual }
        val returns = directional.map { p ->
            when (p.predicted) {
                "LONG" -> p.actualReturnPct
                "SHORT" -> -p.actualReturnPct
                else -> 0.0
            }
        }
        var equity = 1.0
        var peak = 1.0
        var maxDd = 0.0
        returns.forEach { r ->
            equity *= (1.0 + r / 100.0)
            peak = maxOf(peak, equity)
            maxDd = maxOf(maxDd, (peak - equity) / peak * 100.0)
        }
        val accuracy = if (points.isEmpty()) 0.0 else correct.toDouble() / points.size * 100.0
        val coverage = directional.size.toDouble() / points.size * 100.0
        val avg = if (returns.isEmpty()) 0.0 else returns.average()
        val cumulative = (equity - 1.0) * 100.0
        val meanAbsError = points.map { kotlin.math.abs(it.predictedReturnPct - it.actualReturnPct) }.average()
        return BlindReplayReport(
            points.size, directional.size, correct, accuracy, coverage, avg, cumulative, maxDd,
            points,
            "BTCUSDT Binance Spot · 15m. Проверочный участок: последние 14 дней (до 1 344 закрытых свечей). " +
                "Прогноз обновляется каждые 5 свечей и оценивает следующие 5 свечей (75 минут). " +
                "Средняя абсолютная ошибка прогноза: %.3f%%. Аналоги и их исходы полностью завершились до целевого окна; " +
                "будущие свечи не используются. Комиссии и проскальзывание пока не вычтены; результаты не гарантируют будущую доходность."
                    .format(java.util.Locale.US, meanAbsError)
        )
    }

    private fun empty(message: String) =
        BlindReplayReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, emptyList(), message)

    private fun returnVector(data: List<StoredCandle>, start: Int, window: Int): DoubleArray {
        val n = window - 1
        val raw = DoubleArray(n) { i ->
            val a = data[start + i].close
            val b = data[start + i + 1].close
            if (a > 0.0 && b > 0.0) ln(b / a) else 0.0
        }
        val mean = raw.average()
        val sd = sqrt(raw.sumOf { (it - mean) * (it - mean) } / n).coerceAtLeast(1e-9)
        return DoubleArray(n) { (raw[it] - mean) / sd }
    }

    private fun similarity(target: DoubleArray, data: List<StoredCandle>, start: Int, window: Int): Double {
        val n = window - 1
        var mean = 0.0
        for (i in 0 until n) {
            val a = data[start + i].close
            val b = data[start + i + 1].close
            mean += if (a > 0.0 && b > 0.0) ln(b / a) else 0.0
        }
        mean /= n
        var variance = 0.0
        var dot = 0.0
        var targetNorm = 0.0
        for (i in 0 until n) {
            val a = data[start + i].close
            val b = data[start + i + 1].close
            val r = (if (a > 0.0 && b > 0.0) ln(b / a) else 0.0) - mean
            variance += r * r
            dot += target[i] * r
            targetNorm += target[i] * target[i]
        }
        val denom = sqrt(variance * targetNorm)
        if (denom <= 0.0) return 0.0
        return (dot / denom).coerceIn(-1.0, 1.0) * 100.0
    }
}
