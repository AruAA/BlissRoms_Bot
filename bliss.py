from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
import json
import httpx
import datetime
import humanfriendly
import html
from typing import Final, Dict, Optional, List, Tuple
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
import asyncio

# YAML Helper
def load_config(filename):
    with open(filename, "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config

config_data = load_config("config.yml")
telegram_config = config_data["telegram"]
bliss_config = config_data["bliss"]

# Constants
API_ID: Final[int] = int(telegram_config["api_id"])
API_HASH: Final[str] = telegram_config["api_hash"]
BOT_TOKEN: Final[str] = telegram_config["bot_token"]
AUTHORIZED_IDS: Final[List[int]] = [int(telegram_id) for telegram_id in telegram_config["authorized_ids"]]
DOWNLOAD_BASE_URL: Final[str] = bliss_config["download_url"]

# Pyrogram Client
app = Client("BlissBot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Scheduled Jobs
async def download_devices_job() -> None:
    devices_file = "devices.json"
    devices_url = "https://raw.githubusercontent.com/BlissRoms-Devices/official-devices/main/devices.json"
    if os.path.isfile(devices_file):
        new_devices_file = "new_devices.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(devices_url)
            if response.status_code != 200:
                print(f"Request failed with status code: {response.status_code}")
                return None
            with open(new_devices_file, "w") as f:
                json.dump(json.loads(response.text), f)
        if os.path.getsize(devices_file) != os.path.getsize(new_devices_file):
            os.remove(devices_file)
            os.rename(new_devices_file, devices_file)
        else:
            os.remove(new_devices_file)
    else:
        async with httpx.AsyncClient() as client:
            response = await client.get(devices_url)
            if response.status_code != 200:
                print(f"Request failed with status code: {response.status_code}")
                return None
            with open(devices_file, "w") as f:
                json.dump(json.loads(response.text), f)

# Helper Functions
async def devices_list() -> Optional[Dict[str, Dict[str, str]]]:
    devices_file = "devices.json"
    devices: Dict[str, str] = {}
    try:
        with open(devices_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        devices_url = "https://raw.githubusercontent.com/BlissRoms-Devices/official-devices/main/devices.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(devices_url)
            if response.status_code != 200:
                print(f"Request failed with status code: {response.status_code}")
                return None
            data = json.loads(response.text)
            with open(devices_file, "w") as f:
                json.dump(data, f)
    for device in data:
        device_data: Dict[str, str] = {
            'brand': device['brand'],
            'name': device['name'],
            'maintainer': device['supported_versions'][0]['maintainer_name'],
            'support': device['supported_versions'][0]['support_thread'],
        }
        device_codename: str = device['codename']
        devices[device_codename] = device_data
    return devices

async def get_device_info(device_codename: str) -> Optional[Dict[str, str]]:
    devices_file = "devices.json"
    try:
        with open(devices_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await download_devices_job()
    for device in data:
        if device['codename'] != device_codename:
            continue
        return {
            'brand': device['brand'],
            'name': device['name'],
            'maintainer': device['supported_versions'][0]['maintainer_name'],
            'support': device['supported_versions'][0]['support_thread'],
        }
    
async def get_vanilla_build(device_codename: str) -> Optional[Dict[str, str]]:
    download_url = DOWNLOAD_BASE_URL.format(device_codename, "vanilla")
    build_data: Dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        response = await client.get(download_url)
        if response.status_code != 200:
            print(f"Request failed with status code: {response.status_code}")
            return None
        device_data = json.loads(response.text)['response'][0]
        build_data = {
            'date': datetime.datetime.fromtimestamp(device_data['datetime']).strftime('%d-%m-%Y'),
            'size': humanfriendly.format_size(device_data['size']),
            'version': device_data['version'],
            'url': device_data['url'],
        }
        return build_data
    
async def get_gapps_build(device_codename: str) -> Optional[Dict[str, str]]:
    download_url = DOWNLOAD_BASE_URL.format(device_codename, "gapps")
    build_data: Dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        response = await client.get(download_url)
        if response.status_code != 200:
            print(f"Request failed with status code: {response.status_code}")
            return None
        device_data = json.loads(response.text)['response'][0]
        build_data = {
            'date': datetime.datetime.fromtimestamp(device_data['datetime']).strftime('%d-%m-%Y'),
            'size': humanfriendly.format_size(device_data['size']),
            'version': device_data['version'],
            'url': device_data['url'],
        }
        return build_data
    
# Pyrogram Helper Functions
def get_build_keyboard(vanilla_build_url: str, gapps_build_url: str, device_codename: str) -> Optional[InlineKeyboardMarkup]:
    blank_keyboard = []
    if vanilla_build_url:
        blank_keyboard.append([InlineKeyboardButton(text=f"Download Vanilla Build ({device_codename})", url=vanilla_build_url)])
    if gapps_build_url:
        blank_keyboard.append([InlineKeyboardButton(text=f"Download GApps Build ({device_codename})", url=gapps_build_url)])
    if len(blank_keyboard) > 0:
        blank_keyboard.append([InlineKeyboardButton("Close", callback_data="close")])
    else:
        return None
    
    build_keyboard = InlineKeyboardMarkup(
        blank_keyboard
    )
    return build_keyboard

def get_device_text(device_vanilla_build: Optional[Dict[str, str]], device_gapps_build: Optional[Dict[str, str]], device_data: Optional[Dict[str, str]], device_codename: str) -> Tuple[str, Optional[InlineKeyboardMarkup], bool]:
    build_found = False
    if not device_data:
        device_text = ""
    else:
        device_text = f"<strong>Device:</strong> {device_data.get('brand')} {device_data.get('name')}\n<strong>Maintainer:</strong> {device_data.get('maintainer')}\n<strong>Support:</strong> {device_data.get('support')}\n\n"
        if device_vanilla_build:
            build_found = True
            device_text += f"<strong>Build Type:</strong> Vanilla\n<strong>Build Date:</strong> {device_vanilla_build.get('date')}\n<strong>Build Size:</strong> {device_vanilla_build.get('size')}\n<strong>Build Version:</strong> {device_vanilla_build.get('version')}\n\n"
        if device_gapps_build:
            build_found = True
            device_text += f"<strong>Build Type:</strong> GApps\n<strong>Build Date:</strong> {device_gapps_build.get('date')}\n<strong>Build Size:</strong> {device_gapps_build.get('size')}\n<strong>Build Version:</strong> {device_gapps_build.get('version')}"
        build_keyboard = get_build_keyboard(device_vanilla_build.get('url') if device_vanilla_build is not None else None, device_gapps_build.get('url') if device_gapps_build is not None else None, device_codename)
    return device_text, build_keyboard, build_found

# Pyrogram Functions - Commands
@app.on_message(filters=filters.command("start"))
async def start_msg(_: Client, message: Message) -> None:
    await message.reply_text(text="Hey there, I'm Bliss Bot!\n\nUse `/help` to check the list of available commands.\nType `/bliss` {codename} to get BlissROMs for your device.", quote=True)

@app.on_message(filters=filters.command("help"))
async def help_msg(_: Client, message: Message) -> None:
    await message.reply_text(text="Available commands:\n\n`/bliss` {codename}: Check latest version available for your device.\n`/list`: Check the current list of officially supported devices.", quote=True)

@app.on_message(filters=filters.command("refresh"))
async def refresh_msg(_: Client, message: Message) -> None:
    if message.from_user.id not in AUTHORIZED_IDS:
        await message.reply_text(text="You are not authorized to use this command!", quote=True)
        return
    asyncio.gather(
        download_devices_job(),
        message.reply_text(text="Refreshed devices successfully!", quote=True),
    )

@app.on_message(filters=filters.command("list"))
async def list_msg(_: Client, message: Message) -> None:
    devices_list_full = await devices_list()
    list_message = await message.reply_text(text="Please wait, loading the device list...", quote=True)
    text: str = "<strong>Device List:</strong>\n\n"
    if devices_list_full:
        for device, device_data in devices_list_full.items():
            text += f"{html.escape(device_data.get('brand'))} {html.escape(device_data.get('name'))} (<code>{html.escape(device)}</code>)\n"
        await list_message.edit_text(text=text, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close")]]))
    else:
        await list_message.edit_text(text="Sorry, the device list could not be fetched!")

@app.on_message(filters=filters.command("bliss"))
async def bliss_msg(_: Client, message: Message) -> None:
    if len(message.text.split()) < 2 and not message.reply_to_message:
        await message.reply_text(text="Please mention the device codename after `/bliss`. Eg: `/bliss Z01R`", quote=True)
        return
    else:
        devices_list_full = await devices_list()
        if devices_list_full:
            device_codename = message.text.split()[1]
            if device_codename not in devices_list_full.keys():
                await message.reply_text(text="Bliss ROM for the specified device does not exist!\nUse `/list` to check the supported device list", quote=True)
            else:
                await _.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
                device_gapps_build = await get_gapps_build(device_codename=device_codename)
                device_vanilla_build = await get_vanilla_build(device_codename=device_codename)
                device_data = await get_device_info(device_codename=device_codename)
                device_text, build_keyboard, build_found = get_device_text(device_vanilla_build=device_vanilla_build, device_gapps_build=device_gapps_build, device_data=device_data, device_codename=device_codename)
                if not build_found:
                    await message.reply_text(text="Bliss ROM for the specified device does not exist!\nUse `/list` to check the supported device list", quote=True)
                else:
                    await message.reply_text(text=device_text, reply_markup=build_keyboard, parse_mode=enums.ParseMode.HTML, quote=True, disable_web_page_preview=True)
        else:
            await message.reply_text(text="Sorry, the device list could not be fetched!", quote=False)

# Pyrogram Functions - Callback Queries
@app.on_callback_query(filters=filters.regex("close"))
async def close_msg(_: Client, query: CallbackQuery) -> None:
    if query.message.chat.type == enums.ChatType.PRIVATE:
        await query.message.reply_to_message.delete()
    await query.message.delete()

scheduler = AsyncIOScheduler()
scheduler.add_job(func=download_devices_job, trigger="interval", hours=3, next_run_time=datetime.datetime.now(), misfire_grace_time=None)

scheduler.start()
app.run()