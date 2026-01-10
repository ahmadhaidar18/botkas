from dotenv import load_dotenv
import os
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= LOAD ENV =================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003301486148")

if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN tidak terbaca dari environment")

if ADMIN_ID == 0:
    raise RuntimeError("❌ ADMIN_ID tidak terbaca dari environment")

ADMIN_IDS = [ADMIN_ID]

if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN tidak terbaca dari environment")

if not ADMIN_ID:
    raise RuntimeError("❌ ADMIN_ID tidak terbaca dari environment")

ADMIN_IDS = [int(ADMIN_ID)]

print("DEBUG TOKEN:", TOKEN)

# ================= DATABASE =================
conn = sqlite3.connect("kas.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS transaksi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal TEXT,
    jenis TEXT,
    jumlah INTEGER,
    keterangan TEXT
)
""")
conn.commit()

# ================= UTIL =================
def rupiah(n: int) -> str:
    return f"{n:,}".replace(",", ".")

def get_saldo() -> int:
    cur.execute("""
        SELECT SUM(
            CASE WHEN jenis='MASUK' THEN jumlah ELSE -jumlah END
        )
        FROM transaksi
    """)
    r = cur.fetchone()[0]
    return r if r else 0

def is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_IDS

async def kirim_ke_channel(context, text: str):
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=text,
        parse_mode="Markdown"
    )

# ================= KEYBOARD =================
def menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Pemasukan", callback_data="MASUK"),
            InlineKeyboardButton("🔴 Pengeluaran", callback_data="KELUAR")
        ],
        [
            InlineKeyboardButton("💰 Saldo", callback_data="SALDO"),
            InlineKeyboardButton("📒 Riwayat", callback_data="RIWAYAT")
        ]
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data="MENU")]
    ])

# ================= FORMAT RIWAYAT =================
def format_riwayat_tabel():
    cur.execute("SELECT * FROM transaksi ORDER BY id")
    rows = cur.fetchall()

    if not rows:
        return "📒 *BUKU KAS UMUM*\n\n_Belum ada transaksi_"

    saldo = 0
    text = "📒 *BUKU KAS UMUM*\n\n```"
    text += "No Tgl        Ket            Debet            Kredit           Saldo\n"
    text += "--------------------------------------------------------------------\n"

    for i, r in enumerate(rows, 1):
        _, tgl, jenis, jml, ket = r

        if jenis == "MASUK":
            saldo += jml
            debet = f"🟢{rupiah(jml)}"
            kredit = "-"
        else:
            saldo -= jml
            debet = "-"
            kredit = f"🔴{rupiah(jml)}"

        text += (
            f"{i:<3}"
            f"{tgl:<11}"
            f"{ket[:14]:<14}"
            f"{debet:<16}"
            f"{kredit:<16}"
            f"{rupiah(saldo)}\n"
        )

    text += "```"
    return text

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Akses ditolak")
        return

    await update.message.reply_text(
        "🤖 *BOT KAS BENDAHARA*\n\nLogin berhasil ✅",
        parse_mode="Markdown",
        reply_markup=menu_keyboard()
    )

# ================= CALLBACK =================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not is_admin(update):
        return

    data = q.data

    if data == "MENU":
        await q.message.reply_text(
            "📋 *MENU UTAMA*",
            parse_mode="Markdown",
            reply_markup=menu_keyboard()
        )

    elif data in ("MASUK", "KELUAR"):
        context.user_data.clear()
        context.user_data["jenis"] = data
        await q.message.reply_text(
            "Ketik:\n`jumlah keterangan`\n\nContoh:\n`50000 iuran anggota`",
            parse_mode="Markdown"
        )

    elif data == "SALDO":
        saldo = get_saldo()
        await kirim_ke_channel(
            context,
            f"💰 *SALDO KAS*\n\nRp {rupiah(saldo)}"
        )
        await q.message.reply_text(
            f"💰 *SALDO SAAT INI*\nRp {rupiah(saldo)}\n\n📢 Dikirim ke channel",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )

    elif data == "RIWAYAT":
        text = format_riwayat_tabel()

        await kirim_ke_channel(context, text)
        await q.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )

# ================= INPUT =================
async def input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if "jenis" not in context.user_data:
        return

    try:
        jml, ket = update.message.text.split(" ", 1)
        jml = int(jml)
    except:
        await update.message.reply_text("❌ Format salah")
        return

    jenis = context.user_data.pop("jenis")
    tgl = datetime.now().strftime("%d-%m-%Y")

    cur.execute(
        "INSERT INTO transaksi (tanggal, jenis, jumlah, keterangan) VALUES (?,?,?,?)",
        (tgl, jenis, jml, ket)
    )
    conn.commit()

    await update.message.reply_text(
        "✅ Transaksi tersimpan",
        reply_markup=menu_keyboard()
    )

# ================= MAIN =================
if __name__ == "__main__":
    print("🤖 Bot kas bendahara berjalan...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_text))

    app.run_polling()
