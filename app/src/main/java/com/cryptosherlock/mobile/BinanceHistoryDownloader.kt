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
            val connection = URL(endpoint).openConnection() as HttpURLConnection
            connection.connectTimeout = 10000
            connection.readTimeout = 15000
            connection.setRequestProperty("User-Agent", "CryptoSherlockMobile/1.2")
            val payload = try { connection.inputStream.bufferedReader().use { it.readText() } }
                finally { connection.disconnect() }
            val batch = JSONArray(payload)
            if (batch.length() == 0) break
            val rows = ArrayList<StoredCandle>(batch.length())
            var lastTime = cursor
            for (i in 0 until batch.length()) {
                val item = batch.getJSONArray(i)
                val t = item.getLong(0)
                rows.add(StoredCandle(t, item.getString(1).toDouble(), item.getString(2).toDouble(), item.getString(3).toDouble(), item.getString(4).toDouble(), item.getString(5).toDouble()))
                if (t > lastTime) lastTime = t
            }
            store.saveBatch(symbol, interval, rows)
            inserted += rows.size
            cursor = lastTime + 900000L
            onProgress("Загружено: +" + inserted + " свечей · в базе: " + store.count(symbol, interval))
            if (batch.length() < 1000) break
            Thread.sleep(250)
        }
        return inserted
    }
}