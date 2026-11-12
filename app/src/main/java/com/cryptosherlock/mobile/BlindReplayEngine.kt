package com.cryptosherlock.mobile

import kotlin.math.abs
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
 * Chronological blind replay:
 * at each decision timestamp, the target contains only candles already closed;
 * analog windows and their forward outcomes must be fully completed before that
 * timestamp. The next horizon is revealed only for scoring after the prediction.
 */
class BlindReplayEngine {
    fun run(
        history: List<StoredCandle>,
        window: Int = 40,
        horizon: Int = 16,
        step: Int = 16,
        minSimilarity: Double = 35.0,
        topK: Int = 20,
        progress: (Int, Int) -> Unit = { _, _ -> }
    ): BlindReplayReport {
        require(window >= 10 && horizon >= 1 && step >= 1 && topK >= 1)
        if (history.size < window * 4 + horizon * 3) {
            return empty("Для слепого теста мало истории: нужно несколько независимых окон и завершённых исходов.")
        }
        val points = ArrayList<BlindReplayPoint>()
        var cursor = window * 3 + horizon
        val totalSteps = ((history.size - horizon - cursor) / step + 1).coerceAtLeast(1)
        var completedSteps = 0
        while (cursor + horizon <= history.size) {
            val targetStart = cursor - window
            val target = history.subList(targetStart, cursor)
            val targetVector = vector(target)
            val analogs = ArrayList<Pair<Double, Double>>()
            var candidate = 0
            val candidateLimit = targetStart - window - horizon
            while (candidate <= candidateLimit) {
                val sample = history.subList(candidate, candidate + window)
                val similarity = cosine(targetVector, vector(sample))
                if (similarity >= minSimilarity) {
                    val base = sample.last().close
                    val outcome = (history[candidate + window + horizon - 1].close / base - 1.0) * 100.0
                    analogs.add(similarity to outcome)
                }
                candidate += window
            }
            val best = analogs.sortedByDescending { it.first }.take(topK)
            if (best.size >= 3) {
                val weights = best.map { (it.first.coerceAtLeast(0.0) / 100.0).let { w -> w * w + 0.01 } }
                val totalWeight = weights.sum()
                val expected = best.indices.sumOf { best[it].second * weights[it] } / totalWeight
                val positiveWeight = best.indices.filter { best[it].second > 0.0 }.sumOf { weights[it] } / totalWeight
                val negativeWeight = best.indices.filter { best[it].second < 0.0 }.sumOf { weights[it] } / totalWeight
                val direction = when {
                    expected > 0.12 && positiveWeight >= 0.55 -> "LONG"
                    expected < -0.12 && negativeWeight >= 0.55 -> "SHORT"
                    else -> "SIDEWAYS"
                }
                val future = history.subList(cursor, cursor + horizon)
                val base = history[cursor - 1].close
                val actualReturn = (future.last().close / base - 1.0) * 100.0
                val actual = when {
                    actualReturn > 0.12 -> "LONG"
                    actualReturn < -0.12 -> "SHORT"
                    else -> "SIDEWAYS"
                }
                points.add(BlindReplayPoint(
                    history[cursor - 1].openTime, direction, actual,
                    maxOf(positiveWeight, negativeWeight) * 100.0,
                    expected, actualReturn, best.size
                ))
            }
            completedSteps++
            if (completedSteps % 10 == 0 || completedSteps == totalSteps) progress(completedSteps, totalSteps)
            cursor += step
        }
        if (points.isEmpty()) return empty("Аналоги не прошли минимальный порог сходства. Снизьте порог или загрузите больше истории.")
        val directional = points.filter { it.predicted != "SIDEWAYS" }
        val correct = directional.count { it.predicted == it.actual }
        val returns = directional.map { p ->
            when {
                p.predicted == "LONG" -> p.actualReturnPct
                p.predicted == "SHORT" -> -p.actualReturnPct
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
        val accuracy = if (directional.isEmpty()) 0.0 else correct.toDouble() / directional.size * 100.0
        val coverage = directional.size.toDouble() / points.size * 100.0
        val avg = if (returns.isEmpty()) 0.0 else returns.average()
        val cumulative = (equity - 1.0) * 100.0
        return BlindReplayReport(points.size, directional.size, correct, accuracy, coverage, avg, cumulative, maxDd,
            points.takeLast(30),
            "Исторический walk-forward replay без доступа к будущим свечам на момент решения. Это исследовательский прогон: без комиссий, проскальзывания и funding; пересекающиеся тестовые периоды возможны. Результат не является доказательством будущей доходности.")
    }

    private fun empty(message: String) = BlindReplayReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, emptyList(), message)

    private fun vector(c: List<StoredCandle>): DoubleArray {
        val raw = DoubleArray(c.size - 1) { i ->
            if (c[i].close <= 0.0) 0.0 else ln(c[i + 1].close / c[i].close)
        }
        val mean = raw.average()
        val sd = sqrt(raw.map { (it - mean) * (it - mean) }.average()).coerceAtLeast(1e-9)
        return DoubleArray(raw.size) { (raw[it] - mean) / sd }
    }

    private fun cosine(a: DoubleArray, b: DoubleArray): Double {
        var dot = 0.0
        var aa = 0.0
        var bb = 0.0
        for (i in a.indices) {
            dot += a[i] * b[i]
            aa += a[i] * a[i]
            bb += b[i] * b[i]
        }
        if (aa <= 0.0 || bb <= 0.0) return 0.0
        return (dot / sqrt(aa * bb)).coerceIn(-1.0, 1.0) * 100.0
    }
}
