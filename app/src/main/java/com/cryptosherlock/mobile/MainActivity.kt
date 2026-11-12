package com.cryptosherlock.mobile
import android.app.Activity
import android.os.Bundle
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Color
import android.view.Gravity
import android.view.View
import android.widget.*
import org.json.JSONArray
import java.net.URL
import java.text.DecimalFormat
import kotlin.concurrent.thread

data class Candle(val open: Float,val high: Float,val low: Float,val close: Float,val volume: Float)

class MainActivity : Activity() {
 private val bg=Color.rgb(8,14,25); private val panel=Color.rgb(17,27,43)
 private val mint=Color.rgb(85,214,194); private val white=Color.rgb(232,239,248); private val muted=Color.rgb(139,155,177)
 private lateinit var price:TextView; private lateinit var change:TextView; private lateinit var status:TextView
 private lateinit var chart:CandleChart; private lateinit var candleInfo:TextView
 private var interval="15m"; private val fmt=DecimalFormat("#,##0.00")
 override fun onCreate(savedInstanceState:Bundle?) {
  super.onCreate(savedInstanceState); window.statusBarColor=bg; window.navigationBarColor=bg
  val root=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setPadding(18,18,18,12); setBackgroundColor(bg) }
  root.addView(TextView(this).apply { text="◈  CRYPTO SHERLOCK"; textSize=22f; setTextColor(mint); typeface=android.graphics.Typeface.DEFAULT_BOLD })
  root.addView(TextView(this).apply { text="MARKET INTELLIGENCE  /  BINANCE SPOT"; textSize=10f; setTextColor(muted); setPadding(0,5,0,18) })
  price=TextView(this).apply { text="BTC / USDT"; textSize=31f; setTextColor(white); typeface=android.graphics.Typeface.DEFAULT_BOLD }; root.addView(price)
  change=TextView(this).apply { text="Загрузка котировки…"; textSize=14f; setTextColor(mint); setPadding(0,3,0,18) }; root.addView(change)
  val row=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL; gravity=Gravity.CENTER_VERTICAL }
  listOf("15m","30m","1h","2h","4h").forEach { tf -> row.addView(Button(this).apply { text=tf; textSize=11f; isAllCaps=false; setOnClickListener { interval=tf; loadMarket() } },LinearLayout.LayoutParams(0,48,1f)) }
  root.addView(row)
  chart=CandleChart(this).apply { setBackgroundColor(panel) }; root.addView(chart,LinearLayout.LayoutParams(-1,0,1f).apply { topMargin=10; bottomMargin=10 })
  candleInfo=TextView(this).apply { text="График свечей и объёмов"; textSize=13f; setTextColor(white); setPadding(4,8,4,8) }; root.addView(candleInfo)
  root.addView(Button(this).apply { text="ОБНОВИТЬ РЫНОК"; isAllCaps=false; setOnClickListener { loadMarket() } },LinearLayout.LayoutParams(-1,52))
  status=TextView(this).apply { text="Источник: Binance Spot API"; textSize=11f; setTextColor(muted); setPadding(2,10,2,0) }; root.addView(status)
  setContentView(root); loadMarket()
 }
 private fun loadMarket() {
  status.text="Подключение к Binance…"
  thread {
   try {
    val ticker=org.json.JSONObject(readUrl("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"))
    val p=ticker.getString("lastPrice").toDouble(); val pct=ticker.getString("priceChangePercent").toDouble()
    val arr=JSONArray(readUrl("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval="+interval+"&limit=100"))
    val cs=ArrayList<Candle>()
    for(i in 0 until arr.length()) { val a=arr.getJSONArray(i); cs.add(Candle(a.getString(1).toFloat(),a.getString(2).toFloat(),a.getString(3).toFloat(),a.getString(4).toFloat(),a.getString(5).toFloat())) }
    runOnUiThread {
     price.text="$"+fmt.format(p); change.text=(if(pct>=0) "▲ +" else "▼ ")+String.format("%.2f%%",pct)+"  ·  BTCUSDT"
     change.setTextColor(if(pct>=0) mint else Color.rgb(255,105,115)); chart.setCandles(cs)
     candleInfo.text="BTCUSDT  •  "+interval+"  •  "+cs.size+" свечей  •  Объём снизу"
     status.text="Обновлено: Binance Spot  |  "+java.text.SimpleDateFormat("HH:mm:ss",java.util.Locale.getDefault()).format(java.util.Date())
    }
   } catch(e:Exception) { runOnUiThread { status.text="Ошибка загрузки: "+(e.message ?: "нет соединения") } }
  }
 }
 private fun readUrl(s:String):String { val conn=URL(s).openConnection(); conn.connectTimeout=12000; conn.readTimeout=12000; return conn.getInputStream().bufferedReader().use{it.readText()} }
 class CandleChart(context:android.content.Context):View(context) {
  private val up=Paint(Paint.ANTI_ALIAS_FLAG).apply { color=Color.rgb(65,205,158); strokeWidth=2f }
  private val down=Paint(Paint.ANTI_ALIAS_FLAG).apply { color=Color.rgb(245,91,106); strokeWidth=2f }
  private val grid=Paint(Paint.ANTI_ALIAS_FLAG).apply { color=Color.rgb(42,57,77); strokeWidth=1f }
  private val vol=Paint(Paint.ANTI_ALIAS_FLAG); private val label=Paint(Paint.ANTI_ALIAS_FLAG).apply { color=Color.rgb(139,155,177); textSize=22f }
  private var data:List<Candle> = emptyList()
  fun setCandles(c:List<Candle>) { data=c; invalidate() }
  override fun onDraw(c:Canvas) {
   super.onDraw(c); val w=width.toFloat(); val h=height.toFloat()
   for(i in 1..4) c.drawLine(0f,h*i/5,w,h*i/5,grid)
   if(data.isEmpty()) { c.drawText("Ждём рыночные данные…",24f,h/2,label); return }
   val top=24f; val bottom=h*0.77f; val min=data.minOf{it.low}; val max=data.maxOf{it.high}; val span=(max-min).coerceAtLeast(0.01f)
   val step=w/data.size; val body=(step*0.58f).coerceAtLeast(2f); val maxVol=data.maxOf{it.volume}.coerceAtLeast(1f)
   data.forEachIndexed { i,d ->
    val x=i*step+step/2; val yh=bottom-(d.high-min)/span*(bottom-top); val yl=bottom-(d.low-min)/span*(bottom-top)
    val yo=bottom-(d.open-min)/span*(bottom-top); val yc=bottom-(d.close-min)/span*(bottom-top); val p=if(d.close>=d.open) up else down
    c.drawLine(x,yh,x,yl,p); c.drawRect(x-body/2,minOf(yo,yc),x+body/2,maxOf(yc,yo+2),p)
    vol.color=p.color; val vh=d.volume/maxVol*(h*0.16f); c.drawRect(x-body/2,h-vh,x+body/2,h-3f,vol)
   }
  }
 }
}