"""
黑13自助供需 - Telegram Bot
部署方式: Render Background Worker
启动命令: python main.py
环境变量:
  BOT_TOKEN  = 你的BotFather令牌
  ADMIN_ID   = 你的Telegram数字ID
  BASE_API   = 你部署的后端地址(如 https://xxx.onrender.com)
"""
import telebot
from telebot import types
import requests
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8697262422:AAGSyQ_12VfYzBWm0PWd_iiz67NONLUxJLQ")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8408123760"))
BASE_API = os.environ.get("BASE_API", "https://hei13-bot.onrender.com").rstrip("/")

SUBMIT_URL   = BASE_API + "/api/goods/submit"
GET_INFO_URL = BASE_API + "/api/goods/get"
CANCEL_URL   = BASE_API + "/api/goods/cancel"
AUDIT_URL    = BASE_API + "/api/goods/audit"
LIST_WAIT_URL = BASE_API + "/api/goods/waitlist"

bot = telebot.TeleBot(BOT_TOKEN)

user_state = {}
preview_cache = {}

# ========== 下拉指令菜单 ==========
public_commands = [
    telebot.types.BotCommand("start", "✦ 打开主面板"),
    telebot.types.BotCommand("order", "✦ 提交供需上架"),
]
admin_commands = [
    telebot.types.BotCommand("start", "✦ 打开主面板"),
    telebot.types.BotCommand("help", "✦ 使用帮助"),
    telebot.types.BotCommand("order", "✦ 提交供需上架"),
    telebot.types.BotCommand("status", "✦ 查询上架单据"),
    telebot.types.BotCommand("cancel", "✦ 撤销上架单据"),
    telebot.types.BotCommand("list", "✦ 待审核清单"),
]

# ========== 管理员底部常驻按钮 ==========
admin_reply_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
admin_reply_kb.add(
    types.KeyboardButton("📋 主面板"),
    types.KeyboardButton("📋 待审核清单"),
    types.KeyboardButton("📝 提交上架"),
    types.KeyboardButton("🔍 查询单据"),
    types.KeyboardButton("🚫 撤销上架"),
    types.KeyboardButton("❓ 帮助"),
)


@bot.message_handler(commands=['start'])
def cmd_start(message):
    is_admin = (message.from_user.id == ADMIN_ID)
    if is_admin:
        bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(message.chat.id))
    else:
        bot.set_my_commands(public_commands, scope=types.BotCommandScopeChat(message.chat.id))

    inline_kb = types.InlineKeyboardMarkup(row_width=2)
    inline_kb.add(
        types.InlineKeyboardButton("📝 提交供需上架", callback_data="cb_order"),
        types.InlineKeyboardButton("🔍 查询上架单", callback_data="cb_status"),
        types.InlineKeyboardButton("🚫 撤销上架单", callback_data="cb_cancel"),
        types.InlineKeyboardButton("❓ 使用帮助", callback_data="cb_help"),
    )

    text = """✦ 黑13自助供需｜自助上架通道 ✦
▫️自主提交供需上架信息
▫️提交预览确认后进入后台审核
▫️凭编号查询单据状态
▫️仅待审核单据支持撤销"""

    if is_admin:
        bot.send_message(message.chat.id, text, reply_markup=inline_kb)
        bot.send_message(message.chat.id, "✦ 管理员面板已加载 ✦", reply_markup=admin_reply_kb)
    else:
        bot.send_message(message.chat.id, text, reply_markup=inline_kb)


# ========== 管理员底部按钮 ==========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 主面板")
def kb_main_panel(message):
    bot.send_message(message.chat.id, "✅ 已抵达主面板\n提交上架、查看待审单据、审核管理")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 待审核清单")
def kb_list(message):
    try:
        res = requests.get(LIST_WAIT_URL, timeout=15).json()
        if res.get("code") != 200:
            bot.send_message(message.chat.id, "后台获取清单失败")
            return
        data_list = res.get("data", [])
        if not data_list:
            bot.send_message(message.chat.id, "✦ 当前暂无待审核上架单")
            return
        txt = "✦ 待审核上架清单 ✦\n"
        for item in data_list:
            txt += f"\n🆔编号：{item['id']} | 提交人：@{item['username']}\n📄 {item['content'][:30]}"
        bot.send_message(message.chat.id, txt)
    except Exception:
        bot.send_message(message.chat.id, "请求后台接口异常，请检查后端是否部署")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📝 提交上架")
def kb_order(message):
    user_state[message.from_user.id] = "ordering"
    bot.send_message(message.chat.id, "📝【提交供需上架】\n请发送供需信息：\n需求/供货类型｜数量｜备注")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔍 查询单据")
def kb_status(message):
    bot.send_message(message.chat.id, "🔍【查询上架单】\n请发送供需上架编号")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🚫 撤销上架")
def kb_cancel(message):
    bot.send_message(message.chat.id, "🚫【撤销上架单】\n请发送供需上架编号（仅待审核可撤）")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "❓ 帮助")
def kb_help(message):
    bot.send_message(message.chat.id, """📖【管理员须知】
▫️用户提交单据后，你会收到审核通知
▫️点通知下方【通过/驳回】按钮完成审核
▫️待审核清单：拉取全部待审单据
▫️所有数据保存在后端数据库，重启不丢失""")


# ========== 内嵌按钮回调 ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_click(call):
    if call.data == "cb_order":
        user_state[call.from_user.id] = "ordering"
        bot.send_message(call.message.chat.id, "📝【提交供需上架】\n请完整发送：\n需求/供货类型｜数量｜备注")

    elif call.data == "cb_status":
        bot.send_message(call.message.chat.id, "🔍【查询上架单】\n请发送供需上架编号")

    elif call.data == "cb_cancel":
        bot.send_message(call.message.chat.id, "🚫【撤销上架单】\n请发送供需上架编号（仅待审核可撤）")

    elif call.data == "cb_help":
        bot.send_message(call.message.chat.id, """📖【用户须知】
▫️填写信息后预览确认提交
▫️提交后等待管理员审核
▫️保存编号，用于查询进度
▫️仅待审核状态可撤销""")

    elif call.data.startswith("confirm_submit_"):
        uid = int(call.data.split("_")[-1])
        content = preview_cache.get(uid)
        if not content:
            bot.answer_callback_query(call.id, "内容已失效，请重新填写！")
            return
        try:
            payload = {"user_id": uid, "username": call.from_user.username or "", "content": content}
            r = requests.post(SUBMIT_URL, json=payload, timeout=15)
            ret = r.json()
            if ret.get("code") == 200:
                sid = ret["data"]["id"]
                admin_kb = types.InlineKeyboardMarkup(row_width=2)
                admin_kb.add(
                    types.InlineKeyboardButton("✅ 通过审核", callback_data=f"audit_pass_{sid}"),
                    types.InlineKeyboardButton("❌ 驳回上架", callback_data=f"audit_reject_{sid}"),
                )
                admin_msg = f"""📩【新供需上架通知】
🆔编号：{sid}
👤用户ID：{uid}
🔖用户名：@{call.from_user.username or '无'}
📄内容：
{content}
📌状态：待审核"""
                bot.send_message(ADMIN_ID, admin_msg, reply_markup=admin_kb)
                bot.edit_message_text(
                    f"✅ 提交成功！\n🆔单据编号：`{sid}`\n后台等待管理员审核，请保存编号",
                    call.message.chat.id, call.message.message_id, parse_mode="Markdown"
                )
                del preview_cache[uid]
            else:
                bot.answer_callback_query(call.id, ret.get("msg", "提交失败"))
        except Exception:
            bot.answer_callback_query(call.id, "后台接口请求失败")

    elif call.data.startswith("audit_"):
        parts = call.data.split("_")
        action = parts[1]
        sid = parts[2]
        status = "pass" if action == "pass" else "reject"
        try:
            payload = {"id": sid, "status": status}
            res = requests.post(AUDIT_URL, json=payload, timeout=15).json()
            if res.get("code") == 200:
                info = res["data"]
                user_id = info["user_id"]
                if status == "pass":
                    bot.send_message(user_id, f"🎉 你的单据【{sid}】审核已通过！")
                    bot.edit_message_text(f"✅ 单据【{sid}】已通过审核", call.message.chat.id, call.message.message_id)
                else:
                    bot.send_message(user_id, f"❌ 你的单据【{sid}】审核被驳回，请修改后重新提交")
                    bot.edit_message_text(f"❌ 单据【{sid}】已驳回", call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id, "审核完成")
            else:
                bot.answer_callback_query(call.id, res.get("msg", "审核失败"))
        except Exception:
            bot.answer_callback_query(call.id, "接口异常")

    bot.answer_callback_query(call.id)


# ========== 用户输入内容 -> 预览 ==========
@bot.message_handler(func=lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id] == "ordering")
def preview_input(msg):
    uid = msg.from_user.id
    content = msg.text
    preview_cache[uid] = content
    del user_state[uid]

    preview_kb = types.InlineKeyboardMarkup()
    preview_kb.add(types.InlineKeyboardButton("✅ 确认提交上架", callback_data=f"confirm_submit_{uid}"))
    preview_text = f"""✦ 上架预览 ✦
📄 填写内容：
{content}

确认无误点击【确认提交上架】，单据提交后台等待管理员审核"""
    bot.send_message(msg.chat.id, preview_text, reply_markup=preview_kb)


# ========== 用户发数字 -> 查询 or 撤销 ==========
@bot.message_handler(func=lambda msg: msg.text and msg.text.strip().isdigit())
def handle_number(msg):
    sid = msg.text.strip()
    uid = msg.from_user.id

    # 先尝试查询
    try:
        res = requests.get(GET_INFO_URL, params={"id": sid}, timeout=15).json()
        if res.get("code") == 200:
            d = res["data"]
            # 如果是待审核且是本人发的，提示可以撤销
            hint = ""
            if d.get("status_text") == "待审核":
                hint = "\n💡 如需撤销，请发送 /cancel 后输入编号"
            bot.send_message(msg.chat.id,
                f"📋 单据详情\n🆔编号：{d['id']}\n👤提交人：@{d['username']}\n📄内容：{d['content']}\n📌状态：{d['status_text']}{hint}")
            return
    except Exception:
        pass

    bot.send_message(msg.chat.id, "查询失败，请检查编号是否正确")


# ========== 指令兜底 ==========
@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(message.chat.id, "📖 提交上架填写内容预览确认，后台统一审核，凭编号查询状态")

@bot.message_handler(commands=['order'])
def cmd_order(message):
    user_state[message.from_user.id] = "ordering"
    bot.send_message(message.chat.id, "📝【提交供需上架】\n请发送：需求/供货类型｜数量｜备注")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    bot.send_message(message.chat.id, "🔍【查询上架单】\n请发送单据编号")

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    # 记录用户要撤销，下一步发编号
    user_state[message.from_user.id] = "cancelling"
    bot.send_message(message.chat.id, "🚫【撤销上架单】\n请发送要撤销的单据编号")

@bot.message_handler(func=lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id] == "cancelling")
def do_cancel(msg):
    sid = msg.text.strip()
    uid = msg.from_user.id
    del user_state[uid]
    try:
        res = requests.post(CANCEL_URL, json={"id": sid, "user_id": uid}, timeout=15).json()
        if res.get("code") == 200:
            bot.send_message(msg.chat.id, f"✅ 单据【{sid}】撤销成功")
            bot.send_message(ADMIN_ID, f"❌ 单据【{sid}】用户自行撤销")
        else:
            bot.send_message(msg.chat.id, res.get("msg", "撤销失败"))
    except Exception:
        bot.send_message(msg.chat.id, "撤销接口异常")

@bot.message_handler(commands=['list'])
def cmd_list(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⚠️ 仅管理员可用")
        return
    try:
        res = requests.get(LIST_WAIT_URL, timeout=15).json()
        if res.get("code") != 200:
            bot.send_message(message.chat.id, "获取失败")
            return
        lst = res["data"]
        if not lst:
            bot.send_message(message.chat.id, "✦ 暂无待审核单据")
            return
        t = "✦ 待审核清单 ✦\n"
        for item in lst:
            t += f"\n🆔{item['id']} | @{item['username']}"
        bot.send_message(message.chat.id, t)
    except Exception:
        bot.send_message(message.chat.id, "接口异常")


if __name__ == "__main__":
    print("Bot启动成功，对接后端:", BASE_API)
    bot.polling()
