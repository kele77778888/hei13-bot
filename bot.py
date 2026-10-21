import asyncio
import os
import json
import logging
import random
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import aiosqlite

# ==================== 配置区域 ====================
API_TOKEN = "8697262422:AAGSyQ_12VfYzBWm0PWd_iiz67NONLUxJLQ"
ADMIN_ID = 8408123760
CHANNEL_USERNAME = "@HEI7786"
EXHIBITION_CHANNEL = "@ZL66883"
DAILY_LIMIT = 5
DB_PATH = "bot_data.db"
PORT = 10000

# 默认初始文案
DEFAULT_TEXT_DATA = {
    "welcome1": "欢迎使用黑13免费供需自助，在这里你有更多的机会成交产品\n特殊反馈联系黑13处理：@HEI_13Y\n开启交易🤝新合作模式",
    "welcome2": "黑13供需渠道\nhttps://t.me/HEI7786\n黑13展览频道：\nhttps://t.me/ZL66883\n点下方按钮开始填写供需",
    "welcome3": "欢迎来到黑13供需平台，诚信交易，文明沟通，祝大家成交多多🤝",
    "template_img": """----------------------
📍（位置）｜（品类）
✅ 需求：
✅ 数量：
✅ 价格：
✅ 备注：
✅ 联系：
----------------------""",
    "template_text": """----------------------
📍（位置）｜（品类）
✅ 需求：
✅ 数量：
✅ 价格：
✅ 备注：
✅ 联系：
----------------------""",
    "header": "📢 黑13供需发布",
    "footer": "💬理性沟通，谨防诈骗"
}

logging.basicConfig(level=logging.INFO)
router = Router()

# ==================== 数据库 ====================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_posts (
                post_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                preview_text TEXT NOT NULL,
                media_list TEXT,
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                daily_count INTEGER DEFAULT 0,
                last_date TEXT DEFAULT '',
                is_blacklisted INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_text (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS service_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_sort INTEGER NOT NULL,
                col_sort INTEGER NOT NULL,
                text TEXT NOT NULL,
                url TEXT NOT NULL
            )
        """)
        for k, v in DEFAULT_TEXT_DATA.items():
            await db.execute("INSERT OR IGNORE INTO bot_text(key,value) VALUES (?,?)", (k, v))
        await db.commit()

async def get_text(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        res = await db.execute("SELECT value FROM bot_text WHERE key=?", (key,))
        row = await res.fetchone()
        return row["value"] if row else DEFAULT_TEXT_DATA.get(key, "")

async def set_text(key: str, val: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bot_text SET value=? WHERE key=?", (val, key))
        await db.commit()

async def save_service_buttons(button_rows: list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM service_buttons")
        for row_idx, row_btns in enumerate(button_rows):
            for col_idx, (txt, url) in enumerate(row_btns):
                await db.execute("INSERT INTO service_buttons(row_sort, col_sort, text, url) VALUES (?,?,?,?)",
                                 (row_idx, col_idx, txt, url))
        await db.commit()

async def load_service_buttons() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        res = await db.execute("SELECT row_sort, col_sort, text, url FROM service_buttons ORDER BY row_sort, col_sort")
        rows = await res.fetchall()
        out = []
        last_r = -1
        current = []
        for item in rows:
            if item["row_sort"] != last_r:
                if current:
                    out.append(current)
                current = []
                last_r = item["row_sort"]
            current.append((item["text"], item["url"]))
        if current:
            out.append(current)
        return out

async def build_service_keyboard() -> InlineKeyboardMarkup | None:
    btn_rows = await load_service_buttons()
    if not btn_rows:
        return None
    markup_lines = []
    for line in btn_rows:
        markup_lines.append([InlineKeyboardButton(text=t, url=u) for t, u in line])
    return InlineKeyboardMarkup(inline_keyboard=markup_lines)

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await r.fetchone()

async def upsert_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id, username, daily_count, last_date, is_blacklisted) VALUES (?, ?, 0, '', 0)",
                         (user_id, username))
        await db.commit()

async def add_daily_count(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_user(user_id)
        if not user:
            await upsert_user(user_id, "")
            user = await get_user(user_id)
        if user["last_date"] != today:
            await db.execute("UPDATE users SET daily_count=1, last_date=? WHERE user_id=?", (today, user_id))
        else:
            await db.execute("UPDATE users SET daily_count=daily_count+1 WHERE user_id=?", (user_id,))
        await db.commit()

async def add_pending(post_id: str, user_id: int, preview: str, media_list: list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO pending_posts(post_id, user_id, preview_text, media_list, created_at, status) VALUES (?,?,?,?,?, 'pending')",
                         (post_id, user_id, preview, json.dumps(media_list), asyncio.get_event_loop().time()))
        await db.commit()

async def get_pending(post_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await db.execute("SELECT * FROM pending_posts WHERE post_id=? AND status='pending'", (post_id,))
        return await r.fetchone()

async def change_pending_status(post_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE pending_posts SET status=? WHERE post_id=?", (status, post_id))
        await db.commit()

# ==================== FSM ====================
class PostFillState(StatesGroup):
    mode = State()
    media = State()
    pos_main = State()
    need = State()
    quantity = State()
    price = State()
    remark = State()
    link = State()

class SettingState(StatesGroup):
    edit_target = State()

class ButtonImportState(StatesGroup):
    waiting_config = State()

class RejectState(StatesGroup):
    post_id = State()
    reason = State()

# ==================== 管理员指令 ====================
@router.message(Command("settings"))
async def admin_settings(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📝 修改欢迎语1", callback_data="edit:welcome1"),
         InlineKeyboardButton("📝 修改欢迎语2", callback_data="edit:welcome2")],
        [InlineKeyboardButton("📝 修改欢迎语3", callback_data="edit:welcome3")],
        [InlineKeyboardButton("🎬 修改图文模板", callback_data="edit:template_img"),
         InlineKeyboardButton("📄 修改文字模板", callback_data="edit:template_text")],
        [InlineKeyboardButton("🔝 修改顶部标题", callback_data="edit:header"),
         InlineKeyboardButton("🔻 修改底部备注", callback_data="edit:footer")],
        [InlineKeyboardButton("📋 查看全部文案", callback_data="show_all_text")]
    ])
    await message.answer("⚙️管理员后台面板\n点击修改对应文案", reply_markup=kb)

@router.callback_query(F.data.startswith("edit:"))
async def cb_edit_text(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    await state.update_data(edit_target=key)
    await state.set_state(SettingState.edit_target)
    await callback.message.answer(f"✏️发送新内容修改【{key}】，发送/cancel取消")
    await callback.answer()

@router.message(SettingState.edit_target)
async def receive_edit_text(message: Message, state: FSMContext):
    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌已取消修改")
        return
    data = await state.get_data()
    target_key = data["edit_target"]
    await set_text(target_key, message.html_text)
    await state.clear()
    await message.answer(f"✅【{target_key}】修改成功！")

@router.callback_query(F.data == "show_all_text")
async def cb_show_all(callback: CallbackQuery):
    w1 = await get_text("welcome1")
    w2 = await get_text("welcome2")
    w3 = await get_text("welcome3")
    t_img = await get_text("template_img")
    t_txt = await get_text("template_text")
    h = await get_text("header")
    f = await get_text("footer")
    txt = (
        "📋当前全部文案：\n\n"
        f"欢迎语1：\n{w1}\n\n"
        f"欢迎语2：\n{w2}\n\n"
        f"欢迎语3：\n{w3}\n\n"
        f"图文模板：\n{t_img}\n\n"
        f"文字模板：\n{t_txt}\n\n"
        f"顶部标题：{h}\n底部备注：{f}"
    )
    await callback.message.answer(txt)
    await callback.answer()

@router.message(Command("import_buttons"))
async def cmd_import_btn(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(ButtonImportState.waiting_config)
    guide = (
        "✏️导入跳转按钮\n格式示例：\n"
        "文字|链接 | 文字|链接\n"
        "文字|链接\n\n"
        "发送/cancel取消"
    )
    await message.answer(guide)

@router.message(ButtonImportState.waiting_config)
async def receive_btn_config(message: Message, state: FSMContext):
    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌取消导入")
        return
    lines = message.text.strip().splitlines()
    final_rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(" | ")
        row_btn = []
        for p in parts:
            if "|" not in p:
                continue
            bt, bl = p.split("|", 1)
            bt = bt.strip()
            bl = bl.strip()
            if bt and bl:
                row_btn.append((bt, bl))
        if row_btn:
            final_rows.append(row_btn)
    await save_service_buttons(final_rows)
    await state.clear()
    await message.answer(f"✅导入完成，一共{len(final_rows)}行按钮")

@router.message(Command("show_buttons"))
async def cmd_show_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    btn_rows = await load_service_buttons()
    if not btn_rows:
        await message.answer("暂无按钮")
        return
    out = "📋按钮列表：\n"
    for idx, r in enumerate(btn_rows, 1):
        out += f"第{idx}行：{r}\n"
    await message.answer(out)

@router.message(Command("clear_buttons"))
async def cmd_clear_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await save_service_buttons([])
    await message.answer("🗑️按钮全部清空")

# ==================== 用户流程 ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await upsert_user(message.from_user.id, message.from_user.username or "")
    w_list = [await get_text("welcome1"), await get_text("welcome2"), await get_text("welcome3")]
    welcome_txt = random.choice(w_list)
    t_img = await get_text("template_img")
    t_txt = await get_text("template_text")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📝文字供需", callback_data="fill:text")],
        [InlineKeyboardButton("🎬图片/视频供需", callback_data="fill:media")]
    ])
    full_text = f"{welcome_txt}\n\n【图文模板参考】\n{t_img}\n\n【纯文字模板参考】\n{t_txt}"
    await message.answer(full_text, reply_markup=kb)

@router.callback_query(F.data.startswith("fill:"))
async def cb_fill_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if user and user["is_blacklisted"] == 1:
        await callback.answer("❌你已经被拉黑，无法发布", show_alert=True)
        return
    today = datetime.now().strftime("%Y-%m-%d")
    if user and user["last_date"] == today and user["daily_count"] >= DAILY_LIMIT:
        await callback.answer(f"❌今日发布上限{DAILY_LIMIT}条，明天再来", show_alert=True)
        return
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode, media_list=[])
    if mode == "media":
        await state.set_state(PostFillState.media)
        await callback.message.answer("🎬发送图片/视频，发完点下一步")
    else:
        await state.set_state(PostFillState.pos_main)
        await callback.message.answer("📍第一步：填写【位置｜品类】\n示例：平阳｜水果")
    await callback.answer()

@router.message(PostFillState.media, F.photo | F.video)
async def receive_media(message: Message, state: FSMContext):
    d = await state.get_data()
    ml = d.get("media_list", [])
    if message.photo:
        ml.append(("photo", message.photo[-1].file_id))
    else:
        ml.append(("video", message.video.file_id))
    await state.update_data(media_list=ml)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("➡️下一步填写文字", callback_data="media_next")]
    ])
    await message.answer(f"✅收到素材{len(ml)}个，可以继续发或者点下一步", reply_markup=kb)

@router.callback_query(F.data == "media_next")
async def cb_media_next(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PostFillState.pos_main)
    await callback.message.answer("📍填写【位置｜品类】\n示例：平阳｜水果")
    await callback.answer()

@router.message(PostFillState.pos_main)
async def receive_pos_main(message: Message, state: FSMContext):
    content = message.text.strip()
    if not content:
        await message.answer("❌不能为空，请重新输入")
        return
    await state.update_data(pos_main=content)
    await state.set_state(PostFillState.need)
    await message.answer("✅第二步：填写需求（出售/求购）")

@router.message(PostFillState.need)
async def receive_need(message: Message, state: FSMContext):
    content = message.text.strip()
    if not content:
        await message.answer("❌不能为空")
        return
    await state.update_data(need=content)
    await state.set_state(PostFillState.quantity)
    await message.answer("✅第三步：填写数量")

@router.message(PostFillState.quantity)
async def receive_quantity(message: Message, state: FSMContext):
    content = message.text.strip()
    if not content:
        await message.answer("❌不能为空")
        return
    await state.update_data(quantity=content)
    await state.set_state(PostFillState.price)
    await message.answer("✅第四步：填写价格")

@router.message(PostFillState.price)
async def receive_price(message: Message, state: FSMContext):
    content = message.text.strip()
    if not content:
        await message.answer("❌不能为空")
        return
    await state.update_data(price=content)
    await state.set_state(PostFillState.remark)
    await message.answer("✅第五步：填写备注")

@router.message(PostFillState.remark)
async def receive_remark(message: Message, state: FSMContext):
    content = message.text.strip()
    await state.update_data(remark=content)
    await state.set_state(PostFillState.link)
    await message.answer("✅第六步：填写联系方式，没有就发 /skip")

@router.message(PostFillState.link)
async def receive_link(message: Message, state: FSMContext):
    data = await state.get_data()
    link = message.text.strip()
    if link == "/skip":
        link = "无"
    data["link"] = link
    if data["mode"] == "media":
        tpl = await get_text("template_img")
    else:
        tpl = await get_text("template_text")
    preview_text = tpl.replace("（位置）｜（品类）", data["pos_main"]) \
        .replace("需求：", data["need"]) \
        .replace("数量：", data["quantity"]) \
        .replace("价格：", data["price"]) \
        .replace("备注：", data["remark"]) \
        .replace("联系：", data["link"])
    await state.update_data(preview_text=preview_text)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🚀提交审核", callback_data="submit_ok")],
        [InlineKeyboardButton("❌取消", callback_data="fill_cancel")]
    ])
    service_kb = await build_service_keyboard()
    all_rows = confirm_kb.inline_keyboard
    if service_kb:
        all_rows.extend(service_kb.inline_keyboard)
    final_kb = InlineKeyboardMarkup(inline_keyboard=all_rows)
    await message.answer(f"👀预览：\n\n{preview_text}", reply_markup=final_kb)

@router.callback_query(F.data == "fill_cancel")
async def cb_fill_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌已取消本次发布")
    await callback.answer()

@router.callback_query(F.data == "submit_ok")
async def cb_submit_ok(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    post_id = f"{callback.from_user.id}_{int(asyncio.get_event_loop().time())}"
    await add_pending(post_id, callback.from_user.id, data["preview_text"], data["media_list"])
    await add_daily_count(callback.from_user.id)
    await state.clear()
    await callback.message.answer("✅提交成功，等待管理员审核")
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("✅通过", callback_data=f"approve:{post_id}"),
         InlineKeyboardButton("❌拒绝", callback_data=f"reject:{post_id}")]
    ])
    await bot.send_message(
        ADMIN_ID,
        f"📩新供需待审核\n用户ID：{callback.from_user.id}\n\n{data['preview_text']}",
        reply_markup=admin_kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    pid = callback.data.split(":")[1]
    rec = await get_pending(pid)
    if not rec:
        await callback.answer("找不到这条记录", show_alert=True)
        return
    await change_pending_status(pid, "approved")
    preview = rec["preview_text"]
    media_list = json.loads(rec["media_list"])
    header = await get_text("header")
    footer = await get_text("footer")
    publish_text = f"{header}\n\n{preview}\n\n{footer}"
    kb_rows = []
    kb_rows.append([InlineKeyboardButton("💬联系发布者", url=f"tg://user?id={rec['user_id']}")])
    service_kb = await build_service_keyboard()
    if service_kb:
        kb_rows.extend(service_kb.inline_keyboard)
    final_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    if media_list:
        media_group = []
        for typ, fid in media_list:
            if typ == "photo":
                media_group.append({"type": "photo", "media": fid})
            else:
                media_group.append({"type": "video", "media": fid})
        await bot.send_media_group(CHANNEL_USERNAME, media_group)
    await bot.send_message(CHANNEL_USERNAME, publish_text, reply_markup=final_kb)
    await bot.send_message(rec["user_id"], "🎉恭喜！你的供需已经审核通过，发布到频道！")
    await callback.message.answer("✅已发布")
    await callback.answer()

@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery, state: FSMContext):
    pid = callback.data.split(":")[1]
    await state.update_data(post_id=pid)
    await state.set_state(RejectState.reason)
    await callback.message.answer("✏️输入拒绝理由")
    await callback.answer()

@router.message(RejectState.reason)
async def receive_reject_reason(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pid = data["post_id"]
    rec = await get_pending(pid)
    if not rec:
        await message.answer("记录不存在")
        await state.clear()
        return
    await change_pending_status(pid, "rejected")
    await bot.send_message(rec["user_id"], f"❌你的供需审核被驳回\n原因：{message.text}")
    await message.answer("✅驳回通知已发送")
    await state.clear()

# ===================== Web保活服务 + 机器人 =====================
async def web_handler(request):
    return web.Response(text="Bot running!")

async def bot_main():
    await init_db()
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

async def main():
    # 启动保活网页
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
    await site.start()

    # 后台启动机器人，不阻塞网页
    asyncio.create_task(bot_main())

    # 一直保持网页运行
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
