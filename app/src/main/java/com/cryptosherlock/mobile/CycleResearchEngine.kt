package com.cryptosherlock.mobile

import kotlin.math.max
import kotlin.math.min

data class StrategyStats(
    val name: String, val trades: Int, val winRatePct: Double?, val averageNetPct: Double?,
    val medianNetPct: Double?, val totalNetPct: Double?, val maxDrawdownPct: Double?,
    val testTrades: Int, val testWinRatePct: Double?, val testAverageNetPct: Double?, val note: String
)
data class CycleResearchReport(
    val dailyBars: Int, val splitDate: Long, val buyHoldTrainPct: Double?, val buyHoldTestPct: Double?,
    val strategies: List<StrategyStats>, val caveats: String
)

/** Fixed-rule chronological comparison; signal at close, entry next open, fixed 90d exit. */
class CycleResearchEngine {
    private data class Bar(val time: Long, val open: Double, val high: Double, val low: Double, val close: Double, val volume: Double)
    private data class Trade(val entryTime: Long, val exitTime: Long, val netPct: Double)

    fun analyze(source: List<StoredCandle>, roundTripCostPct: Double = 0.20, horizonDays: Int = 90): CycleResearchReport {
        val daily = toDaily(source)
        if (daily.size < 400) return CycleResearchReport(daily.size, 0L, null, null, emptyList(),
            "Нужно не менее 400 дневных свечей для хронологического сравнения.")
        val split = (daily.size * 0.70).toInt().coerceIn(200, daily.size - 100)
        val splitTime = daily[split].time
        val trainBuyHold = (daily[split - 1].close / daily[0].close - 1.0) * 100.0
        val testBuyHold = (daily.last().close / daily[split].close - 1.0) * 100.0
        val sma50 = DoubleArray(daily.size) { i -> if (i < 49) Double.NaN else daily.subList(i - 49, i + 1).map { it.close }.average() }
        val sma100 = DoubleArray(daily.size) { i -> if (i < 99) Double.NaN else daily.subList(i - 99, i + 1).map { it.close }.average() }
        val sma200 = DoubleArray(daily.size) { i -> if (i < 199) Double.NaN else daily.subList(i - 199, i + 1).map { it.close }.average() }
        val signals = linkedMapOf<String, MutableList<Int>>(
            "SMA 50/100" to mutableListOf(), "SMA 50/200" to mutableListOf(),
            "Пробой 90-дневного диапазона" to mutableListOf(), "Импульс 90д + объём" to mutableListOf()
        )
        for (i in 200 until daily.lastIndex) {
            if (sma50[i - 1] <= sma100[i - 1] && sma50[i] > sma100[i]) signals["SMA 50/100"]!!.add(i)
            if (sma50[i - 1] <= sma200[i - 1] && sma50[i] > sma200[i]) signals["SMA 50/200"]!!.add(i)
            val priorHigh = daily.subList(i - 90, i).maxOf { it.high }
            if (daily[i].close > priorHigh) signals["Пробой 90-дневного диапазона"]!!.add(i)
            val momentum = daily[i].close / daily[i - 90].close - 1.0
            val baseVolume = daily.subList(i - 20, i).map { it.volume }.average().coerceAtLeast(1e-12)
            if (momentum > 0.08 && daily[i].volume / baseVolume > 1.2 && daily[i].close > sma200[i])
                signals["Импульс 90д + объём"]!!.add(i)
        }
        val stats = signals.map { (name, indices) ->
            val trades = ArrayList<Trade>()
            var nextAllowed = 0
            for (signal in indices) {
                val entryIndex = signal + 1
                val exitIndex = entryIndex + horizonDays
                if (entryIndex < nextAllowed || exitIndex >= daily.size) continue
                val entry = daily[entryIndex].open.coerceAtLeast(1e-12)
                val net = (daily[exitIndex].close / entry - 1.0) * 100.0 - roundTripCostPct
                trades.add(Trade(daily[entryIndex].time, daily[exitIndex].time, net))
                nextAllowed = exitIndex + 1
            }
            val train = trades.filter { it.entryTime < splitTime && it.exitTime < splitTime }
            val test = trades.filter { it.entryTime >= splitTime }
            fun avg(list: List<Trade>) = if (list.isEmpty()) null else list.map { it.netPct }.average()
            fun win(list: List<Trade>) = if (list.isEmpty()) null else list.count { it.netPct > 0.0 }.toDouble() / list.size * 100.0
            fun median(list: List<Trade>): Double? {
                if (list.isEmpty()) return null
                val s = list.map { it.netPct }.sorted()
                return if (s.size % 2 == 1) s[s.size / 2] else (s[s.size / 2 - 1] + s[s.size / 2]) / 2.0
            }
            var equity = 1.0; var peak = 1.0; var maxDd = 0.0
            trades.forEach { t -> equity *= (1.0 + t.netPct / 100.0); peak = max(peak, equity); maxDd = max(maxDd, (peak - equity) / peak * 100.0) }
            StrategyStats(name, trades.size, win(trades), avg(trades), median(trades),
                if (trades.isEmpty()) null else (equity - 1.0) * 100.0, maxDd,
                test.size, win(test), avg(test),
                "Сигнал на закрытии; вход по следующему open; горизонт " + horizonDays + "д; без перекрытия. Издержки round-trip " + roundTripCostPct + "%.")
        }
        return CycleResearchReport(daily.size, splitTime, trainBuyHold, testBuyHold, stats,
            "70/30 хронологический split. Правила фиксированы заранее, тестовый отрезок не использовался для настройки. Результат исследовательский, не прогноз. Просадка рассчитана по завершённым сделкам, не по внутрисделочной equity.")
    }

    private fun toDaily(source: List<StoredCandle>): List<Bar> {
        if (source.isEmpty()) return emptyList()
        val sorted = source.sortedBy { it.openTime }; val out = ArrayList<Bar>()
        var day = sorted.first().openTime / 86_400_000L
        var first = sorted.first(); var high = first.high; var low = first.low; var close = first.close; var volume = first.volume
        for (c in sorted.drop(1)) {
            val d = c.openTime / 86_400_000L
            if (d != day) {
                out.add(Bar(day * 86_400_000L, first.open, high, low, close, volume))
                day = d; first = c; high = c.high; low = c.low; close = c.close; volume = c.volume
            } else { high = max(high, c.high); low = min(low, c.low); close = c.close; volume += c.volume }
        }
        out.add(Bar(day * 86_400_000L, first.open, high, low, close, volume))
        return out
    }
}