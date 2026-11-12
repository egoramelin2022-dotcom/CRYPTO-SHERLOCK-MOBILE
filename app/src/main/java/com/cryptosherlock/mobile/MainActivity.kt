package com.cryptosherlock.mobile

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Color
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.DecimalFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class Candle(val open: Float, val high: Float, val low: Float, val close: Float, val volume: Float)
data class MarketSnapshot(val price: Double, val change: Double, val candles: List<Candle>, val fetchedAt: Long)
data class Signal(val title: String, val detail: String, val rsi: Double, val emaFast: Double, val emaSlow: Double, val bias: String)

class MainActivity : Activity() {
    private val bg = Color.rgb(8, 14, 25)
    private val panel = Color.rgb(17, 27, 43)
    private val mint = Color.rgb(85, 214, 194)
    private val white = Color.rgb(232, 239, 248)
    private val muted = Color.rgb(139, 155, 177)
    private val red = Color.rgb(255, 105, 115)
    private lateinit var price: TextView
    private lateinit var change: TextView
    private lateinit var status: TextView
    private lateinit var chart: CandleChart
    private lateinit var candleInfo: TextView
    private lateinit var signalCard: TextView
    private lateinit var forecastCard: TextView
    private lateinit var refreshButton: Button
    private lateinit var historyButton: Button
    private lateinit var patternButton: Button
    private lateinit var fiveStageButton: Button
    private lateinit var replayButton: Button
    private lateinit var candleStore: CandleStore
    private var interval = "15m"
    private val fmt = DecimalFormat("#,##0.00")
    private val marketExecutor = Executors.newSingleThreadExecutor()
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val historyExecutor = Executors.newSingleThreadExecutor()
    private val loading = AtomicBoolean(false)
    private val handler = Handler(Looper.getMainLooper())
    private var lastSnapshot: MarketSnapshot? = null
    private var autoRefresh = true
    private val refreshTask = object : Runnable {
        override fun run() {
            if (autoRefresh && !isFinishing) loadMarket(false)
            handler.postDelayed(this, 30_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = bg
        window.navigationBarColor = bg
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 14, 16, 10)
            setBackgroundColor(bg)
        }
        root.addView(TextView(this).apply {
            text = "◈  CRYPTO SHERLOCK"
            textSize = 22f
            setTextColor(mint)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        })
        root.addView(TextView(this).apply {
            text = "MARKET INTELLIGENCE  /  BINANCE SPOT"
            textSize = 10f
            setTextColor(muted)
            setPadding(0, 4, 0, 10)
        })
        price = TextView(this).apply {
            text = "BTC / USDT"
            textSize = 29f
            setTextColor(white)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        }
        root.addView(price)
        change = TextView(this).apply {
            text = "Загрузка котировки…"
            textSize = 13f
            setTextColor(mint)
            setPadding(0, 2, 0, 8)
        }
        root.addView(change)

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        listOf("15m", "30m", "1h", "2h", "4h").forEach { tf ->
            row.addView(Button(this).apply {
                text = tf
                textSize = 10f
                isAllCaps = false
                minWidth = 0
                setPadding(0, 0, 0, 0)
                setOnClickListener {
                    if (interval != tf) {
                        interval = tf
                        loadMarket(true)
                    }
                }
            }, LinearLayout.LayoutParams(0, 42, 1f))
        }
        root.addView(row)

        signalCard = TextView(this).apply {
            text = "АНАЛИЗ СИГНАЛА\nОжидаем первые рыночные данные…"
            textSize = 12f
            setTextColor(white)
            setPadding(12, 9, 12, 9)
            setBackgroundColor(panel)
        }
        root.addView(signalCard, LinearLayout.LayoutParams(-1, -2).apply { topMargin = 8 })
        forecastCard = TextView(this).apply {
            text = "MULTI-TIMEFRAME FORECAST\\nОжидаем данные 15m / 1h / 4h / 1d…"
            textSize = 12f
            setTextColor(white)
            setPadding(12, 10, 12, 10)
            setBackgroundColor(panel)
        }
        root.addView(forecastCard, LinearLayout.LayoutParams(-1, -2).apply { topMargin = 6 })
        chart = CandleChart(this).apply { setBackgroundColor(panel) }
        root.addView(chart, LinearLayout.LayoutParams(-1, dp(260)).apply { topMargin = 8; bottomMargin = 4 })
        candleInfo = TextView(this).apply {
            text = "Свечи и объём"
            textSize = 11f
            setTextColor(muted)
            setPadding(2, 3, 2, 3)
        }
        root.addView(candleInfo)
        refreshButton = Button(this).apply {
            text = "ОБНОВИТЬ СЕЙЧАС"
            isAllCaps = false
            setOnClickListener { loadMarket(true) }
        }
        root.addView(refreshButton, LinearLayout.LayoutParams(-1, 46))
        historyButton = Button(this).apply {
            text = "ЗАГРУЗИТЬ ИСТОРИЮ BTC 15M С 2017 ГОДА"
            isAllCaps = false
            setOnClickListener { downloadHistory() }
        }
        root.addView(historyButton, LinearLayout.LayoutParams(-1, 44).apply { topMargin = 4 })
        patternButton = Button(this).apply {
            text = "PATTERN INTELLIGENCE · ПОИСК АНАЛОГОВ"
            isAllCaps = false
            setOnClickListener { runPatternSearch() }
        }
        root.addView(patternButton, LinearLayout.LayoutParams(-1, 44).apply { topMargin = 2 })
        fiveStageButton = Button(this).apply {
            text = "FIVE-STAGE · ПОИСК 5 ЭТАПОВ"
            isAllCaps = false
            setOnClickListener { runFiveStageSearch() }
        }
        root.addView(fiveStageButton, LinearLayout.LayoutParams(-1, 44).apply { topMargin = 2 })
        replayButton = Button(this).apply {
            text = "BLIND REPLAY · ПРОВЕРИТЬ ЯДРО НА ЗАКРЫТОЙ ИСТОРИИ"
            isAllCaps = false
            setOnClickListener { runBlindReplay() }
        }
        root.addView(replayButton, LinearLayout.LayoutParams(-1, 48).apply { topMargin = 6 })
        val portfolioCard = TextView(this).apply {
            text = "ПОРТФЕЛЬ · РЕЖИМ НАБЛЮДЕНИЯ\\n\\nЗдесь появятся выбранные активы, виртуальные позиции, риск на сделку и журнал результатов. Реальные ордера не подключены."
            textSize = 13f
            setTextColor(white)
            setPadding(12, 12, 12, 12)
            setBackgroundColor(panel)
        }
        root.addView(portfolioCard, LinearLayout.LayoutParams(-1, -2).apply { topMargin = 8 })
        status = TextView(this).apply {
            text = "Автообновление каждые 30 секунд · Binance Spot"
            textSize = 10f
            setTextColor(muted)
            setPadding(2, 8, 2, 8)
        }
        root.addView(status)
        val scroll = ScrollView(this).apply {
            isFillViewport = false
            setBackgroundColor(bg)
            addView(root, ViewGroup.LayoutParams(-1, -2))
        }
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(bg)
            addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        }
        val nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setBackgroundColor(panel)
            setPadding(2, 4, 2, 4)
        }
        fun addTab(label: String, target: View) {
            nav.addView(Button(this).apply {
                text = label
                textSize = 9f
                isAllCaps = false
                minWidth = 0
                setPadding(1, 0, 1, 0)
                setOnClickListener {
                    scroll.post { scroll.smoothScrollTo(0, target.top.coerceAtLeast(0)) }
                }
            }, LinearLayout.LayoutParams(0, dp(52), 1f))
        }
        addTab("РЫНОК", price)
        addTab("ШЕРЛОК", patternButton)
        addTab("АНАЛИЗ", forecastCard)
        addTab("REPLAY", replayButton)
        addTab("ПОРТФЕЛЬ", portfolioCard)
        shell.addView(nav, LinearLayout.LayoutParams(-1, dp(56)))
        setContentView(shell)
        candleStore = CandleStore(this)
        status.text = "Запуск · подключаем рынок и локальную базу…"
        // SQLite opening/counting is disk I/O: never do it on Android's UI thread.
        historyExecutor.execute {
            try {
                val saved = candleStore.count("BTCUSDT", "15m")
                runOnUiThread {
                    if (!isFinishing) status.text = "Локальная база: $saved свечей · автообновление 30с"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    if (!isFinishing) status.text = "Локальная база пока недоступна: ${e.message ?: "ошибка"}"
                }
            }
        }
        loadMarket(true)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun loadMarket(showLoading: Boolean) {
        if (!loading.compareAndSet(false, true)) {
            if (showLoading) status.text = "Запрос уже выполняется…"
            return
        }
        if (showLoading) status.text = "Получаем данные Binance…"
        refreshButton.isEnabled = false
        marketExecutor.execute {
            try {
                val ticker = JSONObject(readUrl("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"))
                val p = ticker.getString("lastPrice").toDouble()
                val pct = ticker.getString("priceChangePercent").toDouble()
                val candles = fetchCandles(interval)
                if (candles.size < 30) throw IllegalStateException("Недостаточно свечей для анализа")
                val states = listOf("15m", "1h", "4h", "1d").map { tf ->
                    MarketAnalysisEngine().state(tf, if (tf == interval) candles else fetchCandles(tf))
                }
                val forecast = MarketAnalysisEngine().forecast(states, p)
                val snapshot = MarketSnapshot(p, pct, candles, System.currentTimeMillis())
                val signal = analyze(candles)
                runOnUiThread {
                    lastSnapshot = snapshot
                    render(snapshot, signal)
                    renderForecast(forecast)
                    status.text = "Binance Spot · обновлено " + SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(snapshot.fetchedAt)) + " · 4 таймфрейма · авто 30с"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    status.text = "Ошибка сети: " + (e.message ?: "нет соединения") + " · повтор через 30с"
                    if (lastSnapshot == null) signalCard.text = "АНАЛИЗ НЕДОСТУПЕН\nПроверь подключение к интернету."
                }
            } finally {
                loading.set(false)
                runOnUiThread { refreshButton.isEnabled = true }
            }
        }
    }

    private fun runFiveStageSearch() {
        fiveStageButton.isEnabled = false
        status.text = "Five-Stage: проверяем исторические формации…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", 50000)
                val report = FiveStageStrategy().search(history, 100, 16, 10)
                runOnUiThread {
                    fiveStageButton.isEnabled = true
                    val rows = report.matches.mapIndexed { i, m ->
                        (i + 1).toString() + ". снижение " + String.format(Locale.US, "%.1f", m.declinePct) + "% · восстановление +" + String.format(Locale.US, "%.1f", m.recoveryPct) + "% · обвал " + String.format(Locale.US, "%.1f", m.collapsePct) + "% · после: " + String.format(Locale.US, "%+.2f", m.forwardReturnPct) + "%"
                    }
                    signalCard.text = "FIVE-STAGE STRATEGY · BTCUSDT 15M\nПроверено окон: " + report.testedWindows + "\n" + rows.joinToString("\n") + "\n" + report.message
                    signalCard.setTextColor(white)
                    status.text = "Five-Stage завершён · база: " + history.size + " свечей"
                }
            } catch (e: Exception) {
                runOnUiThread { fiveStageButton.isEnabled = true; status.text = "Ошибка Five-Stage: " + (e.message ?: "неизвестно") }
            }
        }
    }

    private fun runPatternSearch() {
        patternButton.isEnabled = false
        status.text = "Pattern Intelligence: анализ исторической базы…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", 50000)
                val report = PatternIntelligence().search(history, 40, 16, 10)
                runOnUiThread {
                    patternButton.isEnabled = true
                    val lines = report.matches.mapIndexed { index, match ->
                        (index + 1).toString() + ". сходство " + String.format(Locale.US, "%.1f", match.similarity) + "% · после формации " + String.format(Locale.US, "%+.2f", match.forwardReturnPct) + "%"
                    }
                    signalCard.text = "PATTERN INTELLIGENCE · BTCUSDT 15M\nНайдено исторических окон: " + report.sampleCount + "\nСредний результат после топ-аналогов: " + String.format(Locale.US, "%+.2f", report.averageForwardPct) + "% · положительных: " + String.format(Locale.US, "%.1f", report.positiveRatePct) + "%\n" + lines.joinToString("\n") + "\n" + report.note
                    signalCard.setTextColor(white)
                    status.text = "Поиск завершён · локальная база: " + history.size + " свечей"
                }
            } catch (e: Exception) {
                runOnUiThread { patternButton.isEnabled = true; status.text = "Ошибка Pattern Intelligence: " + (e.message ?: "неизвестно") }
            }
        }
    }

    private fun runBlindReplay() {
        replayButton.isEnabled = false
        status.text = "BLIND REPLAY: прогоняем исторические точки строго по времени…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", 50000)
                val report = BlindReplayEngine().run(history, window = 40, horizon = 16, step = 16, minSimilarity = 35.0, topK = 20)
                runOnUiThread {
                    replayButton.isEnabled = true
                    val recent = report.points.takeLast(8).joinToString("\n") {
                        SimpleDateFormat("MM-dd HH:mm", Locale.US).format(Date(it.decisionTime)) +
                            " · прогноз " + it.predicted + " / факт " + it.actual +
                            " · ожидание " + String.format(Locale.US, "%+.2f", it.predictedReturnPct) +
                            "% / факт " + String.format(Locale.US, "%+.2f", it.actualReturnPct) + "%"
                    }
                    signalCard.text = "BLIND REPLAY · PATTERN CORE\n" +
                        "Тестовых решений: " + report.tested + " · сделок: " + report.traded +
                        "\nНаправление верно: " + String.format(Locale.US, "%.1f", report.accuracyPct) +
                        "% · покрытие: " + String.format(Locale.US, "%.1f", report.coveragePct) + "%" +
                        "\nСредний результат на сигнал: " + String.format(Locale.US, "%+.3f", report.averageActualPct) +
                        "% · накопленный: " + String.format(Locale.US, "%+.2f", report.cumulativeReturnPct) +
                        "% · max drawdown: " + String.format(Locale.US, "%.2f", report.maxDrawdownPct) +
                        "%\nПоследние решения:\n" + recent + "\n" + report.notes
                    signalCard.setTextColor(white)
                    status.text = "Blind Replay завершён · исторических свечей: " + history.size
                }
            } catch (e: Exception) {
                runOnUiThread {
                    replayButton.isEnabled = true
                    status.text = "Ошибка Blind Replay: " + (e.message ?: "неизвестно")
                }
            }
        }
    }

    private fun downloadHistory() {
        historyButton.isEnabled = false
        status.text = "Подготовка загрузки исторических данных…"
        historyExecutor.execute {
            try {
                val total = BinanceHistoryDownloader(candleStore).sync15m { message ->
                    runOnUiThread { status.text = message + " · загрузка может занять время" }
                }
                runOnUiThread {
                    historyButton.isEnabled = true
                    status.text = "Готово: добавлено " + total + " свечей. Всего в базе: " + candleStore.count("BTCUSDT", "15m")
                }
            } catch (e: Exception) {
                runOnUiThread {
                    historyButton.isEnabled = true
                    status.text = "Загрузка прервана: " + (e.message ?: "ошибка сети") + ". Можно продолжить позже — загрузчик продолжит с последней свечи."
                }
            }
        }
    }

    private fun fetchCandles(tf: String): List<Candle> {
        val arr = JSONArray(readUrl("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=" + tf + "&limit=120"))
        return (0 until arr.length()).map { i ->
            val a = arr.getJSONArray(i)
            Candle(a.getString(1).toFloat(), a.getString(2).toFloat(), a.getString(3).toFloat(),
                a.getString(4).toFloat(), a.getString(5).toFloat())
        }
    }

    private fun renderForecast(f: ForecastSnapshot) {
        val lines = f.states.joinToString("\\n") {
            it.interval + " · " + it.bias + " · RSI " + String.format(Locale.US, "%.1f", it.rsi) +
                " · ATR " + String.format(Locale.US, "%.2f", it.atrPct) + "% · объём x" +
                String.format(Locale.US, "%.2f", it.volumeRatio)
        }
        forecastCard.text = "FORECAST ENGINE · ЭКСПЕРИМЕНТАЛЬНЫЙ\\n" +
            "LONG " + f.longPct + "%  |  SHORT " + f.shortPct + "%  |  SIDEWAYS " + f.sidewaysPct + "%\\n" +
            f.entryState + "\\nЗона наблюдения: " + fmt.format(f.entryLow) + " — " + fmt.format(f.entryHigh) +
            "\\nИнвалидация сценария: " + fmt.format(f.invalidation) + "\\n" + lines +
            "\\nОценки основаны на правилах, НЕ откалиброваны как реальные вероятности. " + f.rationale
    }

    private fun render(s: MarketSnapshot, a: Signal) {
        price.text = "$" + fmt.format(s.price)
        change.text = (if (s.change >= 0) "▲ +" else "▼ ") + String.format(Locale.US, "%.2f%%", s.change) + "  ·  BTCUSDT"
        change.setTextColor(if (s.change >= 0) mint else red)
        chart.setCandles(s.candles)
        candleInfo.text = "BTCUSDT  •  $interval  •  " + s.candles.size + " свечей  •  RSI " + String.format(Locale.US, "%.1f", a.rsi)
        signalCard.text = a.title + "\n" + a.detail + "\nEMA 9: " + fmt.format(a.emaFast) + "  |  EMA 21: " + fmt.format(a.emaSlow) + "  |  RSI 14: " + String.format(Locale.US, "%.1f", a.rsi)
        signalCard.setTextColor(if (a.bias == "LONG") mint else if (a.bias == "SHORT") red else white)
    }

    private fun analyze(c: List<Candle>): Signal {
        val closes = c.map { it.close.toDouble() }
        fun ema(period: Int): Double {
            val k = 2.0 / (period + 1.0)
            var value = closes.take(period).average()
            for (i in period until closes.size) value = closes[i] * k + value * (1.0 - k)
            return value
        }
        var gains = 0.0
        var losses = 0.0
        for (i in closes.size - 14 until closes.size) {
            val d = closes[i] - closes[i - 1]
            if (d > 0) gains += d else losses -= d
        }
        val avgGain = gains / 14.0
        val avgLoss = losses / 14.0
        val rsi = if (avgLoss == 0.0) 100.0 else 100.0 - 100.0 / (1.0 + avgGain / avgLoss)
        val fast = ema(9)
        val slow = ema(21)
        val last = closes.last()
        return when {
            fast > slow && last > slow && rsi in 50.0..68.0 ->
                Signal("ВОЗМОЖНОЕ БЫЧЬЕ УСЛОВИЕ", "Тренд вверх подтверждается EMA. Это фильтр наблюдения, не команда на покупку.", rsi, fast, slow, "LONG")
            fast < slow && last < slow && rsi in 32.0..50.0 ->
                Signal("ВОЗМОЖНОЕ МЕДВЕЖЬЕ УСЛОВИЕ", "Тренд вниз подтверждается EMA. Это предупреждение о слабости, не команда на продажу.", rsi, fast, slow, "SHORT")
            else ->
                Signal("ОЖИДАНИЕ · НЕТ ЧИСТОГО СИГНАЛА", "Условия EMA/RSI расходятся или рынок в нейтральной зоне. Не входить только ради сделки.", rsi, fast, slow, "WAIT")
        }
    }

    private fun readUrl(address: String): String {
        val connection = URL(address).openConnection() as HttpURLConnection
        connection.connectTimeout = 8_000
        connection.readTimeout = 8_000
        connection.setRequestProperty("User-Agent", "CryptoSherlockMobile/1.1")
        return try {
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    override fun onResume() {
        super.onResume()
        autoRefresh = true
        handler.removeCallbacks(refreshTask)
        handler.postDelayed(refreshTask, 30_000L)
    }

    override fun onPause() {
        autoRefresh = false
        handler.removeCallbacks(refreshTask)
        super.onPause()
    }

    override fun onDestroy() {
        marketExecutor.shutdownNow()
        analysisExecutor.shutdownNow()
        historyExecutor.shutdownNow()
        super.onDestroy()
    }

    class CandleChart(context: android.content.Context) : View(context) {
        private val up = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(65, 205, 158); strokeWidth = 2f }
        private val down = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(245, 91, 106); strokeWidth = 2f }
        private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(42, 57, 77); strokeWidth = 1f }
        private val vol = Paint(Paint.ANTI_ALIAS_FLAG)
        private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(139, 155, 177); textSize = 22f }
        private var data: List<Candle> = emptyList()
        fun setCandles(c: List<Candle>) { data = c; invalidate() }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val w = width.toFloat()
            val h = height.toFloat()
            for (i in 1..4) canvas.drawLine(0f, h * i / 5, w, h * i / 5, grid)
            if (data.isEmpty()) {
                canvas.drawText("Ждём рыночные данные…", 24f, h / 2, label)
                return
            }
            val top = 18f
            val bottom = h * 0.77f
            val min = data.minOf { it.low }
            val max = data.maxOf { it.high }
            val span = (max - min).coerceAtLeast(0.01f)
            val step = w / data.size
            val body = (step * 0.58f).coerceAtLeast(2f)
            val maxVol = data.maxOf { it.volume }.coerceAtLeast(1f)
            data.forEachIndexed { i, d ->
                val x = i * step + step / 2
                val yh = bottom - (d.high - min) / span * (bottom - top)
                val yl = bottom - (d.low - min) / span * (bottom - top)
                val yo = bottom - (d.open - min) / span * (bottom - top)
                val yc = bottom - (d.close - min) / span * (bottom - top)
                val paint = if (d.close >= d.open) up else down
                canvas.drawLine(x, yh, x, yl, paint)
                canvas.drawRect(x - body / 2, minOf(yo, yc), x + body / 2, maxOf(yc, yo + 2f), paint)
                vol.color = paint.color
                val vh = d.volume / maxVol * (h * 0.16f)
                canvas.drawRect(x - body / 2, h - vh, x + body / 2, h - 3f, vol)
            }
        }
    }
}