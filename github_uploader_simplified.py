__version__ = (1, 0, 0)

#             █ █ ▀ █▄▀ ▄▀█ █▀█ ▀
#             █▀█ █ █ █ █▀█ █▀▄ █
#              © Copyright 2024
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html

# meta pic: https://static.dan.tatar/github_icon.png
# meta banner: https://mods.hikariatama.ru/badges/github.jpg
# meta developer: @hikarimods
# scope: hikka_only
# scope: hikka_min 1.2.10

import asyncio
import base64
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Optional

import aiohttp
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class GitHubUploader(loader.Module):
    """Upload files to GitHub repository"""
    
    strings = {
        "name": "GitHubUploader",
        "no_token": (
            "❌ <b>GitHub token not configured!</b>\n\n"
            "<i>Get your token at: https://github.com/settings/tokens\n"
            "Required permissions: repo (full control)</i>\n\n"
            "<code>{prefix}ghset &lt;token&gt;</code>"
        ),
        "token_set": "✅ <b>GitHub token configured successfully!</b>",
        "invalid_token": "❌ <b>Invalid GitHub token!</b>",
        "no_file": "❌ <b>Reply to a file to upload it!</b>",
        "uploading": "⏳ <b>Uploading file to GitHub...</b>",
        "upload_success": (
            "✅ <b>File uploaded successfully!</b>\n\n"
            "📄 <b>File:</b> <code>{filename}</code>\n"
            "🔗 <b>link:</b>\n<code>{url}</code>"
        ),
        "upload_error": "❌ <b>Upload failed:</b> <code>{error}</code>",
        "file_too_large": (
            "❌ <b>File too large!</b>\n"
            "<i>GitHub has a 100MB limit for single files</i>"
        ),
        "invalid_filename": "❌ <b>Invalid filename!</b>",
        "rate_limit": (
            "⚠️ <b>Rate limit exceeded!</b>\n"
            "<i>Please wait before uploading more files</i>"
        ),
    }
    
    strings_ru = {
        "no_token": (
            "❌ <b>GitHub токен не настроен!</b>\n\n"
            "<i>Получите токен на: https://github.com/settings/tokens\n"
            "Необходимые права: repo (полный контроль)</i>\n\n"
            "<code>{prefix}ghset &lt;токен&gt;</code>"
        ),
        "token_set": "✅ <b>GitHub токен успешно настроен!</b>",
        "invalid_token": "❌ <b>Неверный GitHub токен!</b>",
        "no_file": "❌ <b>Ответьте на файл для загрузки!</b>",
        "uploading": "⏳ <b>Загружаю файл...</b>",
        "upload_success": (
            "✅ <b>Файл успешно загружен!</b>\n\n"
            "📄 <b>Файл:</b> <code>{filename}</code>\n"
            "🔗 <b>ссылка:</b>\n<code>{url}</code>"
        ),
        "upload_error": "❌ <b>Ошибка загрузки:</b> <code>{error}</code>",
        "file_too_large": (
            "❌ <b>Файл слишком большой!</b>\n"
            "<i>GitHub ограничивает размер файла до 100МБ</i>"
        ),
        "invalid_filename": "❌ <b>Неверное имя файла!</b>",
        "rate_limit": (
            "⚠️ <b>Превышен лимит запросов!</b>\n"
            "<i>Подождите перед загрузкой следующего файла</i>"
        ),
        "_cmd_doc_ghset": "Настроить GitHub токен",
        "_cmd_doc_ghupload": "Загрузить файл на GitHub",
        "_cls_doc": "Загружайте файлы на GitHub и получайте прямые ссылки",
    }
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "github_token",
                "",
                "GitHub Personal Access Token",
                validator=loader.validators.Hidden(),
            ),
        )
    
    async def client_ready(self, client, db):
        self._client = client
        self._me = await client.get_me()
        self._session = aiohttp.ClientSession()
        self._last_upload = {}
    
    async def on_unload(self):
        if hasattr(self, '_session'):
            await self._session.close()
    
    def _get_repo_name(self) -> str:
        return f"git-{self._me.id}-files"
    
    def _sanitize_filename(self, filename: str) -> str:
        # Replace spaces with asterisks
        filename = filename.replace(' ', '*')
        
        # Replace other invalid characters with underscores
        invalid_chars = '<>:"|?*\\'
        for char in invalid_chars:
            if char != '*':  # Don't replace asterisks we just added
                filename = filename.replace(char, '_')
        
        if not filename.strip():
            filename = f"file_{int(time.time())}"
        
        return filename.strip()
    
    async def _get_unique_filename(self, username: str, repo_name: str, filename: str) -> str:
        name, ext = os.path.splitext(filename)
        counter = 0
        current_filename = filename
        
        while True:
            try:
                await self._make_github_request("GET", f"/repos/{username}/{repo_name}/contents/{current_filename}")
                counter += 1
                current_filename = f"{name}_{counter}{ext}"
            except Exception:
                break
                
        return current_filename
    
    async def _make_github_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        headers = {
            "Authorization": f"token {self.config['github_token']}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Heroku-GitHubUploader/1.0"
        }
        
        url = f"https://api.github.com{endpoint}"
        
        try:
            async with self._session.request(method, url, headers=headers, json=data) as response:
                result = await response.json()
                
                if response.status == 403 and "rate limit" in str(result).lower():
                    raise Exception("Rate limit exceeded")
                
                if response.status >= 400:
                    error_message = result.get("message", f"HTTP {response.status}")
                    raise Exception(error_message)
                
                return result
        except aiohttp.ClientError as e:
            raise Exception(f"Network error: {str(e)}")
    
    async def _get_github_username(self) -> str:
        try:
            user_data = await self._make_github_request("GET", "/user")
            return user_data["login"]
        except Exception as e:
            raise Exception(f"Failed to get username: {str(e)}")
    
    async def _repository_exists(self, username: str, repo_name: str) -> bool:
        try:
            await self._make_github_request("GET", f"/repos/{username}/{repo_name}")
            return True
        except Exception:
            return False
    
    async def _create_repository(self, repo_name: str) -> dict:
        data = {
            "name": repo_name,
            "description": f"File storage repository created by heroku userbot",
            "private": False,
            "auto_init": True
        }
        
        return await self._make_github_request("POST", "/user/repos", data)
    
    async def _upload_file(self, username: str, repo_name: str, filename: str, content: bytes) -> dict:
        content_b64 = base64.b64encode(content).decode('utf-8')
        
        file_exists = False
        existing_sha = None
        try:
            existing_file = await self._make_github_request("GET", f"/repos/{username}/{repo_name}/contents/{filename}")
            file_exists = True
            existing_sha = existing_file["sha"]
        except Exception:
            pass
        
        commit_message = f"Upload {filename}" if not file_exists else f"Update {filename}"
        data = {
            "message": commit_message,
            "content": content_b64,
            "branch": "main"
        }
        
        if file_exists:
            data["sha"] = existing_sha
        
        return await self._make_github_request("PUT", f"/repos/{username}/{repo_name}/contents/{filename}", data)
    
    async def _check_rate_limit(self, user_id: int) -> bool:
        now = time.time()
        last_upload = self._last_upload.get(user_id, 0)
        
        if now - last_upload < 10:
            return False
        
        self._last_upload[user_id] = now
        return True
    
    async def ghsetcmd(self, message: Message):
        """Configure GitHub token"""
        args = utils.get_args_raw(message)
        
        if not args:
            await utils.answer(
                message,
                self.strings("no_token").format(prefix=self.get_prefix())
            )
            return
        
        old_token = self.config["github_token"]
        self.config["github_token"] = args.strip()
        
        try:
            await self._get_github_username()
            await utils.answer(message, self.strings("token_set"))
        except Exception:
            self.config["github_token"] = old_token
            await utils.answer(message, self.strings("invalid_token"))
    
    async def ghuploadcmd(self, message: Message):
        """Upload file to GitHub"""
        if not self.config["github_token"]:
            await utils.answer(
                message,
                self.strings("no_token").format(prefix=self.get_prefix())
            )
            return
        
        if not await self._check_rate_limit(message.sender_id):
            await utils.answer(message, self.strings("rate_limit"))
            return
        
        reply = await message.get_reply_message()
        if not reply or not reply.file:
            await utils.answer(message, self.strings("no_file"))
            return
        
        if reply.file.size > 100 * 1024 * 1024:
            await utils.answer(message, self.strings("file_too_large"))
            return
        
        status_msg = await utils.answer(message, self.strings("uploading"))
        
        try:
            file_bytes = await reply.download_media(bytes)
            
            filename = reply.file.name or f"file_{int(time.time())}"
            filename = self._sanitize_filename(filename)
            
            if not filename:
                await utils.answer(status_msg, self.strings("invalid_filename"))
                return
            
            username = await self._get_github_username()
            repo_name = self._get_repo_name()
            
            repo_exists = await self._repository_exists(username, repo_name)
            
            if not repo_exists:
                await self._create_repository(repo_name)
                await asyncio.sleep(2)
            
            unique_filename = await self._get_unique_filename(username, repo_name, filename)
            
            upload_result = await self._upload_file(username, repo_name, unique_filename, file_bytes)
            
            raw_url = f"https://raw.githubusercontent.com/{username}/{repo_name}/main/{unique_filename}"
            
            success_text = self.strings("upload_success").format(
                filename=unique_filename,
                url=raw_url
            )
            
            await utils.answer(status_msg, success_text)
            
        except Exception as e:
            error_text = self.strings("upload_error").format(error=str(e))
            await utils.answer(status_msg, error_text)