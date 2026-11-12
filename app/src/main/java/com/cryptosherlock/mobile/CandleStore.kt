package com.cryptosherlock.mobile

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class CandleStore(context: Context) : SQLiteOpenHelper(context, "crypto_sherlock.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE candles (
            symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time INTEGER NOT NULL,
            open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
            volume REAL NOT NULL, PRIMARY KEY(symbol, interval, open_time))""")
        db.execSQL("CREATE INDEX idx_candles_time ON candles(symbol, interval, open_time)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) { }
    fun saveBatch(symbol: String, interval: String, rows: List<StoredCandle>) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            for (row in rows) {
                val v = ContentValues().apply {
                    put("symbol", symbol); put("interval", interval); put("open_time", row.openTime)
                    put("open", row.open); put("high", row.high); put("low", row.low)
                    put("close", row.close); put("volume", row.volume)
                }
                db.insertWithOnConflict("candles", null, v, SQLiteDatabase.CONFLICT_REPLACE)
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }
    fun latestOpenTime(symbol: String, interval: String): Long? {
        readableDatabase.rawQuery("SELECT MAX(open_time) FROM candles WHERE symbol=? AND interval=?", arrayOf(symbol, interval)).use { c ->
            return if (c.moveToFirst() && !c.isNull(0)) c.getLong(0) else null
        }
    }
    fun count(symbol: String, interval: String): Long {
        readableDatabase.rawQuery("SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?", arrayOf(symbol, interval)).use { c ->
            return if (c.moveToFirst()) c.getLong(0) else 0L
        }
    }
    fun readLatest(symbol: String, interval: String, limit: Int): List<StoredCandle> {
        val out = ArrayList<StoredCandle>()
        readableDatabase.rawQuery("SELECT open_time,open,high,low,close,volume FROM candles WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT ?", arrayOf(symbol, interval, limit.toString())).use { c ->
            while (c.moveToNext()) out.add(StoredCandle(c.getLong(0), c.getDouble(1), c.getDouble(2), c.getDouble(3), c.getDouble(4), c.getDouble(5)))
        }
        return out.asReversed()
    }
}
data class StoredCandle(val openTime: Long, val open: Double, val high: Double, val low: Double, val close: Double, val volume: Double)