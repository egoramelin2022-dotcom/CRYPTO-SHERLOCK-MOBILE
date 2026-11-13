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
    private lateinit var researchResult: TextView
    private lateinit var replayResult: TextView
    private lateinit var forecastCard: TextView
    private lateinit var refreshButton: Button
    private lateinit var serverButton: Button
    private lateinit var historyButton: Button
    private lateinit var patternButton: Button
    private lateinit var fiveStageButton: Button
    private lateinit var cycleButton: Button
    private lateinit var auditButton: Button
    private lateinit var pipelineButton: Button
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
        candleStore = CandleStore(this)

        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(bg) }
        val host = FrameLayout(this).apply { setBackgroundColor(bg) }
        val pages = LinkedHashMap<String, ScrollView>()
        fun makePage(key: String): LinearLayout {
            val body = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(16), dp(16), dp(20))
                setBackgroundColor(bg)
            }
            val scroll = ScrollView(this).apply { isFillViewport = false; addView(body, ViewGroup.LayoutParams(-1, -2)) }
            pages[key] = scroll
            host.addView(scroll, FrameLayout.LayoutParams(-1, -1))
            scroll.visibility = if (key == "РЫНОК") View.VISIBLE else View.GONE
            return body
        }
        fun title(body: LinearLayout, main: String, sub: String) {
            body.addView(TextView(this).apply {
                text = main; textSize = 22f; setTextColor(mint)
                typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.BOLD)
            })
            body.addView(TextView(this).apply {
                text = sub; textSize = 11f; setTextColor(muted); setPadding(0, dp(4), 0, dp(14))
            })
        }
        fun card(text: String): TextView = TextView(this).apply {
            this.text = text; textSize = 12f; setTextColor(white)
            setPadding(dp(14), dp(13), dp(14), dp(13))
            setBackgroundColor(panel); setLineSpacing(dp(2).toFloat(), 1f)
        }
        fun label(body: LinearLayout, name: String) {
            body.addView(TextView(this).apply {
                text = name; textSize = 11f; setTextColor(muted)
                typeface = android.graphics.Typeface.DEFAULT_BOLD
                setPadding(dp(2), dp(14), dp(2), dp(7))
            })
        }
        fun button(text: String, action: () -> Unit): Button = Button(this).apply {
            this.text = text; textSize = 11f; isAllCaps = false; setOnClickListener { action() }
        }

        // 01 — MARKET
        val market = makePage("РЫНОК")
        title(market, "◈ SHERLOCK", "MARKET INTELLIGENCE  /  BINANCE SPOT")
        price = TextView(this).apply {
            text = "BTC / USDT"; textSize = 34f; setTextColor(white)
            typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.BOLD)
        }
        market.addView(price)
        change = TextView(this).apply { text = "Подключаем рынок…"; textSize = 14f; setTextColor(mint); setPadding(0, dp(3), 0, dp(12)) }
        market.addView(change)
        val tf = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        listOf("15m", "30m", "1h", "2h", "4h").forEach { frame ->
            tf.addView(button(frame) {
                if (interval != frame) { interval = frame; loadMarket(true) }
            }, LinearLayout.LayoutParams(0, dp(42), 1f))
        }
        market.addView(tf)
        label(market, "РЫНОЧНЫЙ ИМПУЛЬС")
        signalCard = card("Ожидаем данные и подтверждения…")
        market.addView(signalCard)
        label(market, "PRICE ACTION  ·  BTCUSDT")
        chart = CandleChart(this).apply { setBackgroundColor(panel) }
        market.addView(chart, LinearLayout.LayoutParams(-1, dp(285)))
        candleInfo = TextView(this).apply { text = "Свечи и объём"; textSize = 10f; setTextColor(muted); setPadding(2, dp(5), 2, dp(5)) }
        market.addView(candleInfo)
        refreshButton = button("↻  ОБНОВИТЬ РЫНОК") { loadMarket(true) }
        market.addView(refreshButton, LinearLayout.LayoutParams(-1, dp(46)).apply { topMargin = dp(8) })
        serverButton = button("⚙  ПОДКЛЮЧЕНИЕ К СЕРВЕРУ") { configureServer() }
        market.addView(serverButton, LinearLayout.LayoutParams(-1, dp(42)).apply { topMargin = dp(6) })

        // 02 — SHERLOCK LAB
        val lab = makePage("ШЕРЛОК")
        title(lab, "PATTERN LAB", "Поиск повторяющегося поведения цены · локальная история")
        historyButton = button("↓  ЗАГРУЗИТЬ BTCUSDT 15M С 2017 ГОДА") { downloadHistory() }
        lab.addView(historyButton, LinearLayout.LayoutParams(-1, dp(48)))
        label(lab, "ДВА НЕЗАВИСИМЫХ РЕЖИМА")
        patternButton = button("PATTERN INTELLIGENCE  ·  СВОБОДНЫЙ ПОИСК") { runPatternSearch() }
        lab.addView(patternButton, LinearLayout.LayoutParams(-1, dp(48)))
        fiveStageButton = button("FIVE-STAGE  ·  МОДЕЛЬ ПЯТИ ЭТАПОВ") { runFiveStageSearch() }
        lab.addView(fiveStageButton, LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(7) })
        cycleButton = button("CYCLE HUNTER  ·  ПОИСК БОЛЬШИХ ЦИКЛОВ") { runCycleHunter() }
        lab.addView(cycleButton, LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(7) })
        auditButton = button("SERVER DATA AUDIT · ПРОВЕРИТЬ БАЗУ") {
            startResearchJob("/v1/research/audit", "АУДИТ ИСТОРИЧЕСКОЙ БАЗЫ", auditButton)
        }
        lab.addView(auditButton, LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(7) })
        pipelineButton = button("SERVER PIPELINE · ПОСТРОИТЬ ПРИЗНАКИ") {
            startResearchJob("/v1/research/pipeline?symbol=BTCUSDT&interval=15m&window=20", "ИСТОРИЧЕСКИЙ PIPELINE", pipelineButton)
        }
        lab.addView(pipelineButton, LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(7) })
        val cycleCompareButton = button("СРАВНИТЬ СТРАТЕГИИ · WALK-FORWARD 70/30") { runCycleComparison() }
        lab.addView(cycleCompareButton, LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(7) })
        label(lab, "РЕЗУЛЬТАТЫ ИССЛЕДОВАНИЯ")
        researchResult = card("Здесь появятся найденные аналоги, степень сходства и движение цены после каждой формации.")
        lab.addView(researchResult)

        // 03 — ANALYSIS
        val analysis = makePage("АНАЛИЗ")
        title(analysis, "MARKET ANALYSIS", "Сценарии рынка и условия возможного входа")
        label(analysis, "MULTI-TIMEFRAME FORECAST")
        forecastCard = card("Ожидаем данные 15m / 1h / 4h / 1d…")
        analysis.addView(forecastCard)
        label(analysis, "КАК ЧИТАТЬ ОЦЕНКУ")
        analysis.addView(card("LONG / SHORT / SIDEWAYS — экспериментальные оценки на основе правил. Они пока не откалиброваны как вероятности. Вход рассматриваем только при подтверждении, понятной инвалидации и приемлемом соотношении риска к потенциальной прибыли."))

        // 04 — REPLAY
        val replay = makePage("REPLAY")
        title(replay, "BLIND REPLAY", "BTCUSDT 15m · последние 14 дней · прогноз каждые 5 свечей на следующие 5")
        replayButton = button("▶  ЗАПУСТИТЬ ИСТОРИЧЕСКИЙ ТЕСТ") { runBlindReplay() }
        replay.addView(replayButton, LinearLayout.LayoutParams(-1, dp(50)))
        label(replay, "ПОСЛЕДНИЙ ОТЧЁТ")
        replayResult = card("Результаты появятся после теста. Для надёжной оценки сначала загрузите длинную историю BTCUSDT 15m.")
        replay.addView(replayResult)
        label(replay, "ОГРАНИЧЕНИЯ ТЕКУЩЕЙ ВЕРСИИ")
        replay.addView(card("Исследовательский режим: отчёт показывает LONG/SHORT отдельно, качество SIDEWAYS, MAE и сравнение с базовыми подходами. В расчёт net-результата включены модельные round-trip издержки 0,14% на сделку. Это допущение, его можно уточнить под комиссию биржи и тип исполнения. Funding не учитывается. Требуются независимые периоды и проверка разных горизонтов."))

        // 05 — PORTFOLIO
        val portfolio = makePage("ПОРТФЕЛЬ")
        title(portfolio, "PORTFOLIO", "Контроль активов · риск · paper trading")
        label(portfolio, "РЕЖИМ НАБЛЮДЕНИЯ")
        portfolio.addView(card("Реальные ордера не подключены. Следующий этап — виртуальные сделки, журнал прогнозов, размер риска, стоп-сценарии и разбор результатов."))
        label(portfolio, "ПРИНЦИП SHERLOCK")
        portfolio.addView(card("Сначала доказываем качество сигналов на истории и в paper trading. Только после устойчивой проверки можно обсуждать автоматическое исполнение."))

        status = TextView(this).apply {
            text = "●  ИНИЦИАЛИЗАЦИЯ"; textSize = 10f; setTextColor(muted)
            setPadding(dp(12), dp(7), dp(12), dp(7)); setBackgroundColor(bg)
        }
        val nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER
            setBackgroundColor(Color.rgb(12, 21, 34)); setPadding(dp(3), dp(4), dp(3), dp(4))
        }
        val navItems = LinkedHashMap<String, Button>()
        fun navigate(to: String) {
            pages.forEach { (name, view) -> view.visibility = if (name == to) View.VISIBLE else View.GONE }
            navItems.forEach { (name, b) ->
                b.setTextColor(if (name == to) mint else muted)
                b.setBackgroundColor(if (name == to) Color.rgb(25, 48, 62) else Color.rgb(12, 21, 34))
            }
        }
        listOf("РЫНОК", "ШЕРЛОК", "АНАЛИЗ", "REPLAY", "ПОРТФЕЛЬ").forEach { name ->
            nav.addView(Button(this).apply {
                text = name; textSize = 9f; isAllCaps = false; minWidth = 0
                setPadding(0, 0, 0, 0); setTextColor(muted)
                setBackgroundColor(Color.rgb(12, 21, 34))
                setOnClickListener { navigate(name) }; navItems[name] = this
            }, LinearLayout.LayoutParams(0, dp(54), 1f))
        }
        shell.addView(host, LinearLayout.LayoutParams(-1, 0, 1f))
        shell.addView(status)
        shell.addView(nav, LinearLayout.LayoutParams(-1, dp(60)))
        setContentView(shell)
        navigate("РЫНОК")

        historyExecutor.execute {
            try {
                val saved = candleStore.count("BTCUSDT", "15m")
                runOnUiThread { if (!isFinishing) status.text = "●  BINANCE SPOT  ·  ЛОКАЛЬНО: $saved СВЕЧЕЙ  ·  АВТООБНОВЛЕНИЕ 30С" }
            } catch (e: Exception) {
                runOnUiThread { if (!isFinishing) status.text = "●  БАЗА НЕДОСТУПНА: ${e.message ?: "ошибка"}" }
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
                val base = serverBaseUrl()
                val ticker = JSONObject(readUrl("$base/v1/market/ticker/24hr?symbol=BTCUSDT"))
                val p = ticker.getDouble("last_price")
                val pct = ticker.getDouble("price_change_percent")
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
                    status.text = "SERVER OK · Binance Spot · обновлено " + SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(snapshot.fetchedAt)) + " · 4 таймфрейма · авто 30с"
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
                val history = candleStore.readLatest("BTCUSDT", "15m", Int.MAX_VALUE)
                val report = FiveStageStrategy().search(history, 100, 16, 10)
                runOnUiThread {
                    fiveStageButton.isEnabled = true
                    val rows = report.matches.mapIndexed { i, m ->
                        (i + 1).toString() + ". снижение " + String.format(Locale.US, "%.1f", m.declinePct) + "% · восстановление +" + String.format(Locale.US, "%.1f", m.recoveryPct) + "% · обвал " + String.format(Locale.US, "%.1f", m.collapsePct) + "% · после: " + String.format(Locale.US, "%+.2f", m.forwardReturnPct) + "%"
                    }
                    researchResult.text = "FIVE-STAGE STRATEGY · BTCUSDT 15M\nБаза: " + history.size + " свечей · окон проверено: " + report.testedWindows + "\nНайдено формаций: " + report.totalMatches + "\nСредний исход: " + String.format(Locale.US, "%+.2f", report.averageForwardPct) + "% · положительных: " + String.format(Locale.US, "%.1f", report.positiveRatePct) + "% · медиана: " + String.format(Locale.US, "%+.2f", report.medianForwardPct) + "%\nПоследние найденные формации:\n" + rows.joinToString("\n") + "\n" + report.message
                    researchResult.setTextColor(white)
                    status.text = "Five-Stage завершён · база: " + history.size + " свечей"
                }
            } catch (e: Exception) {
                runOnUiThread { fiveStageButton.isEnabled = true; status.text = "Ошибка Five-Stage: " + (e.message ?: "неизвестно") }
            }
        }
    }

    private fun runCycleHunter() {
        cycleButton.isEnabled = false
        status.text = "CYCLE HUNTER: строим дневную историю и ищем пересечения SMA50/100…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", Int.MAX_VALUE)
                val report = CycleHunter().analyze(history, 8)
                runOnUiThread {
                    cycleButton.isEnabled = true
                    fun pct(v: Double?): String = if (v == null) "н/д" else String.format(Locale.US, "%+.1f%%", v)
                    val rows = report.signals.mapIndexed { i, s ->
                        (i + 1).toString() + ". " + SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date(s.time)) +
                            " · BTC " + fmt.format(s.price) + " · +30д " + pct(s.forward30Pct) +
                            " · +90д " + pct(s.forward90Pct) + " · +180д " + pct(s.forward180Pct) +
                            " · +365д " + pct(s.forward365Pct) + " · max + " + pct(s.maxRise365Pct) +
                            " / max " + pct(s.maxDrop365Pct)
                    }
                    researchResult.text = "CYCLE HUNTER · BTC/USD DAILY\n" +
                        "Дневных свечей: " + report.dailyBars + " · пересечений SMA50↑SMA100: " + report.goldenCrosses +
                        "\nСостояние сейчас: " + report.currentState +
                        "\nSMA50: " + (report.currentSma50?.let { fmt.format(it) } ?: "н/д") +
                        " · SMA100: " + (report.currentSma100?.let { fmt.format(it) } ?: "н/д") +
                        "\nСредний исход сигналов: 30д " + pct(report.average30Pct) + " · 90д " + pct(report.average90Pct) +
                        " · 180д " + pct(report.average180Pct) + " · 365д " + pct(report.average365Pct) +
                        "\nПоложительных через 365д: " + pct(report.positive365Pct) + " · медиана: " + pct(report.median365Pct) +
                        "\nПоследние сигналы:\n" + (if (rows.isEmpty()) "Пересечений пока не найдено." else rows.joinToString("\n")) +
                        "\n\n" + report.note
                    researchResult.setTextColor(white)
                    status.text = "Cycle Hunter завершён · дневных свечей: " + report.dailyBars
                }
            } catch (e: Exception) {
                runOnUiThread { cycleButton.isEnabled = true; status.text = "Ошибка Cycle Hunter: " + (e.message ?: "неизвестно") }
            }
        }
    }

    private fun runCycleComparison() {
        status.text = "CYCLE RESEARCH: сравниваем правила на хронологическом тесте 70/30…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", Int.MAX_VALUE)
                val report = CycleResearchEngine().analyze(history, roundTripCostPct = 0.20, horizonDays = 90)
                runOnUiThread {
                    val rows = report.strategies.map { s ->
                        val f = { v: Double? -> if (v == null) "н/д" else String.format(Locale.US, "%+.1f%%", v) }
                        s.name + "\nСделок: " + s.trades + " · win rate: " + f(s.winRatePct) +
                            " · средняя net: " + f(s.averageNetPct) + " · медиана: " + f(s.medianNetPct) +
                            " · совокупно: " + f(s.totalNetPct) + " · max DD: " + f(s.maxDrawdownPct) +
                            "\nTEST 30%: сделок " + s.testTrades + " · win " + f(s.testWinRatePct) +
                            " · средняя net " + f(s.testAverageNetPct)
                    }
                    researchResult.text = "CYCLE RESEARCH · СРАВНЕНИЕ СТРАТЕГИЙ\nДневных баров: " + report.dailyBars +
                        " · split: " + (if (report.splitDate > 0) SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date(report.splitDate)) else "н/д") +
                        "\nBUY & HOLD · train 70%: " + (report.buyHoldTrainPct?.let { String.format(Locale.US, "%+.1f%%", it) } ?: "н/д") +
                        " · test 30%: " + (report.buyHoldTestPct?.let { String.format(Locale.US, "%+.1f%%", it) } ?: "н/д") +
                        "\n\n" + rows.joinToString("\n\n") + "\n\n" + report.caveats
                    researchResult.setTextColor(white)
                    status.text = "Cycle Research завершён · стратегий: " + report.strategies.size
                }
            } catch (e: Exception) {
                runOnUiThread { status.text = "Ошибка Cycle Research: " + (e.message ?: "неизвестно") }
            }
        }
    }

    private fun runPatternSearch() {
        patternButton.isEnabled = false
        status.text = "Pattern Intelligence: анализ исторической базы…"
        analysisExecutor.execute {
            try {
                val history = candleStore.readLatest("BTCUSDT", "15m", Int.MAX_VALUE)
                val report = PatternIntelligence().search(history, 40, 16, 10)
                runOnUiThread {
                    patternButton.isEnabled = true
                    val lines = report.matches.mapIndexed { index, match ->
                        (index + 1).toString() + ". сходство " + String.format(Locale.US, "%.1f", match.similarity) + "% · после формации " + String.format(Locale.US, "%+.2f", match.forwardReturnPct) + "%"
                    }
                    researchResult.text = "PATTERN INTELLIGENCE 2.0 · BTCUSDT 15M\nПолная база: " + history.size + " свечей · кандидатов: " + report.sampleCount + "\nТоп-" + report.matches.size + " по сходству · средний исход: " + String.format(Locale.US, "%+.2f", report.averageForwardPct) + "% · положительных: " + String.format(Locale.US, "%.1f", report.positiveRatePct) + "%\nСредний максимум вверх: " + String.format(Locale.US, "%+.2f", report.averageFavorablePct) + "% · вниз: " + String.format(Locale.US, "%+.2f", report.averageAdversePct) + "%\n" + lines.joinToString("\n") + "\n" + report.note
                    researchResult.setTextColor(white)
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
                val history = candleStore.readLatest("BTCUSDT", "15m", Int.MAX_VALUE)
                val report = BlindReplayEngine().run(
                    history, window = 40, horizon = 5, step = 5,
                    minSimilarity = 35.0, topK = 20, lookbackCandles = 1344
                ) { done, total ->
                    runOnUiThread {
                        if (!isFinishing) status.text = "Blind Replay · проверено $done / $total прогнозных точек · шаг 5 свечей"
                    }
                }
                runOnUiThread {
                    replayButton.isEnabled = true
                    val recent = report.points.takeLast(8).joinToString("\n") {
                        SimpleDateFormat("MM-dd HH:mm", Locale.US).format(Date(it.decisionTime)) +
                            " · прогноз " + it.predicted + " / факт " + it.actual +
                            " · ожидание " + String.format(Locale.US, "%+.2f", it.predictedReturnPct) +
                            "% / факт " + String.format(Locale.US, "%+.2f", it.actualReturnPct) + "%"
                    }
                    replayResult.text = "BLIND REPLAY · WALK-FORWARD 14D / 5×5\n" +
                        "Прогнозов: " + report.tested + " · сделок LONG/SHORT: " + report.traded +
                        "\nНаправление верно: " + String.format(Locale.US, "%.1f", report.accuracyPct) +
                        "% · покрытие: " + String.format(Locale.US, "%.1f", report.coveragePct) + "%" +
                        "\nСредний результат на сигнал: " + String.format(Locale.US, "%+.3f", report.averageActualPct) +
                        "% · накопленный: " + String.format(Locale.US, "%+.2f", report.cumulativeReturnPct) +
                        "% · max drawdown: " + String.format(Locale.US, "%.2f", report.maxDrawdownPct) +
                        "%\nПоследние решения:\n" + recent + "\n" + report.notes
                    replayResult.setTextColor(white)
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

    private fun startResearchJob(path: String, title: String, button: Button) {
        button.isEnabled = false
        status.text = "$title · отправляем задание серверу…"
        analysisExecutor.execute {
            try {
                val base = serverBaseUrl()
                val queued = JSONObject(postUrl(base + path))
                val jobId = queued.getString("job_id")
                var finished: JSONObject? = null
                repeat(400) {
                    Thread.sleep(1500L)
                    val current = JSONObject(readUrl("$base/v1/research/jobs/$jobId"))
                    val state = current.optString("status")
                    runOnUiThread {
                        if (!isFinishing) status.text = "$title · $state · $jobId"
                    }
                    if (state == "completed" || state == "failed") {
                        finished = current
                        return@repeat
                    }
                }
                val finalJob = finished ?: throw IllegalStateException("Задание выполняется дольше 10 минут; проверь статус позже: $jobId")
                if (finalJob.optString("status") != "completed") {
                    throw IllegalStateException(finalJob.optString("error", "сервер завершил задание с ошибкой"))
                }
                val result = finalJob.optJSONObject("result") ?: JSONObject()
                val report = if (title.contains("АУДИТ")) {
                    val datasets = result.optJSONArray("datasets") ?: JSONArray()
                    val lines = (0 until datasets.length()).map { i ->
                        val d = datasets.getJSONObject(i)
                        d.optString("symbol") + " " + d.optString("interval") +
                            " · строк " + d.optLong("rows") +
                            " · пропусков " + d.optLong("missing_candles") +
                            " · повреждённых " + d.optLong("malformed_rows")
                    }
                    "SERVER DATA AUDIT\\nIntegrity: " + result.optJSONArray("integrity_check") +
                        "\\nНаборов: " + datasets.length() + "\\n" + lines.joinToString("\\n")
                } else {
                    "HISTORICAL PIPELINE\\nИнструмент: " + result.optString("symbol") +
                        " · таймфрейм: " + result.optString("interval") +
                        "\\nСвечей прочитано: " + result.optInt("candles_read") +
                        "\\nПризнаков рассчитано: " + result.optInt("features_written") +
                        "\\nРежимов рассчитано: " + result.optInt("regimes_written") +
                        "\\nНепрерывных сегментов: " + result.optInt("segments") +
                        "\\nИсходная БД открыта только для чтения. Результаты записаны в отдельную analytics DB."
                }
                runOnUiThread {
                    researchResult.text = report
                    researchResult.setTextColor(white)
                    status.text = "$title · ГОТОВО"
                }
            } catch (e: Exception) {
                runOnUiThread { status.text = "$title · ОШИБКА: " + (e.message ?: "неизвестная ошибка") }
            } finally {
                runOnUiThread { button.isEnabled = true }
            }
        }
    }

    private fun postUrl(address: String): String {
        val connection = URL(address).openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = 8_000
        connection.readTimeout = 15_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Length", "0")
        return try {
            connection.outputStream.use { }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            stream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun fetchCandles(tf: String): List<Candle> {
        val base = serverBaseUrl()
        val payload = JSONObject(readUrl("$base/v1/market/klines?symbol=BTCUSDT&interval=$tf&limit=120"))
        val arr = payload.getJSONArray("candles")
        return (0 until arr.length()).map { i ->
            val a = arr.getJSONObject(i)
            Candle(a.getDouble("open").toFloat(), a.getDouble("high").toFloat(),
                a.getDouble("low").toFloat(), a.getDouble("close").toFloat(),
                a.getDouble("volume").toFloat())
        }
    }

    private fun serverBaseUrl(): String {
        val prefs = getSharedPreferences("sherlock_settings", MODE_PRIVATE)
        return prefs.getString("server_url", "http://10.0.2.2:8000")!!.trimEnd('/')
    }

    private fun configureServer() {
        val input = EditText(this).apply {
            setSingleLine(true)
            hint = "http://192.168.1.10:8000"
            setText(serverBaseUrl())
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(TextView(this@MainActivity).apply {
                text = "Эмулятор: http://10.0.2.2:8000\\nТелефон: http://IP-АДРЕС-ПК:8000 (одна Wi-Fi сеть)"
                textSize = 12f
            })
            addView(input)
        }
        android.app.AlertDialog.Builder(this)
            .setTitle("Сервер CRYPTO SHERLOCK")
            .setView(box)
            .setNegativeButton("Отмена", null)
            .setNeutralButton("Проверить") { _, _ -> checkServer(input.text.toString().trim()) }
            .setPositiveButton("Сохранить") { _, _ ->
                val value = input.text.toString().trim().trimEnd('/')
                getSharedPreferences("sherlock_settings", MODE_PRIVATE).edit().putString("server_url", value).apply()
                status.text = "Адрес сервера сохранён: $value"
                loadMarket(true)
            }.show()
    }

    private fun checkServer(address: String) {
        historyExecutor.execute {
            try {
                val health = JSONObject(readUrl(address.trimEnd('/') + "/health"))
                runOnUiThread {
                    status.text = if (health.optString("status") == "ok") "СЕРВЕР ДОСТУПЕН · " + health.optString("service")
                        else "СЕРВЕР ОТВЕТИЛ, НО СТАТУС НЕ OK"
                }
            } catch (e: Exception) {
                runOnUiThread { status.text = "СЕРВЕР НЕ ДОСТУПЕН: " + (e.message ?: "ошибка сети") }
            }
        }
    }

    private fun renderForecast(f: ForecastSnapshot) {
        val lines = f.states.joinToString("\n") {
            it.interval + " · " + it.bias + " · RSI " + String.format(Locale.US, "%.1f", it.rsi) +
                " · ATR " + String.format(Locale.US, "%.2f", it.atrPct) + "% · объём x" +
                String.format(Locale.US, "%.2f", it.volumeRatio)
        }
        forecastCard.text = "FORECAST ENGINE · ЭКСПЕРИМЕНТАЛЬНЫЙ\n" +
            "LONG " + f.longPct + "%  |  SHORT " + f.shortPct + "%  |  SIDEWAYS " + f.sidewaysPct + "%\n" +
            f.entryState + "\nЗона наблюдения: " + fmt.format(f.entryLow) + " — " + fmt.format(f.entryHigh) +
            "\nИнвалидация сценария: " + fmt.format(f.invalidation) + "\n" + lines +
            "\nОценки основаны на правилах, НЕ откалиброваны как реальные вероятности. " + f.rationale
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