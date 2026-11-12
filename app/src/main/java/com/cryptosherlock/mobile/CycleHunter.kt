package com.cryptosherlock.mobile

import kotlin.math.max
import kotlin.math.min

data class CycleSignal(
    val time: Long,
    val price: Double,
    val forward30Pct: Double?,
    val forward90Pct: Double?,
    val forward180Pct: Double?,
    val forward365Pct: Double?,
    val forward730Pct: Double?,
    val maxRise365Pct: Double?,
    val maxDrop365Pct: Double?
)

data class CycleReport(
    val dailyBars: Int,
    val goldenCrosses: Int,
    val evaluated365: Int,
    val average30Pct: Double?,
    val average90Pct: Double?,
    val average180Pct: Double?,
    val average365Pct: Double?,
    val positive365Pct: Double?,
    val median365Pct: Double?,
    val currentSma50: Double?,
    val currentSma100: Double?,
    val currentState: String,
    val signals: List<CycleSignal>,
    val note: String
)

/**
 * Long-cycle research on UTC daily candles derived from the locally stored 15m feed.
 * A signal is recorded only when SMA50 crosses above SMA100 using data available
 * at that close. Future bars are used exclusively for outcome evaluation.
 */
class CycleHunter {
    fun analyze(source: List<StoredCandle>, examples: Int = 8): CycleReport {
        val daily = aggregateDaily(source)
        if (daily.size < 120) return CycleReport(
            daily.size, 0, 0, null, null, null, null, null, null, null, null,
            "Недостаточно дневной истории", emptyList(),
            "Нужно минимум 120 завершённых дневных свечей. Загрузи BTCUSDT 15m историю."
        )

        val closes = daily.map { it.close }
        val sma50 = DoubleArray(daily.size) { i ->
            if (i < 49) Double.NaN else closes.subList(i - 49, i + 1).average()
        }
        val sma100 = DoubleArray(daily.size) { i ->
            if (i < 99) Double.NaN else closes.subList(i - 99, i + 1).average()
        }
        val rawSignals = ArrayList<CycleSignal>()
        for (i in 100 until daily.size) {
            if (sma50[i - 1] <= sma100[i - 1] && sma50[i] > sma100[i]) {
                val base = closes[i].coerceAtLeast(1e-12)
                fun futureReturn(days: Int): Double? =
                    if (i + days < daily.size) (closes[i + days] / base - 1.0) * 100.0 else null
                val end = min(daily.lastIndex, i + 365)
                val future = if (end > i) daily.subList(i + 1, end + 1) else emptyList()
                val maxRise = if (future.isEmpty()) null else (future.maxOf { it.high } / base - 1.0) * 100.0
                val maxDrop = if (future.isEmpty()) null else (future.minOf { it.low } / base - 1.0) * 100.0
                rawSignals.add(CycleSignal(
                    daily[i].openTime, base, futureReturn(30), futureReturn(90),
                    futureReturn(180), futureReturn(365), futureReturn(730), maxRise, maxDrop
                ))
            }
        }
        val evaluated = rawSignals.mapNotNull { it.forward365Pct }
        fun avg(values: List<Double?>): Double? {
            val v = values.filterNotNull()
            return if (v.isEmpty()) null else v.average()
        }
        val sorted = evaluated.sorted()
        val median = if (sorted.isEmpty()) null else if (sorted.size % 2 == 1) sorted[sorted.size / 2]
            else (sorted[sorted.size / 2 - 1] + sorted[sorted.size / 2]) / 2.0
        val last = daily.lastIndex
        val state = if (sma50[last] > sma100[last]) "SMA50 выше SMA100 · бычья фаза" else "SMA50 ниже SMA100 · медвежья фаза"
        val note = "Сигнал — пересечение SMA50 вверх через SMA100 на закрытии дневной свечи. История 15m агрегирована в UTC-дни. Доходность считается от цены закрытия сигнала; без комиссий, проскальзывания и дивидендов. Пересечения не гарантируют повторения циклов. Источник локальной базы начинается с доступной даты Binance, поэтому цикл 2015 года здесь не покрывается."
        return CycleReport(
            daily.size, rawSignals.size, evaluated.size,
            avg(rawSignals.map { it.forward30Pct }), avg(rawSignals.map { it.forward90Pct }),
            avg(rawSignals.map { it.forward180Pct }), avg(rawSignals.map { it.forward365Pct }),
            if (evaluated.isEmpty()) null else evaluated.count { it > 0.0 }.toDouble() / evaluated.size * 100.0,
            median, sma50[last], sma100[last], state,
            rawSignals.takeLast(examples).asReversed(), note
        )
    }

    private fun aggregateDaily(source: List<StoredCandle>): List<StoredCandle> {
        if (source.isEmpty()) return emptyList()
        val sorted = source.sortedBy { it.openTime }
        val out = ArrayList<StoredCandle>()
        var day = sorted.first().openTime / 86_400_000L
        var first = sorted.first()
        var high = first.high
        var low = first.low
        var close = first.close
        var volume = first.volume
        for (c in sorted.drop(1)) {
            val nextDay = c.openTime / 86_400_000L
            if (nextDay != day) {
                out.add(StoredCandle(day * 86_400_000L, first.open, high, low, close, volume))
                day = nextDay
                first = c
                high = c.high
                low = c.low
                close = c.close
                volume = c.volume
            } else {
                high = max(high, c.high)
                low = min(low, c.low)
                close = c.close
                volume += c.volume
            }
        }
        out.add(StoredCandle(day * 86_400_000L, first.open, high, low, close, volume))
        return out
    }
}
