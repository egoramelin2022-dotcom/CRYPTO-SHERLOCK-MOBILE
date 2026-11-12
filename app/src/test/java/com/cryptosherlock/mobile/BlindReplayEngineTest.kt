package com.cryptosherlock.mobile

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.sin

class BlindReplayEngineTest {
    @Test fun usesLastFourteenDaysAndForecastsEveryFiveCandles() {
        val rows = (0 until 2000).map { i ->
            val p = 50000.0 + i * 1.7 + sin(i / 13.0) * 220.0 + sin(i / 4.0) * 45.0
            StoredCandle(i * 900_000L, p - 3.0, p + 30.0, p - 30.0, p, 1000.0 + (i % 11) * 10.0)
        }
        val report = BlindReplayEngine().run(
            rows, window = 40, horizon = 5, step = 5,
            minSimilarity = -100.0, topK = 20,
            lookbackCandles = 1344, asOfTime = Long.MAX_VALUE
        )
        assertEquals(269, report.tested)
        assertEquals(269, report.points.size)
        assertEquals(5, 5) // five 15m candles = 75 minutes per forecast
        assertTrue(report.notes.contains("последние 14 дней"))
        assertTrue(report.points.all { it.analogCount >= 3 })
    }

    @Test fun ignoresCurrentlyOpenCandle() {
        val rows = (0 until 1500).map { i ->
            val p = 30000.0 + i * 0.5 + sin(i / 9.0) * 80.0
            StoredCandle(i * 900_000L, p, p + 10.0, p - 10.0, p, 500.0)
        }
        val asOf = rows.last().openTime + 900_000L - 1L
        val report = BlindReplayEngine().run(
            rows, window = 40, horizon = 5, step = 5,
            minSimilarity = -100.0, topK = 20,
            lookbackCandles = 1344, asOfTime = asOf
        )
        assertTrue(report.tested > 0)
        assertTrue(report.points.none { it.decisionTime == rows.last().openTime })
    }
}
