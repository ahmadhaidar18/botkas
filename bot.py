import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import sqlite3
from datetime import datetime

# ================= CONFIG =================
TOKEN = os.getenv ("8598378490:AAEPnPYSqMFI6lJqUEGEQo93aKLduk2ARvo")
ADMIN_IDS = [6484363998]
CHANNEL_ID = "-1003301486148"

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
def rupiah(n):
    return f"{n:,}".replace(",", ".")

def get_saldo():
    cur.execute("""
        SELECT SUM(CASE WHEN jenis='MASUK' THEN jumlah ELSE -jumlah END)
        FROM transaksi
    """)
    r = cur.fetchone()[0]
    return r if r else 0

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

async def kirim_ke_channel(context, text):
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="Markdown"
        )
        print("✅ Pesan terkirim ke channel")
    except Exception as e:
        print("❌ Gagal kirim ke channel:", e)

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

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    await update.message.reply_text(
        "🤖 *BOT KAS BENDAHARA*\n\nLogin berhasil ✅",
        parse_mode="Markdown",
        reply_markup=menu_keyboard()
    )

# ================= RIWAYAT CHANNEL (TABEL) =================
def format_riwayat_channel_tabel():
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

        # ke channel
        await kirim_ke_channel(
            context,
            f"💰 *SALDO KAS*\n\nRp {rupiah(saldo)}"
        )

        # ke admin
        await q.message.reply_text(
            f"💰 *SALDO SAAT INI*\nRp {rupiah(saldo)}\n\n📢 Dikirim ke channel",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )

    elif data == "RIWAYAT":
        # ke channel (tabel)
        await kirim_ke_channel(
            context,
            format_riwayat_channel_tabel()
        )

        # ke admin (lengkap + tombol)
        await tampil_riwayat_admin(q.message)

    elif data.startswith("edit_"):
        context.user_data["edit_id"] = data.split("_")[1]
        await q.message.reply_text(
            "✏️ *Yakin ingin edit transaksi ini?*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ya", callback_data="EDIT_YA"),
                    InlineKeyboardButton("❌ Tidak", callback_data="MENU")
                ]
            ])
        )

    elif data == "EDIT_YA":
        await q.message.reply_text(
            "Ketik ulang:\n`jumlah keterangan`",
            parse_mode="Markdown"
        )

    elif data.startswith("hapus_"):
        context.user_data["hapus_id"] = data.split("_")[1]
        await q.message.reply_text(
            "🗑️ *Yakin ingin menghapus transaksi ini?*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ya", callback_data="HAPUS_YA"),
                    InlineKeyboardButton("❌ Tidak", callback_data="MENU")
                ]
            ])
        )

    elif data == "HAPUS_YA":
        id_trx = context.user_data.pop("hapus_id", None)
        if id_trx:
            cur.execute("DELETE FROM transaksi WHERE id=?", (id_trx,))
            conn.commit()
            await q.message.reply_text("🗑️ Transaksi dihapus")
            await tampil_riwayat_admin(q.message)

# ================= INPUT =================
async def input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    text = update.message.text

    if "edit_id" in context.user_data:
        try:
            jml, ket = text.split(" ", 1)
            jml = int(jml)
        except:
            await update.message.reply_text("❌ Format salah")
            return

        id_trx = context.user_data.pop("edit_id")
        cur.execute(
            "UPDATE transaksi SET jumlah=?, keterangan=? WHERE id=?",
            (jml, ket, id_trx)
        )
        conn.commit()

        await update.message.reply_text("✏️ Transaksi berhasil diedit")
        await tampil_riwayat_admin(update.message)
        return

    if "jenis" not in context.user_data:
        return

    try:
        jml, ket = text.split(" ", 1)
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

    await update.message.reply_text("✅ Transaksi tersimpan", reply_markup=menu_keyboard())

# ================= RIWAYAT ADMIN =================
async def tampil_riwayat_admin(msg):
    cur.execute("SELECT * FROM transaksi ORDER BY id")
    rows = cur.fetchall()

    saldo = 0
    text = "📒 *BUKU KAS UMUM*\n\n```"
    text += "No Tgl        Ket            Debet            Kredit           Saldo\n"
    text += "--------------------------------------------------------------------\n"

    buttons = []

    for i, r in enumerate(rows, 1):
        id, tgl, jenis, jml, ket = r

        if jenis == "MASUK":
            saldo += jml
            d = f"🟢{rupiah(jml)}"
            k = "-"
        else:
            saldo -= jml
            d = "-"
            k = f"🔴{rupiah(jml)}"

        text += (
            f"{i:<3}"
            f"{tgl:<11}"
            f"{ket[:14]:<14}"
            f"{d:<16}"
            f"{k:<16}"
            f"{rupiah(saldo)}\n"
        )

        buttons.append([
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{id}"),
            InlineKeyboardButton("🗑️ Hapus", callback_data=f"hapus_{id}")
        ])

    text += "```"
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="MENU")])

    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ================= MAIN =================
if __name__ == "__main__":
    print("🤖 Bot kas bendahara berjalan...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_text))
    app.run_polling()
