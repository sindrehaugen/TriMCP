import asyncio
import logging
import json
import httpx
from email.message import EmailMessage
import aiosmtplib

log = logging.getLogger("trimcp-notifications")

class NotificationDispatcher:
    def __init__(self):
        self.slack_webhook = None # To be loaded from config/env
        self.teams_webhook = None # To be loaded from config/env
        self.smtp_host = None     # To be loaded from config/env
        self._queue = asyncio.Queue(maxsize=1000)
        self._worker_task = None

    async def start_worker(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop_worker(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def _worker(self):
        while True:
            try:
                title, message = await self._queue.get()
                tasks = [
                    self._send_slack(title, message),
                    self._send_teams(title, message),
                    self._send_email(title, message),
                    self._send_snmp(title, message)
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Notification worker error: {e}")

    async def _send_slack(self, title: str, message: str):
        if not self.slack_webhook: return
        payload = {"text": f"*{title}*\n{message}"}
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.slack_webhook, json=payload, timeout=5)
        except Exception as e:
            log.error(f"Failed to send Slack notification: {e}")

    async def _send_teams(self, title: str, message: str):
        if not self.teams_webhook: return
        payload = {
            "title": title,
            "text": message
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.teams_webhook, json=payload, timeout=5)
        except Exception as e:
            log.error(f"Failed to send Teams notification: {e}")

    async def _send_email(self, title: str, message: str):
        if not self.smtp_host: return
        try:
            msg = EmailMessage()
            msg.set_content(message)
            msg['Subject'] = title
            msg['From'] = "trimcp-alerts@example.com"
            msg['To'] = "admin@example.com"
            await aiosmtplib.send(msg, hostname=self.smtp_host, port=25, timeout=5)
        except Exception as e:
            log.error(f"Failed to send Email notification: {e}")

    async def _send_snmp(self, title: str, message: str):
        # SNMP logic implementation here
        # Typically uses pysnmp, simplified as non-blocking for architecture demonstration
        pass

    async def dispatch_alert(self, title: str, message: str):
        """
        Dispatches alert across all configured channels non-blockingly via a supervised queue.
        """
        log.warning(f"Dispatching Alert: {title} - {message}")
        if self._worker_task is None:
            await self.start_worker()
            
        try:
            self._queue.put_nowait((title, message))
        except asyncio.QueueFull:
            log.error("Notification queue is full, dropping alert!")

dispatcher = NotificationDispatcher()
