# AndroCT 2017 — pre-graph diagnostics

- Generated (UTC): 2026-08-07T09:19:51.522103+00:00
- Scope: `datasets/androct_2017/` only (read-only).

## Check 1 — recall: sms / dynamic_code_loading

### Raw callee-position substring hits

| Class | Substring | Raw line count | Distinct apps |
|---|---|---:|---:|
| benign | `SmsManager` | 8 | 2 |
| benign | `android.telephony` | 9150 | 415 |
| benign | `sendTextMessage` | 0 | 0 |
| benign | `sendMultipartTextMessage` | 0 | 0 |
| benign | `SmsMessage` | 0 | 0 |
| benign | `DexClassLoader` | 93 | 4 |
| benign | `PathClassLoader` | 4 | 1 |
| benign | `BaseDexClassLoader` | 66 | 2 |
| benign | `InMemoryDexClassLoader` | 0 | 0 |
| benign | `System.load` | 0 | 0 |
| benign | `System.loadLibrary` | 0 | 0 |
| benign | `Runtime.exec` | 0 | 0 |
| malware | `SmsManager` | 0 | 0 |
| malware | `android.telephony` | 11233 | 328 |
| malware | `sendTextMessage` | 0 | 0 |
| malware | `sendMultipartTextMessage` | 0 | 0 |
| malware | `SmsMessage` | 0 | 0 |
| malware | `DexClassLoader` | 80 | 11 |
| malware | `PathClassLoader` | 0 | 0 |
| malware | `BaseDexClassLoader` | 15 | 1 |
| malware | `InMemoryDexClassLoader` | 0 | 0 |
| malware | `System.load` | 0 | 0 |
| malware | `System.loadLibrary` | 0 | 0 |
| malware | `Runtime.exec` | 0 | 0 |

#### Examples — benign

**`SmsManager`**
- `<com.anprosit.android.dagger.AndroidModule$$ModuleAdapter: void getBindings(dagger.internal.BindingsGroup,com.anprosit.android.dagger.AndroidModule)> -> <com.anprosit.android.dagger.AndroidModule$$ModuleAdapter$ProvideSmsManagerProvidesAdapter: void <init>(com.anprosit.android.dagger.AndroidModule)>`
- `<com.anprosit.android.dagger.AndroidModule$$ModuleAdapter: void getBindings(dagger.internal.BindingsGroup,com.anprosit.android.dagger.AndroidModule)> -> <com.anprosit.android.dagger.AndroidModule$$ModuleAdapter$ProvideSmsManagerProvidesAdapter: void <init>(com.anprosit.android.dagger.AndroidModule)>`
- `<com.anprosit.android.dagger.AndroidModule$$ModuleAdapter: void getBindings(dagger.internal.BindingsGroup,com.anprosit.android.dagger.AndroidModule)> -> <com.anprosit.android.dagger.AndroidModule$$ModuleAdapter$ProvideSmsManagerProvidesAdapter: void <init>(com.anprosit.android.dagger.AndroidModule)>`
- `<com.anprosit.android.dagger.AndroidModule$$ModuleAdapter: void getBindings(dagger.internal.BindingsGroup,com.anprosit.android.dagger.AndroidModule)> -> <com.anprosit.android.dagger.AndroidModule$$ModuleAdapter$ProvideSmsManagerProvidesAdapter: void <init>(com.anprosit.android.dagger.AndroidModule)>`
- `<com.anprosit.android.dagger.AndroidModule$$ModuleAdapter: void getBindings(dagger.internal.BindingsGroup,com.anprosit.android.dagger.AndroidModule)> -> <com.anprosit.android.dagger.AndroidModule$$ModuleAdapter$ProvideSmsManagerProvidesAdapter: void <init>(com.anprosit.android.dagger.AndroidModule)>`

**`android.telephony`**
- `<org.interlaken.common.net.d: byte c(android.content.Context)> -> <android.telephony.TelephonyManager: int getNetworkType()>`
- `<org.interlaken.common.b.m: java.lang.String c(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getSimOperator()>`
- `<org.interlaken.common.net.d: byte c(android.content.Context)> -> <android.telephony.TelephonyManager: int getNetworkType()>`
- `<org.interlaken.common.b.m: java.lang.String c(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getSimOperator()>`
- `<org.interlaken.common.net.d: byte c(android.content.Context)> -> <android.telephony.TelephonyManager: int getNetworkType()>`

**`DexClassLoader`**
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: void a(dalvik.system.BaseDexClassLoader,java.lang.Object)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`

**`PathClassLoader`**
- `<amazon.android.dexload.SupplementalDexLoader: void updateICSClassLoader(android.content.Context,boolean,java.util.List)> -> <amazon.android.dexload.SupplementalDexLoader: dalvik.system.PathClassLoader getClassLoader(android.content.Context)>`
- `<amazon.android.dexload.SupplementalDexLoader: void updateICSClassLoader(android.content.Context,boolean,java.util.List)> -> <amazon.android.dexload.SupplementalDexLoader: dalvik.system.PathClassLoader getClassLoader(android.content.Context)>`
- `<amazon.android.dexload.SupplementalDexLoader: void updateICSClassLoader(android.content.Context,boolean,java.util.List)> -> <amazon.android.dexload.SupplementalDexLoader: dalvik.system.PathClassLoader getClassLoader(android.content.Context)>`
- `<amazon.android.dexload.SupplementalDexLoader: void updateICSClassLoader(android.content.Context,boolean,java.util.List)> -> <amazon.android.dexload.SupplementalDexLoader: dalvik.system.PathClassLoader getClassLoader(android.content.Context)>`

**`BaseDexClassLoader`**
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: void a(dalvik.system.BaseDexClassLoader,java.lang.Object)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`

#### Examples — malware

**`android.telephony`**
- `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
- `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
- `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
- `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
- `<com.google.android.gms.internal.zzhi$zza: void zza(android.content.Context,android.content.pm.PackageManager)> -> <android.telephony.TelephonyManager: java.lang.String getNetworkOperator()>`

**`DexClassLoader`**
- `<com.qq.e.comm.managers.plugin.PM: void a()> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- `<ongmanibeimeihong.plugin.a: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- `<com.qq.e.comm.managers.plugin.PM: void a()> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- `<com.qq.e.comm.managers.plugin.PM: void a()> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- `<com.qq.e.comm.managers.plugin.PM: void a()> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`

**`BaseDexClassLoader`**
- `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`
- `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`
- `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`
- `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`
- `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`

### Pipeline survival (probe-matched lines)

#### benign

- Probe-matched lines processed: 9321
- Stage counts: `{"allowlist": 8560, "caller_callee_split": 8560, "signature_decomp": 8560, "reached_categorize_callee": 8560, "categorize_callee_nonempty_graph": 6977, "final_mapped": 6977, "fail_allowlist": 761, "fail_categorize_callee_empty": 1583}`
- Post-mapper `sms`: 0
- Post-mapper `dynamic_code_loading`: 0

#### malware

- Probe-matched lines processed: 11328
- Stage counts: `{"fail_allowlist": 1419, "allowlist": 9909, "caller_callee_split": 9909, "signature_decomp": 9909, "reached_categorize_callee": 9909, "categorize_callee_nonempty_graph": 9722, "final_mapped": 9722, "fail_categorize_callee_empty": 187}`
- Post-mapper `sms`: 0
- Post-mapper `dynamic_code_loading`: 0

### GATE

#### benign

- **sms**: raw_related=8, post_mapper=0, gate_trip=True
- **dynamic_code_loading**: raw_related=163, post_mapper=0, gate_trip=True
- Stage fail tallies: allowlist=761, signature_decomp=0, categorize_callee_empty=1583
- Example inputs failing at `categorize_callee` (empty graph set):
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<etv: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<etv: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<etv: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<etv: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
  - `{"class": "com.yy.iheima.aw", "method": "z", "raw_set": [], "line": "<com.yy.iheima.aw: void z(android.content.Context)> -> <com.yy.iheima.aw: java.lang.Object z(android.telephony.TelephonyManager)>"}`
- Example inputs failing at `allowlist_filter`:
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getNetworkOperator()>`
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getNetworkOperator()>`
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: int getPhoneType()>`
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getNetworkCountryIso()>`
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getSimCountryIso()>`

#### malware

- **sms**: raw_related=0, post_mapper=0, gate_trip=False
- **dynamic_code_loading**: raw_related=95, post_mapper=0, gate_trip=True
- Stage fail tallies: allowlist=1419, signature_decomp=0, categorize_callee_empty=187
- Example inputs failing at `categorize_callee` (empty graph set):
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<com.seattleclouds.util.ao: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<com.seattleclouds.util.ao: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.PhoneStateListener", "method": "onCallStateChanged", "raw_set": [], "line": "<com.seattleclouds.util.ao: void onCallStateChanged(int,java.lang.String)> -> <android.telephony.PhoneStateListener: void onCallStateChanged(int,java.lang.String)>"}`
  - `{"class": "android.telephony.SubscriptionManager", "method": "from", "raw_set": [], "line": "<c.REK: java.lang.String \u02ca(android.content.Context,int)> -> <android.telephony.SubscriptionManager: android.telephony.SubscriptionManager 'from'(android.content.Context)>"}`
  - `{"class": "android.telephony.SubscriptionManager", "method": "getActiveSubscriptionInfoList", "raw_set": [], "line": "<c.REK: java.lang.String \u02ca(android.content.Context,int)> -> <android.telephony.SubscriptionManager: java.util.List getActiveSubscriptionInfoList()>"}`
  - `{"class": "android.telephony.SubscriptionManager", "method": "getActiveSubscriptionInfoList", "raw_set": [], "line": "<c.REK: java.lang.String \u02ca(android.content.Context,int)> -> <android.telephony.SubscriptionManager: java.util.List getActiveSubscriptionInfoList()>"}`
  - `{"class": "android.telephony.SubscriptionInfo", "method": "getMnc", "raw_set": [], "line": "<c.REK: java.lang.String \u02ca(android.content.Context,int)> -> <android.telephony.SubscriptionInfo: int getMnc()>"}`
  - `{"class": "android.telephony.SubscriptionManager", "method": "addOnSubscriptionsChangedListener", "raw_set": [], "line": "<c.REK: void \u02ca(android.content.Context)> -> <android.telephony.SubscriptionManager: void addOnSubscriptionsChangedListener(android.telephony.SubscriptionManager$OnSubscriptionsChangedListener)>"}`
  - `{"class": "android.telephony.SubscriptionManager$OnSubscriptionsChangedListener", "method": "onSubscriptionsChanged", "raw_set": [], "line": "<c.REp: void onSubscriptionsChanged()> -> <android.telephony.SubscriptionManager$OnSubscriptionsChangedListener: void onSubscriptionsChanged()>"}`
  - `{"class": "android.telephony.SubscriptionManager", "method": "from", "raw_set": [], "line": "<c.REK: java.lang.String \u02ca(android.content.Context,int)> -> <android.telephony.SubscriptionManager: android.telephony.SubscriptionManager 'from'(android.content.Context)>"}`
- Example inputs failing at `allowlist_filter`:
  - `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
  - `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
  - `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
  - `<com.seattleclouds.util.ao: void <init>(com.seattleclouds.util.an)> -> <android.telephony.PhoneStateListener: void <init>()>`
  - `<com.mopub.common.ClientMetadata: void <init>(android.content.Context)> -> <android.telephony.TelephonyManager: java.lang.String getNetworkOperator()>`


### GATE — failing stage (exact)

Raw substring hits were re-examined after allowlist + signature decomposition to identify the
**callee class_name** (not merely substring presence in the callee-side text, which includes
Jimple parameter/return type names).

#### sms

| Class | Raw `SmsManager` lines | Raw `sendTextMessage` / `sendMultipart` / `SmsMessage` | Post-mapper `sms` | gate_trip |
|---|---:|---:|---:|---|
| benign | 8 | 0 / 0 / 0 | 0 | True |
| malware | 0 | 0 / 0 / 0 | 0 | False |

Benign `SmsManager` substring lines that pass allowlist + decomp (n=3 observed with class identity
`com.venmo.service.VenmoSmsManager`):

- failing stage: `categorize_callee` (returns empty set)
- input string: `<com.venmo.ApplicationState: void onCreate()> -> <com.venmo.service.VenmoSmsManager: com.venmo.service.VenmoSmsManager getDefault()>`
- decomposed: `class_name=com.venmo.service.VenmoSmsManager`, `method_name=getDefault`

No allowlisted line in either class decomposes to callee class `android.telephony.SmsManager`.
No raw callee-side hits for `sendTextMessage` / `sendMultipartTextMessage` / `SmsMessage`.

#### dynamic_code_loading

| Class | Raw Dex/Path/Base/InMemory*ClassLoader lines (sum) | Post-mapper `dynamic_code_loading` | gate_trip |
|---|---:|---:|---|
| benign | 163 | 0 | True |
| malware | 95 | 0 | True |

Two distinct loss modes for loader-related lines:

**Mode A — `allowlist_filter` (Jimple `<init>` breaks `_CALL_RE`)**

`_CALL_RE` uses `<[^<>]*>`, which cannot match a Soot signature containing nested
`<init>` / `<clinit>`. Verified: the following well-formed call line does **not** match
`_CALL_RE`, so it never reaches signature decomposition or `categorize_callee`:

- failing stage: `allowlist_filter`
- input string: `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <dalvik.system.DexClassLoader: void <init>(java.lang.String,java.lang.String,java.lang.String,java.lang.ClassLoader)>`
- note: if this line were force-parsed past the allowlist, `categorize_soot_callee` would return `dynamic_code_loading` (HOOK `DexClassLoader.<init>`).

**Mode B — `categorize_callee` empty (allowlist + decomp succeed)**

- failing stage: `categorize_callee`
- input string: `<androidx.pluginmgr.env.e: java.lang.Class loadClass(java.lang.String,boolean)> -> <dalvik.system.BaseDexClassLoader: java.lang.Class findClass(java.lang.String)>`
- decomposed: `class_name=dalvik.system.BaseDexClassLoader`, `method_name=findClass`, `categorize_callee` set = `[]`

Benign substring hits that pass decomp also include non-loader callee classes where
`DexClassLoader` / `BaseDexClassLoader` appears only in a parameter type:

- `<com.appodeal.ads.utils.i: void c(android.content.Context,java.lang.String)> -> <com.appodeal.ads.utils.i: java.lang.Object a(dalvik.system.BaseDexClassLoader)>`
- failing stage: `categorize_callee` (callee class `com.appodeal.ads.utils.i`, method `a`, empty set)

`System.load` / `System.loadLibrary` / `Runtime.exec`: raw callee-side counts are 0 / 0 / 0 in both classes.

### Generalization — 2000 allowlisted callees / class

#### benign

- Sampled: 2000 (from 136454450 seen)
- Decomp success: 2000; fail rate: 0.000000
- Decomp fail causes: `{}`
- Empty category set among decomp-ok: 1930 (rate 0.965000)
- Top 50 prefixes with empty category set:
  - `java.lang`: 440
  - `com.crashlytics`: 243
  - `android.support`: 236
  - `com.google`: 172
  - `android.view`: 107
  - `org.w3c`: 96
  - `java.util`: 82
  - `com.facebook`: 54
  - `android.content`: 43
  - `com.a`: 39
  - `java.io`: 35
  - `android.graphics`: 31
  - `org.apache`: 30
  - `org.xmlpull`: 24
  - `android.text`: 20
  - `com.b`: 17
  - `com.startapp`: 17
  - `android.util`: 16
  - `org.json`: 15
  - `com.squareup`: 13
  - `android.widget`: 11
  - `com.c`: 11
  - `java.nio`: 10
  - `a.a`: 10
  - `android.os`: 10
  - `com.fasterxml`: 9
  - `com.bumptech`: 9
  - `org.jsoup`: 6
  - `com.cmcm`: 6
  - `android.app`: 5
  - `dagger.internal`: 4
  - `com.handmark`: 4
  - `com.topringtones2017`: 3
  - `com.urbandroid`: 3
  - `android.database`: 3
  - `com.mcpeskins`: 3
  - `com.nineoldandroids`: 3
  - `com.mineworld`: 2
  - `com.masabi`: 2
  - `thai.mal`: 2
  - `com.example`: 2
  - `com.trentapps`: 2
  - `com.alibaba`: 2
  - `com.activeandroid`: 2
  - `com.pixlr`: 2
  - `epic.mychart`: 2
  - `com.seattleclouds`: 2
  - `nl.siegmann`: 2
  - `ch.boye`: 2
  - `kr`: 2

#### malware

- Sampled: 2000 (from 70705721 seen)
- Decomp success: 2000; fail rate: 0.000000
- Decomp fail causes: `{}`
- Empty category set among decomp-ok: 1918 (rate 0.959000)
- Top 50 prefixes with empty category set:
  - `java.lang`: 392
  - `android.support`: 290
  - `com.google`: 188
  - `android.view`: 169
  - `com.facebook`: 106
  - `java.util`: 100
  - `java.nio`: 72
  - `android.content`: 61
  - `gnu.bytecode`: 58
  - `gnu.mapping`: 53
  - `nl.siegmann`: 38
  - `com.seattleclouds`: 36
  - `org.xml`: 29
  - `android.app`: 25
  - `com.inca`: 25
  - `org.fmod`: 24
  - `org.mapsforge`: 18
  - `android.os`: 15
  - `com.crashlytics`: 14
  - `java.io`: 13
  - `com.lody`: 12
  - `android.util`: 12
  - `com.appmk`: 10
  - `android.media`: 9
  - `android.webkit`: 9
  - `gnu.kawa`: 9
  - `org.json`: 9
  - `org.apache`: 8
  - `com.ipphonecamera`: 8
  - `com.alibaba`: 8
  - `android.widget`: 7
  - `java.math`: 7
  - `org.xmlpull`: 6
  - `com.seniorphone`: 5
  - `com.craft`: 4
  - `aimoxiu.theme`: 4
  - `a.a`: 4
  - `com.startapp`: 4
  - `com.hitwe`: 4
  - `android.net`: 4
  - `android.graphics`: 3
  - `ru.wmr`: 3
  - `android.text`: 3
  - `io.fabric`: 2
  - `com.taobao`: 2
  - `com.knightli`: 2
  - `com.qihoo`: 2
  - `com.tencent`: 2
  - `u.aly`: 2
  - `com.baidu`: 2

## Check 2 — crypto semantics

### benign

- Crypto events: 2398520
- Caller share: `{"app_own_package": 1812054, "tls_or_network_library": 151363, "other": 435103, "app_own_package_frac": 0.7554883845037773, "tls_or_network_library_frac": 0.06310683254673716, "other_frac": 0.1814047829494855}`
- Proposed split: `{"app_initiated_events": 1812054, "transport_layer_events": 151363, "unassigned_other_events": 435103, "rule": "app_initiated := caller class is under the app's dominant caller package (mode of caller packages in that trace) and not under TLS_NETWORK_PREFIXES; transport_layer := caller under TLS_NETWORK_PREFIXES; else other", "tls_network_prefixes": ["okhttp3.", "com.squareup.okhttp.", "com.android.okhttp.", "org.apache.http.", "org.apache.commons.http", "cz.msebera.android.httpclient.", "com.android.org.conscrypt.", "org.conscrypt.", "com.google.android.gms.org.conscrypt.", "java.net.", "javax.net.", "javax.net.ssl.", "android.net.", "com.android.volley.", "com.android.okhttp", "libcore.net.", "com.google.android.gms.internal."]}`
- Per-app crypto share of mapped: `{"n": 2084, "min": 0.0, "p10": 0.0, "p25": 0.0, "p50": 0.00822662701168872, "p75": 0.21684782608695652, "p90": 0.6993023255813955, "max": 1.0, "mean": 0.1750738709358435, "mean_over_median": 21.281367282981417, "n_apps_crypto_share_gt_50pct": 289}`
#### Top 30 crypto callee classes
- `java.security.MessageDigest`: 2228943
- `javax.crypto.Cipher`: 136107
- `java.security.Provider`: 18239
- `java.security.cert.CertificateFactory`: 7400
- `java.security.cert.X509Certificate`: 3628
- `java.security.KeyPairGenerator`: 622
- `java.security.KeyStore`: 493
- `java.security.Signature`: 468
- `java.security.KeyPair`: 438
- `java.security.Key`: 428
- `java.security.KeyFactory`: 360
- `javax.crypto.KeyGenerator`: 328
- `java.security.SecureRandom`: 271
- `javax.crypto.spec.SecretKeySpec`: 269
- `javax.crypto.SecretKeyFactory`: 198
- `java.security.cert.Certificate`: 142
- `javax.crypto.Mac`: 121
- `java.security.Provider$Service`: 28
- `java.security.Security`: 26
- `java.security.AccessController`: 9
- `java.security.interfaces.RSAKey`: 2
#### Top 30 crypto caller classes
- `com.startapp.android.publish.i.x`: 1570494
- `com.facebook.ads.internal.util.s`: 484563
- `com.startapp.android.publish.j.x`: 99570
- `com.google.android.gms.internal.zzar`: 54128
- `com.google.android.gms.internal.zzaq`: 30357
- `com.google.android.gms.internal.zzo`: 21665
- `com.google.android.gms.ads.internal.util.client.zza`: 13381
- `com.google.android.gms.measurement.internal.zzn`: 10204
- `com.keyja.b.c.a`: 8643
- `io.fabric.sdk.android.services.common.CommonUtils`: 4249
- `com.baidu.crabsdk.b.d`: 4097
- `com.google.android.gms.internal.um`: 3233
- `com.google.android.gms.internal.zzir`: 3210
- `com.google.android.gms.internal.ah`: 2916
- `com.google.android.gms.internal.zzho`: 2657
- `com.google.android.gms.internal.zzpx`: 2461
- `com.google.android.gms.internal.zzpi`: 2395
- `com.google.android.gms.internal.____`: 2025
- `com.google.android.gms.internal.zzhw`: 1952
- `com.google.android.gms.internal.ur`: 1878
- `com.google.android.gms.measurement.internal.zzal`: 1858
- `com.google.android.gms.internal.zzid`: 1848
- `com.domobile.c.b`: 1721
- `com.google.code.microlog4android.repository.MicrologRepositoryNode`: 1716
- `com.google.android.gms.internal.nc`: 1599
- `com.google.android.gms.internal.zzka`: 1584
- `com.google.android.gms.b.in`: 1581
- `com.google.android.gms.internal.rb`: 1536
- `com.google.android.gms.internal.zzhu`: 1528
- `com.google.android.gms.measurement.internal.zzm`: 1388
#### Top 30 network caller classes
- `com.startapp.android.publish.i.x`: 24120
- `com.facebook.GraphRequest`: 16899
- `okhttp3.CipherSuite`: 16839
- `com.startapp.android.publish.i.p`: 7371
- `com.startapp.android.publish.i.b`: 5584
- `com.startapp.android.publish.j.w`: 4907
- `com.startapp.android.publish.h.b`: 4428
- `org.interlaken.a.b`: 4155
- `okhttp3.HttpUrl`: 3991
- `com.onesignal.OneSignalRestClient`: 3414
- `com.facebook.GraphResponse`: 3411
- `com.seattleclouds.util.a`: 2386
- `com.nostra13.universalimageloader.core.download.BaseImageDownloader`: 2210
- `com.facebook.internal.Utility`: 2101
- `com.google.android.gms.internal.zzhd`: 1797
- `com.squareup.picasso.UrlConnectionDownloader`: 1760
- `com.google.android.gms.internal.zzir`: 1692
- `com.seattleclouds.b.f`: 1624
- `com.startapp.android.publish.j.o`: 1589
- `com.startapp.android.publish.j.x`: 1564
- `com.startapp.android.publish.j.b`: 1393
- `net.dean.jraw.util.JrawUtils`: 1320
- `com.crashlytics.android.core.CodedOutputStream`: 1273
- `com.appsflyer.b`: 1137
- `com.amazon.device.ads.HttpURLConnectionWebRequest`: 1136
- `com.startapp.android.publish.j.h`: 1089
- `com.calldorado.android.service.CalldoradoCommunicationService`: 994
- `com.startapp.android.publish.i.h`: 987
- `ch.boye.httpclientandroidlib.client.utils.URIBuilder`: 952
- `okhttp3.internal.http.HttpEngine`: 952
#### Top 30 file_io caller classes
- `com.activeandroid.ModelInfo`: 74953
- `com.hmobile.biblekjv.DataBaseHelper`: 66043
- `android.support.multidex.MultiDexExtractor`: 32592
- `com.masabi.metro.client.MetroClientActivity`: 20145
- `com.seattleclouds.b.d`: 19461
- `com.crashlytics.android.core.CrashlyticsUncaughtExceptionHandler`: 10129
- `com.appaapps.past2.VocabularyActivity`: 8576
- `com.guoyu.tangshicn.db.DBHelper`: 7971
- `com.appaapps.funfair3.VocabularyActivity`: 7416
- `de.xroot.burgerking.data.BKDataImporter`: 7262
- `org.apache.cordova.file.FileUtils`: 6008
- `com.crashlytics.android.core.ClsFileOutputStream`: 4869
- `com.ducaller.db.ai`: 4709
- `android.support.multidex.MultiDex`: 3506
- `com.fxnetworks.fxnow.data.DatabaseManager`: 3400
- `org.apache.commons.io.b`: 3300
- `com.google.android.gms.common.util.zzx`: 3168
- `com.startapp.android.publish.i.r`: 3099
- `com.ducaller.db.b`: 3091
- `com.startapp.android.publish.video.a`: 2820
- `com.google.android.gms.internal.zzjw`: 2538
- `com.google.firebase.iid.zzg`: 2520
- `com.startapp.android.publish.i.k`: 2296
- `com.startapp.android.publish.h.p`: 1971
- `com.masabi.app.android.services.m`: 1939
- `com.pixlr.utilities.y`: 1921
- `com.google.android.gms.common.util.zzw`: 1827
- `com.android.camera.k`: 1754
- `com.seattleclouds.b.f`: 1736
- `com.appodeal.ads.utils.g`: 1661

### malware

- Crypto events: 839652
- Caller share: `{"app_own_package": 62750, "tls_or_network_library": 688520, "other": 88382, "app_own_package_frac": 0.07473334190831439, "tls_or_network_library_frac": 0.820006383597014, "other_frac": 0.1052602744946716}`
- Proposed split: `{"app_initiated_events": 62750, "transport_layer_events": 688520, "unassigned_other_events": 88382, "rule": "app_initiated := caller class is under the app's dominant caller package (mode of caller packages in that trace) and not under TLS_NETWORK_PREFIXES; transport_layer := caller under TLS_NETWORK_PREFIXES; else other", "tls_network_prefixes": ["okhttp3.", "com.squareup.okhttp.", "com.android.okhttp.", "org.apache.http.", "org.apache.commons.http", "cz.msebera.android.httpclient.", "com.android.org.conscrypt.", "org.conscrypt.", "com.google.android.gms.org.conscrypt.", "java.net.", "javax.net.", "javax.net.ssl.", "android.net.", "com.android.volley.", "com.android.okhttp", "libcore.net.", "com.google.android.gms.internal."]}`
- Per-app crypto share of mapped: `{"n": 1691, "min": 0.0, "p10": 0.0, "p25": 0.0, "p50": 0.18181818181818182, "p75": 0.43767018767018767, "p90": 0.693010325655282, "max": 0.9813348154323561, "mean": 0.2606512522998442, "mean_over_median": 1.433581887649143, "n_apps_crypto_share_gt_50pct": 290}`
#### Top 30 crypto callee classes
- `javax.crypto.Cipher`: 427295
- `java.security.MessageDigest`: 376270
- `java.security.Provider`: 32699
- `java.security.cert.CertificateFactory`: 1489
- `java.security.cert.X509Certificate`: 645
- `javax.crypto.SecretKeyFactory`: 518
- `javax.crypto.Mac`: 181
- `java.security.KeyFactory`: 109
- `java.security.SecureRandom`: 97
- `java.security.KeyStore`: 90
- `javax.crypto.KeyGenerator`: 70
- `java.security.cert.Certificate`: 67
- `javax.crypto.spec.SecretKeySpec`: 52
- `java.security.AccessController`: 49
- `java.security.interfaces.RSAKey`: 8
- `java.security.KeyPairGenerator`: 5
- `java.security.KeyPair`: 4
- `java.security.Key`: 4
#### Top 30 crypto caller classes
- `com.google.android.gms.internal.nc`: 264427
- `com.google.android.gms.internal.ai`: 78207
- `com.google.android.gms.internal.np`: 62987
- `com.google.android.gms.internal.ge`: 56208
- `com.google.android.gms.internal.fg`: 41329
- `com.google.android.gms.internal.om`: 39081
- `com.google.android.gms.internal.nb`: 29108
- `com.google.android.gms.ads.internal.util.client.a`: 25666
- `com.startapp.android.publish.i.x`: 22424
- `com.google.android.gms.internal.zzar`: 14562
- `com.google.android.gms.internal.rj`: 13527
- `com.a.a.a`: 12886
- `com.google.android.gms.b.er`: 12090
- `com.google.android.gms.internal.um`: 12051
- `com.google.android.gms.internal.zzaq`: 10516
- `com.google.android.gms.internal.df`: 9673
- `gnu.mapping.Namespace`: 9491
- `com.startapp.android.publish.common.commonUtils.s`: 7951
- `com.google.android.gms.internal.oy`: 7928
- `com.facebook.ads.internal.util.s`: 6981
- `x.y.h.b`: 6803
- `com.google.android.gms.internal.qp`: 6741
- `com.google.android.gms.b.kl`: 6608
- `com.google.android.gms.internal.gl`: 6130
- `com.jb.gokeyboard.theme.template.crashreport.ErrorReporter`: 6103
- `com.google.android.gms.internal.zzo`: 5161
- `com.google.android.gms.internal.fn`: 4427
- `com.startapp.android.publish.j.x`: 4291
- `com.jiubang.core.util.ErrorReporter`: 4011
- `com.google.android.gms.ads.internal.util.client.zza`: 3724
#### Top 30 network caller classes
- `com.seattleclouds.b.f`: 16919
- `com.facebook.GraphRequest`: 14978
- `com.google.android.gms.internal.mv`: 10605
- `com.seattleclouds.util.a`: 10383
- `com.google.android.gms.internal.oy`: 9155
- `com.facebook.an`: 5209
- `com.android.volley.toolbox.HurlStack`: 4854
- `com.facebook.internal.ax`: 3104
- `com.android.volley.toolbox.BasicNetwork`: 2495
- `com.android.volley.RequestQueue`: 1572
- `com.moxiu.sdk.statistics.utils.PhoneUtils`: 1387
- `com.android.volley.NetworkDispatcher`: 1309
- `com.unity3d.ads.request.WebRequest`: 1297
- `com.google.android.gms.internal.zzhd`: 1287
- `com.yaoo.qlauncher.contact.numberbelong.AssetsDatabaseManager`: 1248
- `okhttp3.l`: 1080
- `com.google.android.gms.internal.zzir`: 1074
- `com.moxiu.sdk.statistics.handler.MxPostHandler`: 851
- `com.facebook.ai`: 777
- `com.seattleclouds.b.d`: 770
- `com.umeng.fb.net.a`: 731
- `com.startapp.android.publish.j.w`: 667
- `com.animesoft.hdwallpapers.app.AppController`: 643
- `com.android.volley.toolbox.PoolingByteArrayOutputStream`: 595
- `com.google.android.gms.internal.zzhc`: 575
- `okhttp3.t`: 553
- `okhttp3.HttpUrl`: 502
- `com.c.a.a.a.k`: 478
- `com.google.android.gms.internal.zzip`: 473
- `com.c.a.a.a.v`: 468
#### Top 30 file_io caller classes
- `com.seattleclouds.b.d`: 102849
- `com.stub.StubApp`: 41857
- `com.seattleclouds.b.f`: 22866
- `org.apache.commons.io.b`: 19067
- `com.lody.virtual.server.pm.VAppManagerService`: 15158
- `com.google.android.gms.internal.fz`: 11287
- `com.google.android.gms.internal.rs`: 10793
- `com.lody.virtual.os.VEnvironment`: 8908
- `com.lody.virtual.helper.utils.AtomicFile`: 8150
- `com.qihoo.util.upgrade.Upgrade`: 6323
- `com.google.android.gms.internal.pe`: 6023
- `com.tencent.StubShell.ZipUtil`: 4906
- `com.lody.virtual.helper.utils.FileUtils`: 4696
- `com.tencent.StubShell.TxAppEntry`: 3911
- `lt.nanoline.busai.CityMapActivity`: 2568
- `com.shell.SuperApplication`: 2115
- `com.google.android.gms.internal.zzjw`: 1731
- `com.facebook.appevents.k`: 1693
- `com.google.android.gms.internal.gi`: 1218
- `com.ta.utdid2.core.persistent.TransactionXMLFile`: 1128
- `com.yyg.nemo.api.t`: 1107
- `com.lody.virtual.server.am.UidSystem`: 1075
- `com.lody.virtual.server.pm.VUserManagerService`: 1004
- `s.h.e.l.l.S`: 851
- `com.jb.gokeyboard.theme.template.crashreport.ErrorReporter`: 820
- `com.seattleclouds.App`: 812
- `com.jiubang.core.util.ErrorReporter`: 766
- `com.baidu.protect.StubApplication`: 763
- `com.google.android.gms.internal.zzjg`: 760
- `com.yyg.nemo.j.k`: 708

## Check 3 — allowlist asymmetry

### benign

- Dropped sample: 500 (from 19074512 dropped seen)
- Bucket counts: `{"well_formed_call_should_have_been_allowed": 498, "other": 2}`
- GATE well_formed_call_should_have_been_allowed nonempty: **True**
- Per-app drop rate dist: `{"n": 2256, "min": 0.00010367276379097572, "p10": 0.06541902566673327, "p25": 0.118479489687011, "p50": 0.22619462775751611, "p75": 0.38468575669174476, "p90": 0.5330527589934163, "max": 1.0, "mean": 0.27005564779824914, "mean_over_median": 1.1939083190240605}`
#### Bucket `malformed_or_truncated_call_line` examples
- `<org.apache.cordova.PluginResult: void <init>(org.apache.cordova.PluginResult$Status,java.lang.String)> -> <java.lang.Enum: int ordinal()>`
- `<com.contextlogic.wish.api.service.compound.AuthenticationService: void <init>()> -> <com.contextlogic.wish.api.service.standalone.GetUserStatusService: void <init>()>`
- `<com.facebook.GraphRequestBatch: void <init>(java.util.Collection)> -> <java.util.ArrayList: void <init>(java.util.Collection)>`
- `<com.google.android.gms.measurement.internal.zzl$zza: void <init>(java.lang.String,com.google.android.gms.internal.zzlz,java.lang.Object)> -> <java.lang.Object: void <init>()>`
- `<com.crashlytics.android.core.ByteString: com.crashlytics.android.core.ByteString copyFromUtf8(java.lang.String)> -> <com.crashlytics.android.core.ByteString: void <init>(byte[])>`
- `<android.support.v7.widget.q: void <init>(android.content.Context,android.util.AttributeSet,int)> -> <android.widget.ImageView: void <init>(android.content.Context,android.util.AttributeSet,int)>`
- `<com.google.android.gms.ads.internal.request.zza: void <init>()> -> <java.lang.Object: void <init>()>`
- `<com.domobile.frame.a.a: java.lang.String a(java.lang.Object[])> -> <java.lang.StringBuffer: void <init>()>`
- `<com.google.android.gms.measurement.internal.zzab: com.google.android.gms.measurement.internal.zzal zzj(com.google.android.gms.measurement.internal.zzx)> -> <com.google.android.gms.measurement.internal.zzal: void <init>(com.google.android.gms.measurement.internal.zzx)>`
- `<com.google.android.gms.ads.identifier.AdvertisingIdClient: void <init>(android.content.Context,long,boolean)> -> <java.lang.Object: void <init>()>`
#### Bucket `other` examples
- `<com.google.android.gms.ads.internal.request.AdRequestInfoParcel: void <init>(int,android.os.Bundle,com.google.android.gms.ads.internal.client.AdRequestParcel,com.google.android.gms.ads.internal.client.AdSizeParcel,java.lang.String,android.content.pm.ApplicationInfo,android.content.pm.PackageInfo,java.lang.String,java.lang.String,java.lang.String,com.google.android.gms.ads.internal.util.client.VersionInfoParcel,android.os.Bundle,int,java.util.List,android.os.Bundle,boolean,android.os.Messenger,i`
- `<com.google.android.gms.ads.internal.request.AdRequestInfoParcel: void <init>(int,android.os.Bundle,com.google.android.gms.ads.internal.client.AdRequestParcel,com.google.android.gms.ads.internal.client.AdSizeParcel,java.lang.String,android.content.pm.ApplicationInfo,android.content.pm.PackageInfo,java.lang.String,java.lang.String,java.lang.String,com.google.android.gms.ads.internal.util.client.VersionInfoParcel,android.os.Bundle,int,java.util.List,android.os.Bundle,boolean,android.os.Messenger,i`
#### Top 40 dropped line prefixes
- `<com.crashlytics.android.core.ByteString`: 1291260
- `<com.google.android.gms.measurement.inte`: 557893
- `<com.crashlytics.android.core.SessionPro`: 281770
- `<com.google.android.gms.ads.internal.cli`: 277977
- `<android.support.v7.widget.AppCompatText`: 240118
- `<com.b.a.o: com.b.a.i a(org.w3c.dom.Node`: 232840
- `<com.google.android.gms.analytics.intern`: 207110
- `<com.google.gson.stream.JsonReader: java`: 167474
- `<com.b.a.k: void <init>(java.lang.String`: 165274
- `<android.support.v7.widget.TintTypedArra`: 161172
- `<android.support.v7.widget.Toolbar: void`: 144281
- `<com.google.android.gms.common.internal.`: 136740
- `<android.support.v7.widget.AppCompatImag`: 132149
- `<com.handmark.data.ScCode: void <init>(o`: 130118
- `<thai.mal.dictionary.WordRec: void <init`: 125941
- `<com.startapp.android.publish.b.a.e.c: b`: 123067
- `<com.google.android.gms.common.api.Statu`: 102872
- `<com.pixlr.utilities.Path: void <init>(c`: 102434
- `<com.startapp.android.publish.g.a.e.c: b`: 100968
- `<com.neatplug.u3d.plugins.common.d: void`: 100203
- `<com.google.android.gms.internal.zzfx: v`: 96494
- `<com.google.android.gms.ads.internal.uti`: 86595
- `<android.support.graphics.drawable.PathP`: 76926
- `<android.support.v7.graphics.ColorCutQua`: 68946
- `<com.pixlr.model.c: void <init>(com.pixl`: 67415
- `<thai.mal.dictionary.Menu: void loadreco`: 63739
- `<com.usnaviguide.radarnow.model.RadarSta`: 62507
- `<org.osmdroid.util.GeoPoint: void <init>`: 62260
- `<com.startapp.android.publish.h.a.e.c: b`: 62064
- `<android.support.v7.widget.AppCompatButt`: 60183
- `<com.google.android.gms.internal.zzdc: v`: 58461
- `<com.fasterxml.jackson.databind.introspe`: 58391
- `<b.b: void <init>(org.w3c.dom.Element)> `: 58304
- `<com.google.gson.Gson: void <init>(com.g`: 58074
- `<android.support.v7.widget.AppCompatBack`: 54933
- `<com.crashlytics.android.ByteString: voi`: 54584
- `<com.crashlytics.android.ByteString: com`: 54074
- `<com.google.android.gms.ads.AdSize: void`: 53399
- `<br: void <init>(byte[])> -> <java.lang.`: 52457
- `<com.google.android.gms.internal.zzbt: v`: 52448
#### Top 20 highest drop-rate apps
- `benign2017/com.iabuzz.Puzzle4KidsTools.apk.logcat`: drop_rate=1.0000, dropped=146, nonblank=146, events=0
- `benign2017/com.mapquest.android.ace.apk.logcat`: drop_rate=1.0000, dropped=98, nonblank=98, events=0
- `benign2017/com.bbt.myfi.apk.logcat`: drop_rate=1.0000, dropped=58, nonblank=58, events=0
- `benign2017/com.meetingplay.con17.apk.logcat`: drop_rate=1.0000, dropped=57, nonblank=57, events=0
- `benign2017/8DC59AF71C86765549C3A23B8A172FFFB43E1B6226F9C1AF6BD5DD8831F5F08E.apk.logcat`: drop_rate=1.0000, dropped=50, nonblank=50, events=0
- `benign2017/com.iart.chromecastapps.apk.logcat`: drop_rate=1.0000, dropped=32, nonblank=32, events=0
- `benign2017/no.mobitroll.kahoot.android.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/mbinc12.mb32b.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.peacock.flashlight.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.mxtech.ffmpeg.v7_vfpv3d16.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.mxtech.ffmpeg.v7_neon.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.mxtech.ffmpeg.v6_vfp.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.microsoft.rdc.android.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.innovapps.maquillajeparahombres.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.google.android.apps.pdfviewer.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.creepycat.fireblue.fire_blue.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.cam001.selfie.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/com.aws.android.tsunami.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/FDC5401D6FCB3389B9AE1EA0517E59107ABF7B04D7103101A3248089F76FEF6F.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `benign2017/F8030D5721B9DEE4392E5DAF25187E6CE39CE1E74985ED1936D0CC29B1C31D43.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0

### malware

- Dropped sample: 500 (from 27551904 dropped seen)
- Bucket counts: `{"well_formed_call_should_have_been_allowed": 499, "malformed_or_truncated_call_line": 1}`
- GATE well_formed_call_should_have_been_allowed nonempty: **True**
- Per-app drop rate dist: `{"n": 1742, "min": 0.0001191087939724144, "p10": 0.05666939230814273, "p25": 0.07864730137110104, "p50": 0.3236469556029252, "p75": 0.49517922007970616, "p90": 0.6003608080320859, "max": 1.0, "mean": 0.31886135443505303, "mean_over_median": 0.9852135140311855}`
#### Bucket `malformed_or_truncated_call_line` examples
- `<gnu.lists.PairWithPosition: gnu.lists.PairWithPosition make(java.lang.Object,java.lang.Object,java.lang.String,int)> -> <gnu.lists.PairWithPosition: void <init>(java.lang.Object,java.lang.Object)>`
- `<com.google.android.gms.ads.e: void <clinit>()> -> <com.google.android.gms.ads.e: void <init>(int,int,java.lang.String)>`
- `<com.google.android.gms.internal.de: void <clinit>()> -> <com.google.android.gms.internal.cn: com.google.android.gms.internal.cn a(java.lang.String,java.lang.Boolean)>`
- `<com.google.android.gms.common.g: void <clinit>()> -> <java.lang.Object: void <init>()>`
- `<gnu.expr.ModuleMethod: void <init>(gnu.expr.ModuleBody,int,java.lang.Object,int)> -> <gnu.mapping.MethodProc: void <init>()>`
- `<gnu.mapping.SymbolRef: void <init>(gnu.mapping.Symbol,gnu.mapping.Namespace)> -> <java.lang.ref.WeakReference: void <init>(java.lang.Object)>`
- `<com.google.android.gms.ads.internal.client.zzad: void <init>(com.google.android.gms.ads.internal.client.zzad$zza,com.google.android.gms.ads.search.SearchAdRequest)> -> <java.util.Collections: java.util.Set unmodifiableSet(java.util.Set)>`
- `<gnu.mapping.SymbolRef: void <init>(gnu.mapping.Symbol,gnu.mapping.Namespace)> -> <java.lang.ref.WeakReference: void <init>(java.lang.Object)>`
- `<com.google.android.gms.internal.de: void <clinit>()> -> <java.lang.Boolean: java.lang.Boolean valueOf(boolean)>`
- `<gnu.math.IntNum: void <init>(int)> -> <gnu.math.RatNum: void <init>()>`
#### Top 40 dropped line prefixes
- `<gnu.math.IntNum: void <init>(int)> -> <`: 2954016
- `<gnu.math.IntNum: void <clinit>()> -> <g`: 2913819
- `<mirror.RefMethod: void <init>(java.lang`: 772214
- `<gnu.mapping.Symbol: void <init>(gnu.map`: 664755
- `<gnu.mapping.Namespace: gnu.mapping.Symb`: 651591
- `<com.google.android.gms.ads.internal.cli`: 645712
- `<gnu.mapping.SimpleSymbol: void <init>(j`: 643282
- `<gnu.expr.ModuleMethod: void <init>(gnu.`: 474095
- `<mirror.RefStaticMethod: void <init>(jav`: 458215
- `<com.google.appinventor.components.runti`: 385519
- `<gnu.mapping.SymbolRef: void <init>(gnu.`: 325973
- `<gnu.lists.FString: void <init>(java.lan`: 264640
- `<com.google.android.gms.internal.de: voi`: 259000
- `<com.google.android.gms.analytics.intern`: 205639
- `<gnu.lists.LList: void <init>()> -> <gnu`: 194757
- `<gnu.lists.Pair: void <init>()> -> <gnu.`: 189778
- `<gnu.lists.ImmutablePair: void <init>(ja`: 189391
- `<gnu.lists.PairWithPosition: void <init>`: 189066
- `<gnu.lists.PairWithPosition: gnu.lists.P`: 188841
- `<com.google.android.gms.internal.ce: voi`: 178420
- `<com.google.android.gms.internal.nc: byt`: 176406
- `<com.seattleclouds.b.d: int[] a(java.lan`: 160609
- `<com.google.android.gms.internal.cp: voi`: 158440
- `<com.google.android.gms.ads.internal.uti`: 150784
- `<com.google.android.gms.internal.e: void`: 141591
- `<com.google.android.gms.internal.af: voi`: 140219
- `<com.google.android.gms.internal.zzba: v`: 130155
- `<com.google.android.gms.internal.ak: voi`: 117635
- `<com.google.android.gms.ads.e: void <ini`: 117408
- `<com.google.android.gms.ads.e: void <cli`: 117379
- `<com.google.android.gms.internal.dz: voi`: 107137
- `<gnu.bytecode.Method: void <init>(gnu.by`: 105626
- `<gnu.bytecode.ClassType: gnu.bytecode.Me`: 105387
- `<com.google.android.gms.common.g: void <`: 102523
- `<com.google.android.gms.internal.cg: voi`: 97229
- `<com.google.android.gms.internal.v: void`: 97226
- `<com.google.android.gms.measurement.inte`: 94496
- `<com.google.android.gms.internal.zzhy: v`: 92773
- `<com.google.android.gms.internal.zzjd: v`: 90092
- `<gnu.bytecode.PrimType: void <init>(java`: 87439
#### Top 20 highest drop-rate apps
- `malware-2017/04D66C98B6A115BD61A65BD20DB1D10F4A871AD65FC173949757C8A74D2BF8D8.apk.logcat`: drop_rate=1.0000, dropped=633, nonblank=633, events=0
- `malware-2017/01C2890377C08AAD5C4804DC6D0DD966AE0F4ED642B403081171E9AF18933E70.apk.logcat`: drop_rate=1.0000, dropped=563, nonblank=563, events=0
- `malware-2017/0642C54F15B535F25AC1ECFE1C5087FE70422B3A313D434B22E2112AF4B1FD65.apk.logcat`: drop_rate=1.0000, dropped=3, nonblank=3, events=0
- `malware-2017/0588C18955C329F9830D30F06FD6950D5B60EF5680DE37CB454A62A01C1B3915.apk.logcat`: drop_rate=1.0000, dropped=3, nonblank=3, events=0
- `malware-2017/02497C0ACA93D6039D1D9EDB33FED58BB2DF9ABDE52438CCFD89E9ACA3A7D43F.apk.logcat`: drop_rate=1.0000, dropped=3, nonblank=3, events=0
- `malware-2017/0247EBF3FB4092E54FEE3B5CABBC359779B4D5905E47902502C91C4ABC3DC9ED.apk.logcat`: drop_rate=1.0000, dropped=3, nonblank=3, events=0
- `malware-2017/002086D558A084FBFBC9B67129728FC495B9ADC85D99E4AC20461E1F5E4E9248.apk.logcat`: drop_rate=1.0000, dropped=3, nonblank=3, events=0
- `malware-2017/0024330D6A5193B78A9CB3597C17E61B30F39D5E5CC7EFF1C80A5B60C5904BB0.apk.logcat`: drop_rate=1.0000, dropped=2, nonblank=2, events=0
- `malware-2017/02FFE06E88212FF20111FE2F85215BABDC7BEB3A3AB62480BF1090C0F789F128.apk.logcat`: drop_rate=0.8775, dropped=9013, nonblank=10271, events=1258
- `malware-2017/0050A6BB8C45DDCF6999325753F731ACF479941181C3B4E2101A699156A20CBC.apk.logcat`: drop_rate=0.7510, dropped=29194, nonblank=38872, events=9678
- `malware-2017/00F3EFD6BA2F529CC5C86E67195D0DB4EF7AC2A8B709BEA3A1DC8A42A9FFD376.apk.logcat`: drop_rate=0.7481, dropped=294681, nonblank=393913, events=98595
- `malware-2017/0459FAAD8BA5CF69EECD619A6E29F4B95AC78B706D6E7BBF7A1EF20DA4DE84A5.apk.logcat`: drop_rate=0.7388, dropped=6744, nonblank=9128, events=2384
- `malware-2017/00F111163D88D14779961EB507F28512BB89646F07C4651AD7A81FFC49444DF1.apk.logcat`: drop_rate=0.7174, dropped=198, nonblank=276, events=78
- `malware-2017/058F72D1972EFD1ACF3846CDAC259FBF8F640B40E8D94EF83E664B0B6FBF347D.apk.logcat`: drop_rate=0.7129, dropped=169513, nonblank=237787, events=68274
- `malware-2017/03DBF650ADF07B808E9EA9E097E30301196BBF78560C197C6FE0F9406B484FA5.apk.logcat`: drop_rate=0.7108, dropped=13863, nonblank=19503, events=5640
- `malware-2017/0297DD21E4D0A5CF6B4838CAC025231F119C2294FF4A68C9F67339042786B32C.apk.logcat`: drop_rate=0.6962, dropped=5895, nonblank=8468, events=2573
- `malware-2017/013B4E3D4001C0D0A52785957DC7F233913C91E4BE31601388CF4871638EBECD.apk.logcat`: drop_rate=0.6899, dropped=8339, nonblank=12087, events=3748
- `malware-2017/04BEBDE1D11DE945F4043AAACB818CF54EDB0FDEB83062E84FD29FAD3E3E498E.apk.logcat`: drop_rate=0.6897, dropped=7478, nonblank=10842, events=3364
- `malware-2017/0145F24B707BF4607F16A7B15A7619EDCFAC51BF5490843A449E05CA0F355503.apk.logcat`: drop_rate=0.6891, dropped=6500, nonblank=9433, events=2933
- `malware-2017/02DDC76A6424F9591F218D69BEFF99A8C879DD596B16C8529EF41708E61C343D.apk.logcat`: drop_rate=0.6888, dropped=7516, nonblank=10912, events=3396


### Check 3 GATE — well-formed calls dropped by allowlist (`<init>`-aware reclassification)

#### benign bucket_counts: `{"well_formed_call_should_have_been_allowed": 498, "other": 2}`

- gate nonempty: **True**
- well_formed count in sample of 500: 498
- `<org.apache.cordova.PluginResult: void <init>(org.apache.cordova.PluginResult$Status,java.lang.String)> -> <java.lang.Enum: int ordinal()>`
- `<com.contextlogic.wish.api.service.compound.AuthenticationService: void <init>()> -> <com.contextlogic.wish.api.service.standalone.GetUserStatusService: void <init>()>`
- `<com.facebook.GraphRequestBatch: void <init>(java.util.Collection)> -> <java.util.ArrayList: void <init>(java.util.Collection)>`
- `<com.google.android.gms.measurement.internal.zzl$zza: void <init>(java.lang.String,com.google.android.gms.internal.zzlz,java.lang.Object)> -> <java.lang.Object: void <init>()>`
- `<com.crashlytics.android.core.ByteString: com.crashlytics.android.core.ByteString copyFromUtf8(java.lang.String)> -> <com.crashlytics.android.core.ByteString: void <init>(byte[])>`
- `<android.support.v7.widget.q: void <init>(android.content.Context,android.util.AttributeSet,int)> -> <android.widget.ImageView: void <init>(android.content.Context,android.util.AttributeSet,int)>`
- `<com.google.android.gms.ads.internal.request.zza: void <init>()> -> <java.lang.Object: void <init>()>`
- `<com.domobile.frame.a.a: java.lang.String a(java.lang.Object[])> -> <java.lang.StringBuffer: void <init>()>`
- `<com.google.android.gms.measurement.internal.zzab: com.google.android.gms.measurement.internal.zzal zzj(com.google.android.gms.measurement.internal.zzx)> -> <com.google.android.gms.measurement.internal.zzal: void <init>(com.google.android.gms.measurement.internal.zzx)>`
- `<com.google.android.gms.ads.identifier.AdvertisingIdClient: void <init>(android.content.Context,long,boolean)> -> <java.lang.Object: void <init>()>`

#### malware bucket_counts: `{"well_formed_call_should_have_been_allowed": 499, "malformed_or_truncated_call_line": 1}`

- gate nonempty: **True**
- well_formed count in sample of 500: 499
- `<gnu.lists.PairWithPosition: gnu.lists.PairWithPosition make(java.lang.Object,java.lang.Object,java.lang.String,int)> -> <gnu.lists.PairWithPosition: void <init>(java.lang.Object,java.lang.Object)>`
- `<com.google.android.gms.ads.e: void <clinit>()> -> <com.google.android.gms.ads.e: void <init>(int,int,java.lang.String)>`
- `<com.google.android.gms.internal.de: void <clinit>()> -> <com.google.android.gms.internal.cn: com.google.android.gms.internal.cn a(java.lang.String,java.lang.Boolean)>`
- `<com.google.android.gms.common.g: void <clinit>()> -> <java.lang.Object: void <init>()>`
- `<gnu.expr.ModuleMethod: void <init>(gnu.expr.ModuleBody,int,java.lang.Object,int)> -> <gnu.mapping.MethodProc: void <init>()>`
- `<gnu.mapping.SymbolRef: void <init>(gnu.mapping.Symbol,gnu.mapping.Namespace)> -> <java.lang.ref.WeakReference: void <init>(java.lang.Object)>`
- `<com.google.android.gms.ads.internal.client.zzad: void <init>(com.google.android.gms.ads.internal.client.zzad$zza,com.google.android.gms.ads.search.SearchAdRequest)> -> <java.util.Collections: java.util.Set unmodifiableSet(java.util.Set)>`
- `<gnu.mapping.SymbolRef: void <init>(gnu.mapping.Symbol,gnu.mapping.Namespace)> -> <java.lang.ref.WeakReference: void <init>(java.lang.Object)>`
- `<com.google.android.gms.internal.de: void <clinit>()> -> <java.lang.Boolean: java.lang.Boolean valueOf(boolean)>`
- `<gnu.math.IntNum: void <init>(int)> -> <gnu.math.RatNum: void <init>()>`

## Check 4 — trivial baselines (AUC)

- These AUCs are the floor any ABRG result must clear.

### total_event_count

- AUC=0.331490, U=1.28e+06, p=3.56e-74, n_benign=2225, n_malware=1734
- Higher at median: **malware**; higher at mean: **benign**
- Benign dist: `{"n": 2225, "min": 1.0, "p10": 330.40000000000003, "p25": 807.0, "p50": 4328.0, "p75": 31909.0, "p90": 137915.00000000023, "max": 1664929.0, "mean": 61341.19370786517, "mean_over_median": 14.17310390662319}`
- Malware dist: `{"n": 1734, "min": 24.0, "p10": 2158.0, "p25": 9729.25, "p50": 17277.0, "p75": 55122.5, "p90": 92090.2, "max": 1606665.0, "mean": 40791.797001153405, "mean_over_median": 2.361046304402003}`

### mapped_event_count

- AUC=0.309937, U=1.2e+06, p=7.39e-94, n_benign=2225, n_malware=1734
- Higher at median: **malware**; higher at mean: **benign**
- Benign dist: `{"n": 2225, "min": 0.0, "p10": 3.0, "p25": 21.0, "p50": 131.0, "p75": 662.0, "p90": 2253.0, "max": 270350.0, "mean": 1799.6777528089888, "mean_over_median": 13.737998113045716}`
- Malware dist: `{"n": 1734, "min": 0.0, "p10": 98.30000000000001, "p25": 205.0, "p50": 562.0, "p75": 1449.0, "p90": 2921.7000000000016, "max": 454292.0, "mean": 1421.8985005767013, "mean_over_median": 2.530068506364237}`

### distinct_active_categories

- AUC=0.486015, U=1.88e+06, p=0.128, n_benign=2225, n_malware=1734
- Higher at median: **malware**; higher at mean: **malware**
- Benign dist: `{"n": 2225, "min": 0.0, "p10": 1.0, "p25": 2.0, "p50": 5.0, "p75": 7.0, "p90": 9.0, "max": 13.0, "mean": 4.9892134831460675, "mean_over_median": 0.9978426966292135}`
- Malware dist: `{"n": 1734, "min": 0.0, "p10": 2.0, "p25": 3.0, "p50": 6.0, "p75": 7.0, "p90": 8.0, "max": 13.0, "mean": 5.115916955017301, "mean_over_median": 0.8526528258362168}`

### allowlist_drop_rate

- AUC=0.439761, U=1.73e+06, p=6.09e-11, n_benign=2256, n_malware=1742
- Higher at median: **malware**; higher at mean: **malware**
- Benign dist: `{"n": 2256, "min": 0.00010367276379097572, "p10": 0.06541902566673327, "p25": 0.118479489687011, "p50": 0.22619462775751611, "p75": 0.38468575669174476, "p90": 0.5330527589934163, "max": 1.0, "mean": 0.27005564779824914, "mean_over_median": 1.1939083190240605}`
- Malware dist: `{"n": 1742, "min": 0.0001191087939724144, "p10": 0.05666939230814273, "p25": 0.07864730137110104, "p50": 0.3236469556029252, "p75": 0.49517922007970616, "p90": 0.6003608080320859, "max": 1.0, "mean": 0.31886135443505303, "mean_over_median": 0.9852135140311855}`

