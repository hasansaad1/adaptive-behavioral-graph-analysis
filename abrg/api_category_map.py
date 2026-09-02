"""Map framework APIs / DEX callees to CATEGORY_UNIVERSE (aligned with hook_apis.js v3)."""

from __future__ import annotations

from pathlib import Path

# Frida logEvent(api_label, category) — hook_apis.js v3
HOOK_API_TO_CATEGORY: dict[str, str] = {
    "SmsManager.sendTextMessage": "sms",
    "SmsManager.sendMultipartTextMessage": "sms",
    "URL.openConnection": "network",
    "HttpURLConnection.connect": "network",
    "okhttp3.RealCall.execute": "network",
    "okhttp3.RealCall.enqueue": "network",
    "retrofit2.OkHttpCall.execute": "network",
    "volley.RequestQueue.add": "network",
    "Socket.connect": "network",
    "FileOutputStream.<init>": "file_io",
    "FileInputStream.<init>": "file_io",
    "File.delete": "file_io",
    "AssetManager.open": "file_io",
    "Cipher.getInstance": "crypto",
    "Cipher.doFinal": "crypto",
    "SecretKeySpec.<init>": "crypto",
    "MessageDigest.getInstance": "crypto",
    "MessageDigest.digest": "crypto",
    "Runtime.exec": "process",
    "ProcessBuilder.start": "process",
    "ContentResolver.query": "content_access",
    "ContentResolver.insert": "content_access",
    "ContentResolver.update": "content_access",
    "ContentResolver.delete": "content_access",
    "ClipboardManager.setPrimaryClip": "clipboard",
    "Camera.open": "camera",
    "CameraManager.openCamera": "camera",
    "PackageManager.getInstalledPackages": "package_manager",
    "PackageManager.getInstalledApplications": "package_manager",
    "LocationManager.requestLocationUpdates": "location",
    "TelephonyManager.getDeviceId": "device_info",
    "TelephonyManager.getSubscriberId": "device_info",
    "TelephonyManager.getSimSerialNumber": "device_info",
    "TelephonyManager.getCallState": "telephony",
    "DexClassLoader.<init>": "dynamic_code_loading",
    "PathClassLoader.<init>": "dynamic_code_loading",
    "AccountManager.getAccounts": "accounts",
    "AccountManager.getAccountsByType": "accounts",
    "AudioRecord.<init>": "audio",
    "MediaRecorder.setAudioSource": "audio",
    "SharedPreferences.getString": "storage",
    "SharedPreferences.getInt": "storage",
    "SharedPreferences.putString": "storage",
    "SharedPreferences.apply": "storage",
    "SQLiteDatabase.rawQuery": "database",
    "SQLiteDatabase.execSQL": "database",
    "SQLiteDatabase.insert": "database",
    "MediaPlayer.setDataSource": "media",
    "MediaPlayer.start": "media",
    "MediaPlayer.prepare": "media",
    "Context.startActivity": "ipc_intents",
    "Context.sendBroadcast": "ipc_intents",
    "Context.startService": "ipc_intents",
    "Context.bindService": "ipc_intents",
    "WebView.loadUrl": "webview",
    "NotificationManager.notify": "notifications",
    "NotificationManager.notifyAsUser": "notifications",
    "System.loadLibrary": "native_code",
    "Runtime.load": "native_code",
    "Runtime.loadLibrary": "native_code",
    "hook_loaded": "lifecycle",
    "Method.invoke": "reflection",
}

PERM_TO_CATEGORIES: dict[str, set[str]] = {
    "INTERNET": {"network"},
    "ACCESS_NETWORK_STATE": {"network"},
    "CAMERA": {"camera"},
    "RECORD_AUDIO": {"audio"},
    "ACCESS_FINE_LOCATION": {"location"},
    "ACCESS_COARSE_LOCATION": {"location"},
    "ACCESS_BACKGROUND_LOCATION": {"location"},
    "READ_CONTACTS": {"content_access"},
    "WRITE_CONTACTS": {"content_access"},
    "READ_CALL_LOG": {"telephony", "content_access"},
    "WRITE_CALL_LOG": {"telephony"},
    "READ_SMS": {"sms", "content_access"},
    "SEND_SMS": {"sms"},
    "RECEIVE_SMS": {"sms"},
    "READ_CALENDAR": {"content_access"},
    "WRITE_CALENDAR": {"content_access"},
    "READ_EXTERNAL_STORAGE": {"file_io"},
    "WRITE_EXTERNAL_STORAGE": {"file_io"},
    "READ_MEDIA_IMAGES": {"file_io", "media"},
    "READ_MEDIA_VIDEO": {"file_io", "media"},
    "READ_MEDIA_AUDIO": {"file_io", "media"},
    "GET_ACCOUNTS": {"accounts"},
    "USE_CREDENTIALS": {"accounts"},
    "READ_PHONE_STATE": {"device_info", "telephony"},
    "READ_PHONE_NUMBERS": {"device_info"},
    "CALL_PHONE": {"telephony"},
    "POST_NOTIFICATIONS": {"notifications"},
    "BLUETOOTH": {"network"},
    "BLUETOOTH_CONNECT": {"network"},
    "NFC": {"network"},
    "FOREGROUND_SERVICE": {"ipc_intents"},
}

CATEGORY_SENSITIVITY_OVERRIDE: dict[str, float] = {
    "dynamic_code_loading": 0.9,
    "native_code": 0.9,
    "ipc_intents": 0.5,
    "sms": 0.7,
    "telephony": 0.7,
    "device_info": 0.7,
    "location": 0.7,
    "camera": 0.7,
    "audio": 0.7,
    "content_access": 0.7,
}

PROTECTION_TO_GATE_IDX: dict[str, int] = {
    "normal": 0,
    "dangerous": 1,
    "signature": 2,
    "signatureOrSystem": 2,
    "privileged": 2,
    "internal": 2,
}

PROTECTION_TO_SENSITIVITY: dict[str, float] = {
    "normal": 0.2,
    "dangerous": 0.7,
    "signature": 0.9,
    "signatureOrSystem": 0.9,
    "privileged": 0.9,
    "internal": 0.9,
}


def _smali_to_dotted(class_name: str) -> str:
    """Landroid/foo/Bar; -> android.foo.Bar"""
    if class_name.startswith("L") and class_name.endswith(";"):
        return class_name[1:-1].replace("/", ".")
    return class_name.replace("/", ".")


def categorize_callee(class_name: str, method_name: str) -> set[str]:
    """Infer hook categories from a DEX callee (static analysis)."""
    dotted = _smali_to_dotted(class_name)
    simple = dotted.split(".")[-1]
    label = f"{simple}.{method_name}"
    if method_name == "<init>":
        label = f"{simple}.<init>"

    cats: set[str] = set()
    if label in HOOK_API_TO_CATEGORY:
        cats.add(HOOK_API_TO_CATEGORY[label])

    prefix_rules: list[tuple[str, str]] = [
        ("javax.crypto", "crypto"),
        ("java.security.MessageDigest", "crypto"),
        ("java.security.", "crypto"),
        ("java.net.", "network"),
        ("okhttp3.", "network"),
        ("retrofit2.", "network"),
        ("com.android.volley", "network"),
        ("java.io.File", "file_io"),
        ("java.io.FileInputStream", "file_io"),
        ("java.io.FileOutputStream", "file_io"),
        ("android.content.res.AssetManager", "file_io"),
        ("android.telephony.SmsManager", "sms"),
        ("android.telephony.TelephonyManager", "device_info"),
        ("android.location.", "location"),
        ("android.hardware.camera", "camera"),
        ("android.hardware.Camera", "camera"),
        ("dalvik.system.DexClassLoader", "dynamic_code_loading"),
        ("dalvik.system.PathClassLoader", "dynamic_code_loading"),
        ("android.content.ContentResolver", "content_access"),
        ("android.database.sqlite", "database"),
        ("android.app.SharedPreferences", "storage"),
        ("android.webkit.WebView", "webview"),
        ("android.media.MediaPlayer", "media"),
        ("android.media.AudioRecord", "audio"),
        ("android.media.MediaRecorder", "audio"),
        ("android.accounts.AccountManager", "accounts"),
        ("android.content.pm.PackageManager", "package_manager"),
        ("android.app.ApplicationPackageManager", "package_manager"),
        ("android.app.NotificationManager", "notifications"),
        ("android.content.ClipboardManager", "clipboard"),
        ("java.lang.Runtime", "process"),
        ("java.lang.ProcessBuilder", "process"),
        ("android.content.Intent", "ipc_intents"),
        ("android.app.PendingIntent", "ipc_intents"),
        ("java.lang.System", "native_code"),
    ]
    for prefix, cat in prefix_rules:
        if dotted.startswith(prefix) or class_name.replace("/", ".").find(prefix.replace(".", "/")) >= 0:
            cats.add(cat)

    if method_name in ("startActivity", "startActivities"):
        if "android.content" in dotted or "android.app" in dotted:
            cats.add("ipc_intents")
            cats.add("navigation")
    elif method_name in ("sendBroadcast", "startService", "bindService"):
        if "android.content" in dotted or "android.app" in dotted:
            cats.add("ipc_intents")

    if method_name == "invoke" and simple == "Method":
        cats.add("reflection")

    if method_name in ("loadLibrary", "load") and ("java.lang.Runtime" in dotted or "java.lang.System" in dotted):
        cats.add("native_code")

    return cats


def perm_short_name(perm: str) -> str:
    """android.permission.INTERNET -> INTERNET"""
    return perm.split(".")[-1] if perm else ""


def apk_path_from_session_dir(session_dir: Path) -> Path | None:
    """Read apk_path from *_dynamic_metadata.json next to the trace."""
    matches = list(session_dir.glob("*_dynamic_metadata.json"))
    if not matches:
        return None
    import json

    meta = json.loads(matches[0].read_text(encoding="utf-8"))
    raw = meta.get("apk_path")
    return Path(raw) if raw else None
