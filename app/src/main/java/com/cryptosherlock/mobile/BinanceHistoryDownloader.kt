package com.cryptosherlock.mobile

import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

class BinanceHistoryDownloader(private val store: CandleStore) {
    companion object { const val FIRST_BTCUSDT_15M = 1502942400000L }

    fun sync15m(onProgress: (String) -> Unit): Long {
        val symbol = "BTCUSDT"
        val interval = "15m"
        var cursor = (store.latestOpenTime(symbol, interval)?.plus(900000L)) ?: FIRST_BTCUSDT_15M
        var inserted = 0L
        while (true) {
            val endpoint = "https://api.binance.com/api/v3/klines?symbol=$symbol&interval=$interval&startTime=$cursor&limit=1000"
            val batch = fetchWithRetry(endpoint)
            if (batch.length() == 0) break
            val rows = ArrayList<StoredCandle>(batch.length())
            var lastTime = cursor
            for (i in 0 until batch.length()) {
                val item = batch.getJSONArray(i)
                val t = item.getLong(0)
                rows.add(StoredCandle(t, item.getString(1).toDouble(), item.getString(2).toDouble(),
                    item.getString(3).toDouble(), item.getString(4).toDouble(), item.getString(5).toDouble()))
                if (t > lastTime) lastTime = t
            }
            if (lastTime < cursor) throw IllegalStateException("Binance вернула некорректную последовательность свечей")
            store.saveBatch(symbol, interval, rows)
            inserted += rows.size
            cursor = lastTime + 900000L
            onProgress("Загружено: +$inserted свечей · в базе: ${store.count(symbol, interval)}")
            if (batch.length() < 1000) break
            Thread.sleep(300)
        }
        return inserted
    }

    private fun fetchWithRetry(endpoint: String): JSONArray {
        var lastError: Exception? = null
        for (attempt in 0 until 5) {
            var connection: HttpURLConnection? = null
            try {
                connection = URL(endpoint).openConnection() as HttpURLConnection
                connection.connectTimeout = 10000
                connection.readTimeout = 20000
                connection.setRequestProperty("User-Agent", "CryptoSherlockMobile/1.4")
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() } ?: ""
                if (code == 429 || code == 418 || code >= 500) {
                    val retryHeader = connection.getHeaderField("Retry-After")?.toLongOrNull()
                    val waitMs = (retryHeader?.times(1000L) ?: (1000L shl attempt)).coerceAtMost(30000L)
                    lastError = IllegalStateException("HTTP $code от Binance")
                    if (attempt < 4) {
                        Thread.sleep(waitMs)
                        continue
                    }
                    throw lastError!!
                }
                if (code !in 200..299) throw IllegalStateException("Binance HTTP $code: $body")
                return JSONArray(body)
            } catch (e: Exception) {
                lastError = e
                if (attempt == 4) throw e
                if (e.message?.contains("HTTP 4") == true && e.message?.contains("HTTP 429") != true && e.message?.contains("HTTP 418") != true) throw e
                Thread.sleep((1000L shl attempt).coerceAtMost(16000L))
            } finally {
                connection?.disconnect()
            }
        }
        throw lastError ?: IllegalStateException("Не удалось получить данные Binance")
    }
}