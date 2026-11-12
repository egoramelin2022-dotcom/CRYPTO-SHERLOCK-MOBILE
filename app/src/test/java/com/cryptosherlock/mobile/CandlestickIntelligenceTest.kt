package com.cryptosherlock.mobile

import org.junit.Assert.*
import org.junit.Test

class CandlestickIntelligenceTest {
    @Test fun detectsHammerAfterDecline() {
        val rows = mutableListOf<StoredCandle>()
        val closes = listOf(110.0, 106.0, 102.0, 98.0, 94.0)
        closes.forEachIndexed { i, close ->
            rows.add(StoredCandle(i * 900000L, close + 1, close + 2, close - 2, close, 100.0))
        }
        rows.add(StoredCandle(5 * 900000L, 90.0, 93.0, 75.0, 92.0, 180.0))
        val result = CandlestickIntelligence().analyze(rows)
        assertTrue(result.patterns.any { it.name == "HAMMER" })
        assertEquals("BULLISH", result.bias)
        assertTrue(result.lowerWickToRange > 0.5)
    }

    @Test fun detectsBullishEngulfing() {
        val rows = listOf(
            StoredCandle(0, 100.0, 102.0, 98.0, 101.0, 100.0),
            StoredCandle(1, 101.0, 102.0, 96.0, 97.0, 100.0),
            StoredCandle(2, 97.0, 98.0, 94.0, 95.0, 100.0),
            StoredCandle(3, 95.0, 96.0, 92.0, 93.0, 100.0),
            StoredCandle(4, 93.0, 94.0, 90.0, 91.0, 100.0),
            StoredCandle(5, 90.0, 97.0, 89.0, 96.0, 180.0)
        )
        val result = CandlestickIntelligence().analyze(rows)
        assertTrue(result.patterns.any { it.name == "BULLISH_ENGULFING" })
    }

    @Test fun returnsNeutralWhenInsufficientHistory() {
        val result = CandlestickIntelligence().analyze(emptyList())
        assertEquals("NEUTRAL", result.bias)
        assertTrue(result.patterns.isEmpty())
    }
}
