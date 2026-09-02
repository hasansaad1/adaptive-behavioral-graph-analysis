"""Smoke tests for AndroCT / DroidFax logcat parsing."""

from __future__ import annotations

from abrg.androct.categorize import categorize_soot_callee, parse_soot_method_signature
from abrg.androct.parse import parse_androct_logcat


def test_jimple_quoting():
    sig = "<io.fabric.sdk.android.Fabric: io.fabric.sdk.android.Fabric 'with'(android.content.Context,io.fabric.sdk.android.Kit[])>"
    parsed = parse_soot_method_signature(sig)
    assert parsed is not None
    assert parsed[1] == "with"


def test_annotation_quoting():
    sig = "<java.lang.reflect.Field: java.lang.'annotation'.Annotation getAnnotation(java.lang.Class)>"
    parsed = parse_soot_method_signature(sig)
    assert parsed is not None
    assert parsed[0] == "java.lang.reflect.Field"
    assert parsed[1] == "getAnnotation"


def test_categorize_network():
    sig = "<java.net.URL: java.net.URLConnection openConnection()>"
    assert categorize_soot_callee(sig) == "network"


def test_parse_call_reflection_and_icc():
    text = """--------- beginning of main
<com.example.App: void onCreate()> -> <android.app.Activity: void onCreate(android.os.Bundle)>
+through reflection
<com.example.App: void reflect()> -> <android.telephony.SmsManager: void sendTextMessage(java.lang.String,java.lang.String,java.lang.String,android.app.PendingIntent,android.app.PendingIntent)>
[ Intent sent ]
caller=<com.example.App: void go()>
callsite=virtualinvoke $r0.<android.content.Context: void startActivity(android.content.Intent)>($r1)
\tAction=android.intent.action.VIEW
\tPackageName=null
noise from logcat that should drop
"""
    report, events = parse_androct_logcat(text, path="ABCD.apk.logcat", yield_events=True)
    assert events is not None
    assert report.n_call_events == 2
    assert report.n_icc_events == 1
    assert report.n_reflection_calls == 1
    assert report.n_dropped >= 2  # beginning + noise
    assert report.category_counts["sms"] >= 1
    assert report.category_counts["ipc_intents"] >= 1
    assert not report.header_only


def test_header_only():
    text = """--------- beginning of /dev/log/main
--------- beginning of /dev/log/system
"""
    report, _ = parse_androct_logcat(text, yield_events=False)
    assert report.header_only
    assert report.n_events == 0


def test_call_re_accepts_init_clinit():
    from abrg.androct.parse import _CALL_RE

    init_line = (
        "<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> "
        "<dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,"
        "java.lang.String,java.lang.ClassLoader)>"
    )
    clinit_line = (
        "<com.google.android.gms.ads.e: void <clinit>()> -> "
        "<com.google.android.gms.ads.e: void <init>(int,int,java.lang.String)>"
    )
    assert _CALL_RE.match(init_line)
    assert _CALL_RE.match(clinit_line)
    assert categorize_soot_callee(
        "<dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,"
        "java.lang.String,java.lang.ClassLoader)>"
    ) == "dynamic_code_loading"
    assert categorize_soot_callee(
        "<dalvik.system.PathClassLoader: void <init>(java.lang.String,java.lang.ClassLoader)>"
    ) == "dynamic_code_loading"
