"""
Push Notification Service using Firebase Cloud Messaging (FCM)

This service handles sending push notifications to users across:
- Web browsers (Chrome, Firefox, Edge)
- Android devices
- iOS devices (with native app)
"""

import os
import json
import httpx
from typing import Optional
from datetime import datetime

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

import structlog
from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = structlog.get_logger(__name__)

# Firebase configuration - loaded after dotenv
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")  # Path to service account JSON
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")  # Or JSON string directly

# FCM API endpoint
FCM_URL = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"


class PushNotificationService:
    """Service for sending push notifications via Firebase Cloud Messaging."""
    
    def __init__(self):
        self.credentials = None
        self._init_credentials()
    
    def _init_credentials(self):
        """Initialize Google credentials for FCM."""
        try:
            if FIREBASE_CREDENTIALS_JSON:
                # Parse JSON string
                creds_dict = json.loads(FIREBASE_CREDENTIALS_JSON)
                self.credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"]
                )
            elif FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
                # Load from file
                self.credentials = service_account.Credentials.from_service_account_file(
                    FIREBASE_CREDENTIALS_PATH,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"]
                )
            else:
                logger.warning("firebase_credentials_not_configured", 
                             hint="Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH")
        except Exception as e:
            logger.error("firebase_credentials_error", error=str(e))
    
    def _get_access_token(self) -> Optional[str]:
        """Get valid access token for FCM API."""
        if not self.credentials:
            return None
        
        try:
            if self.credentials.expired or not self.credentials.valid:
                self.credentials.refresh(Request())
            return self.credentials.token
        except Exception as e:
            logger.error("firebase_token_refresh_error", error=str(e))
            return None
    
    async def send_notification(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        image: Optional[str] = None,
        call_style: bool = False
    ) -> bool:
        """
        Send a push notification to a specific device token.
        
        Args:
            token: FCM device token
            title: Notification title
            body: Notification body
            data: Additional data payload
            image: Image URL for rich notification
            call_style: If True, use call-specific settings
        
        Returns:
            True if sent successfully, False otherwise
        """
        access_token = self._get_access_token()
        if not access_token:
            logger.error("fcm_no_access_token")
            return False
        
        # Build message payload
        message = {
            "token": token,
            "notification": {
                "title": title,
                "body": body,
            },
            "data": data or {},
        }
        
        # Add image if provided
        if image:
            message["notification"]["image"] = image
        
        # Web-specific options (for action buttons)
        message["webpush"] = {
            "notification": {
                "title": title,
                "body": body,
                "icon": "/icons/synki-icon-192.png",
                "badge": "/icons/synki-badge-72.png",
                "tag": "synki-call" if call_style else "synki-notification",
                "requireInteraction": call_style,  # Keep visible for calls
                "vibrate": [200, 100, 200, 100, 200] if call_style else [100, 50, 100],
                "actions": [
                    {"action": "accept", "title": "📞 Accept"},
                    {"action": "reject", "title": "❌ Decline"}
                ] if call_style else []
            },
            "fcm_options": {
                "link": "/app.html"
            }
        }
        
        # Android-specific options
        message["android"] = {
            "priority": "high",
            "notification": {
                "title": title,
                "body": body,
                "icon": "ic_notification",
                "color": "#ff6b9d",
                "sound": "ringtone" if call_style else "default",
                "channel_id": "synki_calls" if call_style else "synki_notifications",
                "click_action": "OPEN_CALL" if call_style else "OPEN_APP"
            }
        }
        
        # iOS/APNs-specific options
        message["apns"] = {
            "headers": {
                "apns-priority": "10",
                "apns-push-type": "voip" if call_style else "alert"
            },
            "payload": {
                "aps": {
                    "alert": {
                        "title": title,
                        "body": body
                    },
                    "sound": "ringtone.caf" if call_style else "default",
                    "badge": 1,
                    "category": "INCOMING_CALL" if call_style else "DEFAULT"
                }
            }
        }
        
        # Send to FCM
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    FCM_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={"message": message},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info("fcm_notification_sent", token=token[:20]+"...", title=title)
                    return True
                else:
                    logger.error("fcm_send_failed", 
                               status=response.status_code, 
                               error=response.text)
                    return False
                    
        except Exception as e:
            logger.error("fcm_send_error", error=str(e))
            return False
    
    async def send_call_notification(
        self,
        token: str,
        caller_name: str = "Synki",
        message: str = "is calling you...",
        call_id: Optional[str] = None
    ) -> bool:
        """
        Send a call-style notification with Accept/Reject buttons.
        
        Args:
            token: FCM device token
            caller_name: Name to show as caller
            message: Call message
            call_id: Optional call ID for tracking
        
        Returns:
            True if sent successfully
        """
        return await self.send_notification(
            token=token,
            title=f"📞 {caller_name}",
            body=message,
            data={
                "type": "incoming_call",
                "call_id": call_id or "",
                "caller": caller_name,
                "timestamp": datetime.now().isoformat()
            },
            call_style=True
        )
    
    async def send_to_user_devices(
        self,
        user_id: str,
        tokens: list,
        title: str,
        body: str,
        data: Optional[dict] = None,
        call_style: bool = False
    ) -> dict:
        """
        Send notification to all of a user's devices.
        
        Args:
            user_id: User ID
            tokens: List of FCM tokens for the user
            title: Notification title
            body: Notification body
            data: Additional data
            call_style: If True, use call-specific settings
        
        Returns:
            Dict with success/failure counts
        """
        results = {"success": 0, "failed": 0, "tokens_to_remove": []}
        
        for token in tokens:
            success = await self.send_notification(
                token=token,
                title=title,
                body=body,
                data=data,
                call_style=call_style
            )
            
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                # Token might be invalid - mark for removal
                results["tokens_to_remove"].append(token)
        
        logger.info("fcm_batch_send_complete", 
                   user_id=user_id, 
                   success=results["success"], 
                   failed=results["failed"])
        
        return results


# Singleton instance
push_service = PushNotificationService()
