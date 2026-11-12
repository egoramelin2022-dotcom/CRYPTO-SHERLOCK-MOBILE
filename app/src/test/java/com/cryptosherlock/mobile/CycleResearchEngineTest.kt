package com.cryptosherlock.mobile

import org.junit.Assert.*
import org.junit.Test

class CycleResearchEngineTest {
    @Test fun rejectsShortHistory() {
        val rows = (0 until 200).map { i ->
            val p = 100.0 + i
            StoredCandle(i * 86_400_000L, p, p + 2, p - 2, p + 1, 1000.0)
        }
        val report = CycleResearchEngine().analyze(rows)
        assertTrue(report.strategies.isEmpty())
        assertTrue(report.caveats.contains("400"))
    }

    @Test fun producesChronologicalBenchmarkOnSyntheticHistory() {
        val rows = (0 until 700).map { i ->
            val p = 100.0 + i * 0.35 + kotlin.math.sin(i / 17.0) * 4.0
            StoredCandle(i * 86_400_000L, p - 0.2, p + 1.0, p - 1.0, p, 1000.0 + (i % 9) * 20.0)
        }
        val report = CycleResearchEngine().analyze(rows, roundTripCostPct = 0.20, horizonDays = 30)
        assertEquals(700, report.dailyBars)
        assertTrue(report.splitDate > 0L)
        assertNotNull(report.buyHoldTrainPct)
        assertNotNull(report.buyHoldTestPct)
        assertEquals(4, report.strategies.size)
        assertTrue(report.strategies.all { it.note.contains("следующему open") })
    }

    @Test fun costsAreDeductedFromNetTradeReturns() {
        val rows = (0 until 700).map { i ->
            val p = 100.0 + i * 0.3 + kotlin.math.sin(i / 11.0) * 6.0
            StoredCandle(i * 86_400_000L, p - 0.1, p + 1.0, p - 1.0, p, 1000.0)
        }
        val lowCost = CycleResearchEngine().analyze(rows, 0.0, 20)
        val highCost = CycleResearchEngine().analyze(rows, 1.0, 20)
        lowCost.strategies.zip(highCost.strategies).forEach { (a,b) ->
            if (a.averageNetPct != null && b.averageNetPct != null) assertEquals(1.0, a.averageNetPct!! - b.averageNetPct!!, 1e-8)
        }
    }
}